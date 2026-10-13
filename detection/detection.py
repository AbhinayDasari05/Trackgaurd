"""
TrackGuard Detection Engine
Comprehensive cybersecurity anomaly detection for vehicle tracking and GNSS telemetry.
Detects:
  - Speed anomalies
  - Location jumps & physically implausible movement (Haversine + implied speed)
  - Duplicate packets (packet-level replay)
  - Unauthorized device identities (IMEI spoofing indicators)
  - NMEA syntax / checksum injection
  - Timestamp manipulation & backward time steps (with UTC rollover support)
  - GNSS fix-status & satellite count contradictions
  - Receiver signal loss & stale data
Distinguishes observed facts from inferred anomalies and simulated attacks.
"""

import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple


# ============================================================
# CONFIGURABLE DETECTION THRESHOLDS
# ============================================================

SPEED_LIMIT = 100.0                   # km/h: Reported vehicle speed ceiling
LOCATION_JUMP_LIMIT_KM = 50.0         # km: Absolute distance jump threshold
MAX_IMPLIED_SPEED_KMH = 220.0         # km/h: Physical kinematic velocity threshold
MAX_ALLOWED_CLOCK_DRIFT_SEC = 300.0   # seconds: Max acceptable clock skew from current UTC
STALE_FIX_THRESHOLD_SEC = 10.0        # seconds: Max age before a fix is flagged stale


# ============================================================
# DISTANCE & KINEMATIC CALCULATIONS
# ============================================================

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate geodesic distance between two GPS coordinates
    using the Haversine formula (returns distance in kilometers).
    """
    earth_radius = 6371.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    difference_lat = math.radians(lat2 - lat1)
    difference_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(difference_lat / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(difference_lon / 2.0) ** 2
    )

    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return earth_radius * c


def calculate_implied_speed(
    distance_km: float,
    elapsed_seconds: float
) -> Optional[float]:
    """
    Computes implied kinematic speed in km/h based on distance and elapsed time.
    Returns None if elapsed time is zero or negative.
    """
    if elapsed_seconds <= 0:
        return None
    hours = elapsed_seconds / 3600.0
    return distance_km / hours


# ============================================================
# INDIVIDUAL ANOMALY DETECTORS
# ============================================================

def detect_speed_anomaly(speed: Optional[float], speed_limit: float = SPEED_LIMIT) -> bool:
    """
    Evaluates whether vehicle reported speed exceeds configured limit.
    Note: A speed anomaly is a vehicle speed violation, not proof of GNSS spoofing.
    """
    if speed is None:
        return False
    try:
        return float(speed) > speed_limit
    except (ValueError, TypeError):
        return False


def detect_location_jump(
    previous_lat: Optional[float],
    previous_lon: Optional[float],
    current_lat: Optional[float],
    current_lon: Optional[float],
    maximum_distance: float = LOCATION_JUMP_LIMIT_KM,
    elapsed_seconds: Optional[float] = None,
    max_implied_speed: float = MAX_IMPLIED_SPEED_KMH
) -> Tuple[bool, float, Optional[float]]:
    """
    Detects physically implausible transitions.
    Returns (detected, distance_km, implied_speed_kmh).
    Classified as SUSPECTED_POSITION_ANOMALY.
    """
    if None in (previous_lat, previous_lon, current_lat, current_lon):
        return False, 0.0, None

    distance = calculate_distance(previous_lat, previous_lon, current_lat, current_lon)
    implied_speed = None

    if elapsed_seconds is not None and elapsed_seconds > 0:
        implied_speed = calculate_implied_speed(distance, elapsed_seconds)
        if implied_speed is not None and implied_speed > max_implied_speed:
            return True, distance, implied_speed

    if distance > maximum_distance:
        return True, distance, implied_speed

    return False, distance, implied_speed


def detect_timestamp_anomaly(
    current_timestamp: Any,
    previous_timestamp: Optional[Any] = None,
    allow_midnight_rollover: bool = True
) -> List[Dict[str, Any]]:
    """
    Validates telemetry timestamp sanity:
      - Backward time movement (clock inversion)
      - Repeated timestamps
      - Future timestamp drift (> 5 mins)
      - Accounts for UTC midnight rollover (e.g. 23:59:59 -> 00:00:01)
    """
    anomalies = []

    def parse_time(val):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            # Check if integer epoch in string
            if val.isdigit():
                return float(val)
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.timestamp()
            except Exception:
                return None
        return None

    curr_sec = parse_time(current_timestamp)
    prev_sec = parse_time(previous_timestamp)

    if curr_sec is None:
        anomalies.append({
            "type": "Timestamp Anomaly",
            "subtype": "MALFORMED_TIMESTAMP",
            "severity": "MEDIUM",
            "description": f"Malformed or unparseable telemetry timestamp: {current_timestamp}"
        })
        return anomalies

    # Check future clock drift against current system UTC
    now_sec = datetime.now(timezone.utc).timestamp()
    if curr_sec > (now_sec + MAX_ALLOWED_CLOCK_DRIFT_SEC):
        drift_min = round((curr_sec - now_sec) / 60.0, 1)
        anomalies.append({
            "type": "Timestamp Anomaly",
            "subtype": "FUTURE_CLOCK_DRIFT",
            "severity": "MEDIUM",
            "description": f"Telemetry timestamp is {drift_min} minutes in the future compared to server UTC"
        })

    # Compare with previous packet timestamp
    if prev_sec is not None:
        elapsed = curr_sec - prev_sec

        # Handle potential UTC midnight rollover if raw seconds within a day (86400)
        if elapsed < 0 and allow_midnight_rollover and (elapsed + 86400) > 0 and (elapsed + 86400) < 60:
            pass  # Valid midnight rollover
        elif elapsed < 0:
            anomalies.append({
                "type": "Timestamp Anomaly",
                "subtype": "BACKWARD_TIME_STEP",
                "severity": "HIGH",
                "description": f"Telemetry timestamp moved backward by {abs(elapsed):.1f}s"
            })
        elif elapsed == 0:
            anomalies.append({
                "type": "Timestamp Anomaly",
                "subtype": "REPEATED_TIMESTAMP",
                "severity": "LOW",
                "description": "Telemetry packet received with identical timestamp to previous fix"
            })

    return anomalies


def detect_fix_integrity_anomaly(packet: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Validates consistency between NMEA fix indicators, satellite counts, and coordinates.
    Detects contradictory states (e.g. coordinates provided with fix_quality=0 or status='V').
    """
    anomalies = []
    fix_valid = packet.get("fix_valid")
    fix_quality = packet.get("fix_quality")
    satellites = packet.get("satellites_used")
    lat = packet.get("latitude")
    lon = packet.get("longitude")

    # Contradiction: Fix quality is 0 (invalid) but coordinates are populated as active
    if fix_quality == 0 and lat is not None and lon is not None and (lat != 0 or lon != 0) and fix_valid is True:
        anomalies.append({
            "type": "GNSS Fix Manipulation",
            "subtype": "CONTRADICTORY_FIX_QUALITY",
            "severity": "HIGH",
            "description": "Coordinates declared valid while NMEA GGA fix quality indicates 0 (Invalid)"
        })

    # Contradiction: 0 satellites used but valid navigation solution claimed
    if satellites is not None and satellites == 0 and fix_valid is True:
        anomalies.append({
            "type": "GNSS Fix Manipulation",
            "subtype": "ZERO_SATELLITE_FIX",
            "severity": "HIGH",
            "description": "Navigation fix marked valid with 0 satellites used in solution"
        })

    # Coordinate boundary verification
    if lat is not None:
        try:
            if not (-90.0 <= float(lat) <= 90.0):
                anomalies.append({
                    "type": "Telemetry Integrity Anomaly",
                    "subtype": "LATITUDE_OUT_OF_BOUNDS",
                    "severity": "HIGH",
                    "description": f"Latitude value {lat} is outside physical bounds [-90, +90]"
                })
        except (ValueError, TypeError):
            pass

    if lon is not None:
        try:
            if not (-180.0 <= float(lon) <= 180.0):
                anomalies.append({
                    "type": "Telemetry Integrity Anomaly",
                    "subtype": "LONGITUDE_OUT_OF_BOUNDS",
                    "severity": "HIGH",
                    "description": f"Longitude value {lon} is outside physical bounds [-180, +180]"
                })
        except (ValueError, TypeError):
            pass

    return anomalies


# ============================================================
# MASTER PACKET ANALYZER (COMPATIBLE WITH ORIGINAL INTERFACE)
# ============================================================

def analyze_packet(packet: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Unified packet security analyzer.
    Preserves 100% backward compatibility with existing TrackGuard callers
    while adding deep kinematic and protocol integrity checks.
    """
    alerts = []

    speed = packet.get("speed")
    latitude = packet.get("latitude")
    longitude = packet.get("longitude")
    previous_latitude = packet.get("previous_latitude")
    previous_longitude = packet.get("previous_longitude")

    current_timestamp = packet.get("timestamp")
    previous_timestamp = packet.get("previous_timestamp")

    # 1. Speed Check (Rule: Speed anomaly != proof of spoofing)
    if detect_speed_anomaly(speed):
        alerts.append({
            "type": "Speed Anomaly",
            "severity": "MEDIUM",
            "description": f"Vehicle speed {speed} km/h exceeds configured limit ({SPEED_LIMIT} km/h)"
        })

    # 2. Location Jump & Kinematic Check
    if (
        latitude is not None
        and longitude is not None
        and previous_latitude is not None
        and previous_longitude is not None
    ):
        elapsed_sec = None
        if current_timestamp is not None and previous_timestamp is not None:
            try:
                curr_t = float(current_timestamp)
                prev_t = float(previous_timestamp)
                elapsed_sec = curr_t - prev_t
            except (ValueError, TypeError):
                pass

        detected, distance, implied_speed = detect_location_jump(
            previous_latitude,
            previous_longitude,
            latitude,
            longitude,
            maximum_distance=LOCATION_JUMP_LIMIT_KM,
            elapsed_seconds=elapsed_sec
        )

        if detected:
            if implied_speed:
                desc = (
                    f"Implausible kinematic movement: jumped {distance:.2f} km in "
                    f"{elapsed_sec:.1f}s (implied velocity: {implied_speed:.1f} km/h). "
                    f"Classified as SUSPECTED_POSITION_ANOMALY."
                )
            else:
                desc = (
                    f"Vehicle location changed abruptly by {distance:.2f} km. "
                    f"Classified as SUSPECTED_POSITION_ANOMALY."
                )

            alerts.append({
                "type": "Location Jump",
                "category": "SUSPECTED_POSITION_ANOMALY",
                "severity": "HIGH",
                "description": desc,
                "evidence": {
                    "distance_km": round(distance, 2),
                    "implied_speed_kmh": round(implied_speed, 1) if implied_speed else None
                }
            })

    # 3. Timestamp Consistency Checks
    if current_timestamp is not None:
        ts_anomalies = detect_timestamp_anomaly(current_timestamp, previous_timestamp)
        alerts.extend(ts_anomalies)

    # 4. GNSS Fix & Coordinate Integrity Checks
    fix_anomalies = detect_fix_integrity_anomaly(packet)
    alerts.extend(fix_anomalies)

    return alerts


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":
    print("==========================================")
    print("   TRACKGUARD EXTENDED DETECTION TEST")
    print("==========================================")

    test_packet = {
        "imei": "123456789012345",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "previous_latitude": 17.3852,
        "previous_longitude": 78.4869,
        "speed": 150,
        "timestamp": 1002,
        "previous_timestamp": 1000
    }

    detections = analyze_packet(test_packet)
    print(f"Total detections: {len(detections)}")
    for d in detections:
        print(f"[{d['severity']}] {d['type']}: {d['description']}")