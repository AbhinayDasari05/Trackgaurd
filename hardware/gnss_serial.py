"""
TrackGuard Hardware GNSS Serial Ingestion Service
Supports physical 7semi NEO-M9N GNSS breakout and ESP32 UART bridge.
Provides thread-safe parsing of NMEA sentences (GGA, RMC, GLL, GSA, GSV, VTG)
and normalized JSON emitted over USB serial.
"""

import os
import sys
import time
import json
import re
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

# Platform-aware default configuration
DEFAULT_BAUD = int(os.environ.get("TRACKGUARD_BAUD_RATE", "38400"))
DEFAULT_TIMEOUT = float(os.environ.get("TRACKGUARD_SERIAL_TIMEOUT", "2.0"))
RECONNECT_INTERVAL = float(os.environ.get("TRACKGUARD_RECONNECT_INTERVAL", "3.0"))
STALE_THRESHOLD_SECONDS = float(os.environ.get("TRACKGUARD_STALE_SECONDS", "5.0"))


def auto_detect_serial_port() -> Optional[str]:
    """
    Detect available GNSS or ESP32 serial port dynamically across Windows and macOS.
    Prefers active u-blox (NEO-M9N) or Silicon Labs CP210x (ESP32) devices.
    """
    if serial is None:
        return None

    env_port = os.environ.get("TRACKGUARD_SERIAL_PORT")
    if env_port:
        return env_port

    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None

    # Priority 1: Check for u-blox native USB device (VID:PID 1546:01A9)
    for p in ports:
        if "1546:01A9" in (p.hwid or "").upper() or "u-blox" in (p.description or "").lower():
            return p.device

    # Priority 2: Check for CP210x / ESP32 UART bridge (VID:PID 10C4:EA60)
    for p in ports:
        if "10C4:EA60" in (p.hwid or "").upper() or "cp210" in (p.description or "").lower():
            return p.device

    # Priority 3: Common GNSS COM ports on Windows (e.g., COM9, COM3, COM10)
    for p in ports:
        if p.device.upper() in ["COM9", "COM3", "COM10"]:
            return p.device

    # Priority 4: macOS serial ports (/dev/cu.usbserial*, /dev/cu.SLAB_USBtoUART*)
    for p in ports:
        if "/dev/cu.usb" in p.device.lower() or "slab" in p.device.lower():
            return p.device

    # Fallback to the first available non-Bluetooth serial device
    for p in ports:
        if "bluetooth" not in (p.description or "").lower():
            return p.device

    return ports[0].device


def validate_nmea_checksum(sentence: str) -> bool:
    """
    Validates NMEA 0183 XOR checksum.
    Sentence format: $TAG,data...*HH
    """
    if not sentence or not sentence.startswith("$"):
        return False

    parts = sentence.split("*")
    if len(parts) != 2:
        return False

    body = parts[0][1:]  # Exclude leading '$'
    expected_hex = parts[1].strip()

    if len(expected_hex) < 2:
        return False

    checksum = 0
    for char in body:
        checksum ^= ord(char)

    try:
        calculated_hex = f"{checksum:02X}"
        return calculated_hex.upper() == expected_hex[:2].upper()
    except ValueError:
        return False


def nmea_to_decimal_degrees(raw_coord: str, direction: str, is_longitude: bool = False) -> Optional[float]:
    """
    Accurately converts NMEA degrees-and-minutes (ddmm.mmmmm or dddmm.mmmmm)
    to decimal degrees.
    """
    if not raw_coord or not direction:
        return None

    direction = direction.strip().upper()
    if direction not in ("N", "S", "E", "W"):
        return None

    try:
        deg_digits = 3 if is_longitude else 2
        degrees = float(raw_coord[:deg_digits])
        minutes = float(raw_coord[deg_digits:])
        decimal = degrees + (minutes / 60.0)

        if direction in ("S", "W"):
            decimal = -decimal

        return round(decimal, 7)
    except (ValueError, IndexError):
        return None


class GNSSHardwareReceiver:
    """
    Thread-safe GNSS receiver service for real NEO-M9N / ESP32 hardware.
    Maintains connection health, handles automatic reconnection, parses NMEA & JSON,
    and exposes normalized telemetry states.
    """

    def __init__(self, port: Optional[str] = None, baud: int = DEFAULT_BAUD):
        self.configured_port = port
        self.baud = baud
        self.active_port: Optional[str] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Telemetry state
        self.connected = False
        self.reconnecting = False
        self.error_message: Optional[str] = None
        self.last_read_timestamp: Optional[datetime] = None
        self.last_valid_fix_timestamp: Optional[datetime] = None
        self.last_valid_position: Optional[Tuple[float, float]] = None

        # Normalized GNSS metrics
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.speed_kmh: Optional[float] = None
        self.altitude_m: Optional[float] = None
        self.satellites_used: int = 0
        self.satellites_in_view: int = 0
        self.hdop: Optional[float] = None
        self.fix_quality: int = 0  # 0=Invalid, 1=GPS SPS, 2=DGPS, etc.
        self.fix_valid: bool = False
        self.nmea_talker: str = "GN"
        self.active_sentences: Dict[str, str] = {}
        self.total_messages_received = 0
        self.checksum_errors = 0
        self.on_packet_callback = None
        self._last_logged_time = 0.0
        self._ser = None

    def start(self):
        """Start the background serial ingestion loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, name="TrackGuard-GNSS-Reader", daemon=True)
            self._thread.start()

    def stop(self):
        """Stop the background serial ingestion loop."""
        self._running = False
        with self._lock:
            if self._ser:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def set_port(self, port: Optional[str] = None, baud: Optional[int] = None):
        """Dynamically reconfigure the serial port and force immediate reconnect."""
        old_ser = None
        with self._lock:
            self.configured_port = port
            if baud:
                self.baud = baud
            self.connected = False
            self.reconnecting = True
            self.error_message = None
            if self._ser:
                old_ser = self._ser
                self._ser = None
        if old_ser:
            try:
                old_ser.close()
            except Exception:
                pass

    def reconnect(self, port: Optional[str] = None, baud: Optional[int] = None) -> Dict[str, Any]:
        """Force an immediate disconnect and reconnection to specified or auto-detected port."""
        target = port or self.configured_port or auto_detect_serial_port()
        self.set_port(target, baud)
        # Give reader loop time to open the port
        time.sleep(0.6)
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        """Returns thread-safe snapshot of hardware GNSS status.

        connected is True when:
          - The serial port context is active (self.connected = True), OR
          - Data was received very recently (< 10 s), indicating the thread
            is between reconnect cycles but the device is clearly alive.
        This prevents the "DISCONNECTED" badge from flickering while 30,000+
        NMEA sentences have already arrived and data_age is < 1 s.
        """
        RECENT_DATA_WINDOW = 10.0   # seconds — considered still-connected

        with self._lock:
            now = datetime.now(timezone.utc)
            read_age = (now - self.last_read_timestamp).total_seconds() if self.last_read_timestamp else None
            fix_age  = (now - self.last_valid_fix_timestamp).total_seconds() if self.last_valid_fix_timestamp else None

            # A device is "effectively connected" if the port thread says so OR
            # if we received data very recently (handles brief reconnect windows).
            data_is_fresh = read_age is not None and read_age < RECENT_DATA_WINDOW
            effectively_connected = self.connected or data_is_fresh

            # Determine human-readable fix state
            if not effectively_connected:
                fix_state = "DISCONNECTED"
            elif self.fix_valid:
                if fix_age is not None and fix_age > STALE_THRESHOLD_SECONDS:
                    fix_state = "STALE_FIX"
                else:
                    fix_state = "VALID_FIX"
            elif self.last_valid_fix_timestamp is not None:
                fix_state = "LOST_FIX"
            else:
                fix_state = "NO_FIX"

            return {
                "connected": effectively_connected,
                "reconnecting": self.reconnecting and not data_is_fresh,
                "port": self.active_port or self.configured_port or "Auto-detect",
                "baud": self.baud,
                "fix_state": fix_state,
                "fix_valid": self.fix_valid and (fix_age is None or fix_age <= STALE_THRESHOLD_SECONDS),
                "fix_quality": self.fix_quality,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "speed_kmh": self.speed_kmh,
                "altitude_m": self.altitude_m,
                "satellites_used": self.satellites_used,
                "satellites_in_view": self.satellites_in_view,
                "hdop": self.hdop,
                "data_age_seconds": round(read_age, 1) if read_age is not None else None,
                "fix_age_seconds": round(fix_age, 1) if fix_age is not None else None,
                "last_update": self.last_read_timestamp.isoformat() if self.last_read_timestamp else None,
                "last_valid_fix_time": self.last_valid_fix_timestamp.isoformat() if self.last_valid_fix_timestamp else None,
                "error": self.error_message,
                "source": "7semi NEO-M9N GNSS (Hardware)",
                "source_type": "HARDWARE",
                "simulation": False,
                "total_messages": self.total_messages_received,
                "checksum_errors": self.checksum_errors,
            }

    def _run_loop(self):
        """Continuous serial read loop with automatic reconnection."""
        while self._running:
            target_port = self.configured_port or auto_detect_serial_port()
            if not target_port or serial is None:
                with self._lock:
                    self.connected = False
                    self.error_message = "No GNSS serial device found or PySerial not installed"
                time.sleep(RECONNECT_INTERVAL)
                continue

            self.active_port = target_port

            try:
                time.sleep(0.3)
                ser = serial.Serial(target_port, self.baud, timeout=DEFAULT_TIMEOUT)
                with self._lock:
                    self._ser = ser
                    self.connected = True
                    self.reconnecting = False
                    self.error_message = None

                # Flush initial garbage
                ser.reset_input_buffer()

                while self._running and (self.configured_port is None or self.configured_port == target_port):
                    try:
                        raw_line = ser.readline().decode("ascii", errors="replace").strip()
                    except (serial.SerialException, UnicodeDecodeError, OSError, TypeError, AttributeError) as e:
                        with self._lock:
                            self.error_message = f"Read error: {e}"
                        break

                    if not raw_line:
                        continue

                    self._process_incoming_line(raw_line)

            except (serial.SerialException, PermissionError, OSError, TypeError, AttributeError) as exc:
                with self._lock:
                    self.connected = False
                    self.reconnecting = True
                    self.error_message = f"Port {target_port} error: {exc}"
                time.sleep(RECONNECT_INTERVAL)
            except Exception as exc:
                with self._lock:
                    self.connected = False
                    self.reconnecting = True
                    self.error_message = f"Loop error: {exc}"
                time.sleep(RECONNECT_INTERVAL)
            finally:
                with self._lock:
                    if self._ser:
                        try:
                            self._ser.close()
                        except Exception:
                            pass
                        self._ser = None
                    self.connected = False

    def _process_incoming_line(self, line: str):
        """Processes a single line from serial (NMEA or JSON)."""
        now = datetime.now(timezone.utc)

        with self._lock:
            self.last_read_timestamp = now
            self.total_messages_received += 1

        # Check for normalized JSON emitted by custom ESP32 firmware
        if line.startswith("{") and line.endswith("}"):
            self._parse_json_packet(line, now)
            return

        # Check for NMEA 0183 sentence
        if line.startswith("$"):
            self._parse_nmea_sentence(line, now)

    def _parse_json_packet(self, line: str, now: datetime):
        """Parse normalized JSON from ESP32."""
        try:
            data = json.loads(line)
            with self._lock:
                if "latitude" in data and "longitude" in data:
                    lat = data.get("latitude")
                    lon = data.get("longitude")
                    if lat is not None and lon is not None:
                        self.latitude = float(lat)
                        self.longitude = float(lon)
                        self.last_valid_position = (self.latitude, self.longitude)
                        self.last_valid_fix_timestamp = now

                if "speed_kmh" in data:
                    self.speed_kmh = float(data.get("speed_kmh") or 0.0)
                elif "speed" in data:
                    self.speed_kmh = float(data.get("speed") or 0.0)

                if "altitude_m" in data:
                    self.altitude_m = float(data.get("altitude_m") or 0.0)
                if "satellites_used" in data:
                    self.satellites_used = int(data.get("satellites_used") or 0)
                if "satellites_in_view" in data:
                    self.satellites_in_view = int(data.get("satellites_in_view") or 0)
                if "hdop" in data:
                    self.hdop = float(data.get("hdop") or 0.0)
                if "fix_valid" in data:
                    self.fix_valid = bool(data.get("fix_valid"))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            with self._lock:
                self.error_message = f"JSON parse error: {exc}"

    def _parse_nmea_sentence(self, sentence: str, now: datetime):
        """
        Parses standard NMEA 0183 sentences:
        $xxGGA, $xxRMC, $xxGLL, $xxGSA, $xxGSV, $xxVTG
        """
        if "*" in sentence and not validate_nmea_checksum(sentence):
            with self._lock:
                self.checksum_errors += 1
            return

        # Strip checksum part
        body = sentence.split("*")[0]
        fields = body.split(",")
        if len(fields) < 2:
            return

        tag = fields[0][1:].upper()  # e.g., GNGGA, GPRMC, GNGSA
        if len(tag) >= 5:
            self.nmea_talker = tag[:2]
            sentence_type = tag[2:]
        else:
            sentence_type = tag

        with self._lock:
            self.active_sentences[sentence_type] = sentence

        # -------------------------------------------------------------
        # GGA: Global Positioning System Fix Data
        # $xxGGA,time,lat,NS,lon,EW,quality,numSV,HDOP,alt,altUnit,geoid,geoidUnit,age,station
        # -------------------------------------------------------------
        if sentence_type == "GGA" and len(fields) >= 10:
            try:
                quality_str = fields[6]
                quality = int(quality_str) if quality_str else 0
                num_sats = int(fields[7]) if fields[7] else 0
                hdop = float(fields[8]) if fields[8] else None
                alt = float(fields[9]) if fields[9] else None

                raw_lat = fields[2]
                lat_dir = fields[3]
                raw_lon = fields[4]
                lon_dir = fields[5]

                lat = nmea_to_decimal_degrees(raw_lat, lat_dir, is_longitude=False)
                lon = nmea_to_decimal_degrees(raw_lon, lon_dir, is_longitude=True)

                with self._lock:
                    self.fix_quality = quality
                    self.satellites_used = num_sats
                    if hdop is not None:
                        self.hdop = hdop
                    if alt is not None:
                        self.altitude_m = alt

                    # GGA Quality > 0 indicates valid fix (1=SPS, 2=DGPS, etc.)
                    if quality > 0 and lat is not None and lon is not None:
                        self.fix_valid = True
                        self.latitude = lat
                        self.longitude = lon
                        self.last_valid_position = (lat, lon)
                        self.last_valid_fix_timestamp = now
                    elif quality == 0:
                        self.fix_valid = False
            except (ValueError, IndexError):
                pass

        # -------------------------------------------------------------
        # RMC: Recommended Minimum Specific GNSS Data
        # $xxRMC,time,status,lat,NS,lon,EW,spd_knots,course,date,magVar,magDir,mode
        # -------------------------------------------------------------
        elif sentence_type == "RMC" and len(fields) >= 8:
            try:
                status = fields[2].upper()  # 'A'=Valid, 'V'=Navigation receiver warning / Invalid
                raw_lat = fields[3]
                lat_dir = fields[4]
                raw_lon = fields[5]
                lon_dir = fields[6]
                spd_knots = float(fields[7]) if fields[7] else 0.0

                lat = nmea_to_decimal_degrees(raw_lat, lat_dir, is_longitude=False)
                lon = nmea_to_decimal_degrees(raw_lon, lon_dir, is_longitude=True)

                with self._lock:
                    self.speed_kmh = round(spd_knots * 1.852, 2)
                    if status == "A" and lat is not None and lon is not None:
                        self.fix_valid = True
                        self.latitude = lat
                        self.longitude = lon
                        self.last_valid_position = (lat, lon)
                        self.last_valid_fix_timestamp = now
                        if self.on_packet_callback and (time.time() - self._last_logged_time >= 3.0):
                            self._last_logged_time = time.time()
                            try:
                                self.on_packet_callback({
                                    "device_id": "trackguard-gnss-01",
                                    "latitude": lat,
                                    "longitude": lon,
                                    "speed": self.speed_kmh or 0.0,
                                    "altitude": self.altitude_m,
                                    "satellites_used": self.satellites_used,
                                    "hdop": self.hdop,
                                    "timestamp": int(now.timestamp()),
                                    "raw_sentence": sentence.strip()
                                })
                            except Exception:
                                pass
                    elif status == "V":
                        self.fix_valid = False
            except (ValueError, IndexError):
                pass

        # -------------------------------------------------------------
        # GLL: Geographic Position - Latitude/Longitude
        # $xxGLL,lat,NS,lon,EW,time,status,mode
        # -------------------------------------------------------------
        elif sentence_type == "GLL" and len(fields) >= 7:
            try:
                status = fields[6].upper()
                raw_lat = fields[1]
                lat_dir = fields[2]
                raw_lon = fields[3]
                lon_dir = fields[4]

                lat = nmea_to_decimal_degrees(raw_lat, lat_dir, is_longitude=False)
                lon = nmea_to_decimal_degrees(raw_lon, lon_dir, is_longitude=True)

                with self._lock:
                    if status == "A" and lat is not None and lon is not None:
                        self.latitude = lat
                        self.longitude = lon
                        self.last_valid_position = (lat, lon)
                        self.last_valid_fix_timestamp = now
            except (ValueError, IndexError):
                pass

        # -------------------------------------------------------------
        # GSA: GNSS DOP and Active Satellites
        # $xxGSA,mode1,mode2,sv1..sv12,PDOP,HDOP,VDOP
        # -------------------------------------------------------------
        elif sentence_type == "GSA" and len(fields) >= 18:
            try:
                # Active satellites used in solution
                active_sats = [s for s in fields[3:15] if s.strip()]
                hdop = float(fields[16]) if fields[16] else None

                with self._lock:
                    if active_sats:
                        self.satellites_used = len(active_sats)
                    if hdop is not None:
                        self.hdop = hdop
            except (ValueError, IndexError):
                pass

        # -------------------------------------------------------------
        # GSV: GNSS Satellites in View
        # $xxGSV,totalMsgs,msgNum,totalSVs,...
        # -------------------------------------------------------------
        elif sentence_type == "GSV" and len(fields) >= 4:
            try:
                total_svs = int(fields[3]) if fields[3] else 0
                with self._lock:
                    self.satellites_in_view = total_svs
            except (ValueError, IndexError):
                pass

        # -------------------------------------------------------------
        # VTG: Course Over Ground and Ground Speed
        # $xxVTG,trackTrue,T,trackMag,M,speedKnots,N,speedKmh,K,mode
        # -------------------------------------------------------------
        elif sentence_type == "VTG" and len(fields) >= 8:
            try:
                speed_kmh = float(fields[7]) if fields[7] else None
                if speed_kmh is not None:
                    with self._lock:
                        self.speed_kmh = round(speed_kmh, 2)
            except (ValueError, IndexError):
                pass


# Singleton instance for application-wide use
gnss_hardware = GNSSHardwareReceiver()
