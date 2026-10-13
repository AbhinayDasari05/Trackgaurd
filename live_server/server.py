import socket
import json
import time
import sys
import os
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# ============================================================
# TRACKGUARD LIVE SECURITY SERVER
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "parser"))

from detection.detection import analyze_packet
from mitigation.mitigation import apply_mitigation
from database.database import (
    create_tables,
    check_imei,
    is_replay,
    store_fingerprint,
    create_fingerprint
)
from parser.gt06_parser import parse_gt06_packet
from hardware.gnss_serial import nmea_to_decimal_degrees, validate_nmea_checksum


# ============================================================
# CONFIGURATION
# ============================================================

HOST = os.environ.get("TRACKGUARD_HOST", "0.0.0.0")
PORT = int(os.environ.get("TRACKGUARD_PORT", "5006"))
BUFFER_SIZE = 4096

DB_PATH = str(BASE_DIR / "trackguard.db")


# ============================================================
# DEVICE AUTHORIZATION & REPLAY DETECTION HELPERS
# ============================================================

def check_device_authorization(device_id):
    """
    Verify whether incoming device_id / IMEI is registered and authorized.
    Returns True if authorized, False if unauthorized (IMEI Spoofing).
    """
    if not device_id:
        return False
    return check_imei(str(device_id))


def check_replay_attack(device_id, latitude, longitude, speed, timestamp):
    """
    Check if a packet with the same telemetry and timestamp has been received before.
    Returns True if replay attack detected, False if new packet.
    """
    if timestamp is None:
        return False

    fingerprint = create_fingerprint(device_id, "TCP", "GPS", f"{latitude}_{longitude}_{speed}_{timestamp}")
    if is_replay(fingerprint):
        return True

    store_fingerprint(fingerprint, str(device_id))
    return False


# ============================================================
# STORE LAST LOCATION & TIMESTAMPS FOR EACH DEVICE
# ============================================================

previous_locations = {}


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_database():
    try:
        create_tables()
        print("Database initialized and verified.")
    except Exception as error:
        print("Database initialization error:", error)


# ============================================================
# SAVE PACKET TO DATABASE
# ============================================================

def save_packet_to_database(
    packet,
    detection_time_ms,
    validation_status
):
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        device_id = packet.get("device_id") or packet.get("imei")
        source = packet.get("source", "TCP")
        is_sim = 1 if packet.get("simulation") or packet.get("is_simulation") else 0
        source_type = packet.get("source_type") or ("SIMULATION" if is_sim else "HARDWARE")
        protocol = packet.get("protocol", "TCP")
        packet_type = packet.get("packet_type", "GPS")
        lat = packet.get("latitude")
        lon = packet.get("longitude")
        spd = packet.get("speed") or packet.get("speed_kmh")
        ts = packet.get("timestamp")
        fix_val = 1 if packet.get("fix_valid", True) else 0
        sats = int(packet.get("satellites_used") or 0)
        hdop = packet.get("hdop")
        alt = packet.get("altitude") or packet.get("altitude_m")

        cursor.execute(
            """
            INSERT INTO packets
            (
                imei, protocol, packet_type, validation_status,
                latitude, longitude, speed, timestamp, detection_time_ms,
                source, source_type, is_simulation, fix_valid, satellites_used, hdop, altitude
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id, protocol, packet_type, validation_status,
                lat, lon, spd, ts, detection_time_ms,
                source, source_type, is_sim, fix_val, sats, hdop, alt
            )
        )

        connection.commit()
        packet_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO packet_history
            (
                packet_id, imei, protocol, packet_type, validation_status,
                latitude, longitude, speed, timestamp, detection_time_ms,
                source, source_type, is_simulation, fix_valid, satellites_used, hdop, altitude
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet_id, device_id, protocol, packet_type, validation_status,
                lat, lon, spd, ts, detection_time_ms,
                source, source_type, is_sim, fix_val, sats, hdop, alt
            )
        )

        connection.commit()
        connection.close()

        print(f"Database: packet #{packet_id} saved")
        return packet_id

    except sqlite3.Error as error:
        print("Database error:", error)
        return None


# ============================================================
# SAVE SECURITY EVENT TO DATABASE
# ============================================================

def save_security_event(
    packet_id,
    packet,
    detection,
    mitigation_result
):
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        device_id = packet.get("device_id") or packet.get("imei")

        cursor.execute(
            """
            INSERT INTO security_events
            (
                packet_id, imei, attack_type, severity, description, action, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet_id,
                device_id,
                detection.get("type"),
                detection.get("severity"),
                detection.get("description"),
                mitigation_result.get("action"),
                "DETECTED"
            )
        )

        event_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO security_events_history
            (
                event_id, packet_id, imei, attack_type, severity, description, action, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                packet_id,
                device_id,
                detection.get("type"),
                detection.get("severity"),
                detection.get("description"),
                mitigation_result.get("action"),
                "DETECTED"
            )
        )

        connection.commit()
        connection.close()

        print(f"Database: security event #{event_id} saved")

    except sqlite3.Error as error:
        print("Security event database error:", error)


# ============================================================
# PROCESS GPS PACKET
# ============================================================

def process_packet(packet):
    detection_start = time.perf_counter()

    device_id = packet.get("device_id") or packet.get("imei")
    latitude = packet.get("latitude")
    longitude = packet.get("longitude")
    speed = packet.get("speed") if packet.get("speed") is not None else packet.get("speed_kmh")
    timestamp = packet.get("timestamp")

    print("\n==========================================")
    print("          TRACKGUARD GPS PACKET")
    print("==========================================")
    print("Device   :", device_id)
    print("Latitude :", latitude)
    print("Longitude:", longitude)
    print("Speed    :", speed)
    print("Timestamp:", timestamp)
    print("Source   :", packet.get("source_type", "HARDWARE"))

    # Add previous location and timestamp
    previous = previous_locations.get(device_id)
    if previous:
        packet["previous_latitude"] = previous.get("latitude")
        packet["previous_longitude"] = previous.get("longitude")
        packet["previous_timestamp"] = previous.get("timestamp")
    else:
        packet["previous_latitude"] = None
        packet["previous_longitude"] = None
        packet["previous_timestamp"] = None

    # 1. Telemetry checks (Speed Anomaly & Location Jump & Kinematics)
    detections = analyze_packet(packet)

    # 2. Device Identity Authorization Check (IMEI Spoofing)
    if not check_device_authorization(device_id):
        detections.append({
            "type": "IMEI Spoofing",
            "severity": "HIGH",
            "description": f"Unauthorized device identity: {device_id}"
        })

    # 3. Packet Fingerprint Replay Check (Replay Attack)
    if check_replay_attack(device_id, latitude, longitude, speed, timestamp):
        detections.append({
            "type": "Replay Attack",
            "severity": "HIGH",
            "description": "Repeated GPS packet with identical timestamp & telemetry detected"
        })

    detection_end = time.perf_counter()
    detection_time_ms = (detection_end - detection_start) * 1000

    print(f"Detection Processing Time: {detection_time_ms:.3f} ms")

    validation_status = "ANOMALY_DETECTED" if detections else "NORMAL"

    packet_id = save_packet_to_database(
        packet,
        detection_time_ms,
        validation_status
    )

    if detections:
        print("\n[ALERT] SECURITY ANOMALY DETECTED")
        for detection in detections:
            print("\n----------------------------------------")
            print("Attack        :", detection["type"])
            print("Severity      :", detection["severity"])
            print("Description   :", detection["description"])
            print(f"Detection Time: {detection_time_ms:.3f} ms")
            print("----------------------------------------")

            alert = {
                "imei": device_id,
                "alert_type": detection["type"],
                "severity": detection["severity"],
                "description": detection["description"],
                "detection_time_ms": detection_time_ms
            }

            result = apply_mitigation(alert)

            if packet_id is not None:
                save_security_event(
                    packet_id,
                    packet,
                    detection,
                    result
                )
    else:
        print("\n[OK] No security anomalies detected.")

    # Save current location & timestamp if valid
    if latitude is not None and longitude is not None:
        previous_locations[device_id] = {
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": timestamp
        }

    print("\n==========================================")


# ============================================================
# START SERVER
# ============================================================

def start_server():
    print("=" * 60)
    print("        TRACKGUARD LIVE SECURITY SERVER")
    print("=" * 60)
    print(f"Listening on {HOST}:{PORT}")
    print("Security detection : ENABLED")
    print("Mitigation engine  : ENABLED")
    print("Detection timing   : ENABLED")
    print("Database logging   : ENABLED")
    print("Protocols supported: JSON Lines, GT06 ASCII, NMEA 0183")
    print("Waiting for GPS device connection...")

    initialize_database()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
    except OSError as err:
        print(f"Failed to bind to {HOST}:{PORT}: {err}")
        return

    server_socket.listen(5)

    try:
        while True:
            client_socket, address = server_socket.accept()
            print("\nConnection from:", address)
            buffer = ""

            try:
                while True:
                    data = client_socket.recv(BUFFER_SIZE)
                    if not data:
                        break

                    buffer += data.decode("utf-8", errors="ignore")

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        # 1. JSON Lines
                        if line.startswith("{") and line.endswith("}"):
                            try:
                                packet = json.loads(line)
                                process_packet(packet)
                            except json.JSONDecodeError as exc:
                                print("Invalid JSON packet:", exc)

                        # 2. GT06 ASCII format
                        elif "IMEI:" in line or "TYPE:" in line:
                            try:
                                parsed = parse_gt06_packet(line)
                                packet = {
                                    "device_id": parsed["imei"],
                                    "protocol": parsed["protocol"],
                                    "packet_type": parsed["packet_type"],
                                    "latitude": parsed["latitude"],
                                    "longitude": parsed["longitude"],
                                    "speed": parsed["speed"],
                                    "timestamp": parsed["timestamp"],
                                    "source": "gt06_tcp",
                                    "source_type": "HARDWARE"
                                }
                                process_packet(packet)
                            except Exception as exc:
                                print("GT06 parse error:", exc)

                        # 3. NMEA 0183 ($GPRMC, $GNGGA, etc.)
                        elif line.startswith("$"):
                            if "*" in line and not validate_nmea_checksum(line):
                                print("Rejected NMEA sentence with bad checksum:", line)
                                continue

                            parts = line.split("*")[0].split(",")
                            tag = parts[0][1:].upper()
                            if "RMC" in tag and len(parts) >= 8:
                                lat = nmea_to_decimal_degrees(parts[3], parts[4])
                                lon = nmea_to_decimal_degrees(parts[5], parts[6], is_longitude=True)
                                knots = float(parts[7]) if parts[7] else 0.0
                                packet = {
                                    "device_id": "trackguard-gnss-01",
                                    "protocol": "NMEA",
                                    "packet_type": "RMC",
                                    "latitude": lat,
                                    "longitude": lon,
                                    "speed": round(knots * 1.852, 2),
                                    "timestamp": int(time.time()),
                                    "source": "nmea_tcp",
                                    "source_type": "HARDWARE"
                                }
                                process_packet(packet)

            except ConnectionResetError:
                print("Client connection reset.")
            finally:
                client_socket.close()
                print("\nConnection closed.")

    except KeyboardInterrupt:
        print("\n\nStopping TrackGuard server...")
    finally:
        server_socket.close()
        print("TrackGuard server stopped.")


if __name__ == "__main__":
    start_server()
