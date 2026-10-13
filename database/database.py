import sqlite3
import hashlib
import os
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "trackguard.db")
DB_NAME = DB_PATH


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    return sqlite3.connect(DB_NAME)


# ============================================================
# CREATE DATABASE TABLES & SAFE VERSIONED MIGRATIONS
# ============================================================

def create_tables():
    connection = get_connection()
    cursor = connection.cursor()

    # Authorized devices
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        device_id INTEGER PRIMARY KEY AUTOINCREMENT,
        imei TEXT UNIQUE NOT NULL,
        device_name TEXT,
        status TEXT DEFAULT 'AUTHORIZED',
        registered_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Received packets
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS packets (
        packet_id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id INTEGER,
        imei TEXT,
        protocol TEXT,
        packet_type TEXT,
        received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        validation_status TEXT,
        latitude REAL,
        longitude REAL,
        speed REAL,
        timestamp INTEGER,
        detection_time_ms REAL,
        FOREIGN KEY(device_id) REFERENCES devices(device_id)
    )
    """)

    # Security events
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS security_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        packet_id INTEGER,
        imei TEXT,
        attack_type TEXT,
        severity TEXT,
        description TEXT,
        action TEXT,
        event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT
    )
    """)

    # Packet fingerprints for replay detection
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS packet_fingerprints (
        fingerprint TEXT PRIMARY KEY,
        imei TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Historical packet archive
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS packet_history (
        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        packet_id INTEGER,
        device_id INTEGER,
        imei TEXT,
        protocol TEXT,
        packet_type TEXT,
        received_at DATETIME,
        validation_status TEXT,
        latitude REAL,
        longitude REAL,
        speed REAL,
        timestamp INTEGER,
        detection_time_ms REAL,
        archived_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Historical security events archive
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS security_events_history (
        history_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER,
        packet_id INTEGER,
        imei TEXT,
        attack_type TEXT,
        severity TEXT,
        description TEXT,
        action TEXT,
        event_time DATETIME,
        status TEXT,
        archived_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Attack simulation & detection laboratory runs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS simulation_runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_id TEXT NOT NULL,
        scenario_name TEXT NOT NULL,
        input_summary TEXT,
        expected_detection TEXT,
        observed_detection TEXT,
        severity TEXT,
        mitigation_action TEXT,
        pass_fail TEXT,
        evidence_details TEXT,
        is_simulation INTEGER DEFAULT 1,
        executed_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # SDR capture metadata & offline analysis
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sdr_captures (
        capture_id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        filesize_bytes INTEGER,
        sample_format TEXT,
        sample_rate_sps REAL,
        center_freq_hz REAL,
        analysis_status TEXT,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Audit log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_type TEXT NOT NULL,
        details TEXT,
        actor TEXT DEFAULT 'SYSTEM',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Default authorized devices
    cursor.execute("""
    INSERT OR IGNORE INTO devices (imei, device_name, status)
    VALUES ('TG001', 'TrackGuard-Primary', 'AUTHORIZED')
    """)
    cursor.execute("""
    INSERT OR IGNORE INTO devices (imei, device_name, status)
    VALUES ('123456789012345', 'GT06-001', 'AUTHORIZED')
    """)
    cursor.execute("""
    INSERT OR IGNORE INTO devices (imei, device_name, status)
    VALUES ('trackguard-gnss-01', 'NEO-M9N-Hardware', 'AUTHORIZED')
    """)

    # Non-destructive migrations for extra telemetry columns
    extra_packet_cols = [
        ("source", "TEXT DEFAULT 'TCP'"),
        ("source_type", "TEXT DEFAULT 'UNKNOWN'"),
        ("is_simulation", "INTEGER DEFAULT 0"),
        ("fix_valid", "INTEGER DEFAULT 1"),
        ("satellites_used", "INTEGER DEFAULT 0"),
        ("hdop", "REAL"),
        ("altitude", "REAL"),
        ("payload", "TEXT")
    ]

    for table in ("packets", "packet_history"):
        cursor.execute(f"PRAGMA table_info({table})")
        existing_cols = {col[1] for col in cursor.fetchall()}
        for col_name, col_def in extra_packet_cols:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                except sqlite3.OperationalError:
                    pass

    # Seed SDR capture metadata record if empty
    cursor.execute("SELECT COUNT(*) FROM sdr_captures")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO sdr_captures
        (filename, filesize_bytes, sample_format, sample_rate_sps, center_freq_hz, analysis_status, notes)
        VALUES (
            'adalm_pluto_2.4ghz_raw.bin',
            10485760,
            'int16 complex (I/Q)',
            4000000.0,
            2400000000.0,
            'ANALYZED_NON_GNSS',
            'ADALM-PLUTO SDR Rev.C capture at 2.4 GHz. Explicit notice: capture is at 2.4 GHz ISM band; has not established GPS L1 (1575.42 MHz) signals. Nonzero I/Q samples are RF energy, not proof of GNSS signals.'
        )
        """)

    connection.commit()
    connection.close()


# ============================================================
# DEVICE FUNCTIONS
# ============================================================

def add_device(imei, device_name):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO devices
    (imei, device_name, status)
    VALUES (?, ?, ?)
    """, (
        imei,
        device_name,
        "AUTHORIZED"
    ))

    connection.commit()
    connection.close()


def check_imei(imei):
    if not imei:
        return False

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT status
    FROM devices
    WHERE imei = ?
    """, (str(imei),))

    result = cursor.fetchone()
    connection.close()

    if result is None:
        return False

    return result[0] == "AUTHORIZED"


# ============================================================
# PACKET FUNCTIONS
# ============================================================

def add_packet(
    device_id,
    imei,
    protocol,
    packet_type,
    validation_status,
    latitude=None,
    longitude=None,
    speed=None,
    timestamp=None,
    detection_time_ms=0.0,
    source="TCP",
    source_type="TCP",
    is_simulation=0,
    fix_valid=1,
    satellites_used=0,
    hdop=None,
    altitude=None,
    payload=None
):
    if payload is None:
        if protocol == "NMEA" and latitude is not None and longitude is not None:
            ns = "N" if latitude >= 0 else "S"
            ew = "E" if longitude >= 0 else "W"
            alat, alon = abs(latitude), abs(longitude)
            lat_deg = int(alat)
            lat_min = (alat - lat_deg) * 60.0
            lon_deg = int(alon)
            lon_min = (alon - lon_deg) * 60.0
            lat_str = f"{lat_deg:02d}{lat_min:07.4f}"
            lon_str = f"{lon_deg:03d}{lon_min:07.4f}"
            now_dt = datetime.now(timezone.utc)
            t_str = now_dt.strftime("%H%M%S.00")
            d_str = now_dt.strftime("%d%m%y")
            spd_kt = (speed or 0.0) / 1.852
            base_sent = f"GNRMC,{t_str},A,{lat_str},{ns},{lon_str},{ew},{spd_kt:.2f},0.0,{d_str},,,A"
            csum = 0
            for ch in base_sent:
                csum ^= ord(ch)
            payload = f"${base_sent}*{csum:02X}"
        elif is_simulation:
            payload = json.dumps({
                "type": "SIMULATION_TELEMETRY",
                "imei": imei or str(device_id),
                "protocol": protocol,
                "lat": round(latitude, 6) if latitude is not None else None,
                "lon": round(longitude, 6) if longitude is not None else None,
                "speed_kmh": speed,
                "validation": validation_status,
                "source": source
            })
        else:
            payload = f"$RAW_TELEMETRY,ID={device_id},PROTO={protocol},LAT={latitude},LON={longitude},SPD={speed}"

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO packets
    (
        device_id, imei, protocol, packet_type, validation_status,
        latitude, longitude, speed, timestamp, detection_time_ms,
        source, source_type, is_simulation, fix_valid, satellites_used, hdop, altitude, payload
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        device_id,
        imei,
        protocol,
        packet_type,
        validation_status,
        latitude,
        longitude,
        speed,
        timestamp,
        detection_time_ms,
        source,
        source_type,
        is_simulation,
        fix_valid,
        satellites_used,
        hdop,
        altitude,
        payload
    ))

    packet_id = cursor.lastrowid

    # Mirror to packet_history for forensic retention
    cursor.execute("""
    INSERT INTO packet_history
    (
        packet_id, device_id, imei, protocol, packet_type, validation_status,
        latitude, longitude, speed, timestamp, detection_time_ms,
        source, source_type, is_simulation, fix_valid, satellites_used, hdop, altitude, payload
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        packet_id,
        device_id,
        imei,
        protocol,
        packet_type,
        validation_status,
        latitude,
        longitude,
        speed,
        timestamp,
        detection_time_ms,
        source,
        source_type,
        is_simulation,
        fix_valid,
        satellites_used,
        hdop,
        altitude,
        payload
    ))

    connection.commit()
    connection.close()

    return packet_id


# ============================================================
# SECURITY EVENT FUNCTION
# ============================================================

def log_security_event(
    packet_id,
    imei,
    attack_type,
    severity,
    description,
    action
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO security_events
    (
        packet_id,
        imei,
        attack_type,
        severity,
        description,
        action,
        status
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        packet_id,
        imei,
        attack_type,
        severity,
        description,
        action,
        "DETECTED"
    ))

    event_id = cursor.lastrowid

    # Mirror to security_events_history
    cursor.execute("""
    INSERT INTO security_events_history
    (
        event_id,
        packet_id,
        imei,
        attack_type,
        severity,
        description,
        action,
        status
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        event_id,
        packet_id,
        imei,
        attack_type,
        severity,
        description,
        action,
        "DETECTED"
    ))

    connection.commit()
    connection.close()

    return event_id


# ============================================================
# REPLAY DETECTION
# ============================================================

def create_fingerprint(
    imei,
    protocol,
    packet_type,
    packet_data
):
    data = (
        str(imei)
        + str(protocol)
        + str(packet_type)
        + str(packet_data)
    )

    return hashlib.sha256(
        data.encode()
    ).hexdigest()


def is_replay(fingerprint):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT COUNT(*)
    FROM packet_fingerprints
    WHERE fingerprint = ?
    """, (fingerprint,))

    count = cursor.fetchone()[0]
    connection.close()

    return count > 0


def store_fingerprint(
    fingerprint,
    imei
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO packet_fingerprints
    (fingerprint, imei)
    VALUES (?, ?)
    """, (
        fingerprint,
        str(imei)
    ))

    connection.commit()
    connection.close()


# ============================================================
# SIMULATION RUNS & AUDIT LOGS
# ============================================================

def log_simulation_run(
    scenario_id: str,
    scenario_name: str,
    input_summary: str,
    expected_detection: str,
    observed_detection: str,
    severity: str,
    mitigation_action: str,
    pass_fail: str,
    evidence_details: str
) -> int:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO simulation_runs
    (
        scenario_id, scenario_name, input_summary,
        expected_detection, observed_detection, severity,
        mitigation_action, pass_fail, evidence_details, is_simulation
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (
        scenario_id,
        scenario_name,
        input_summary,
        expected_detection,
        observed_detection,
        severity,
        mitigation_action,
        pass_fail,
        evidence_details
    ))

    run_id = cursor.lastrowid
    connection.commit()
    connection.close()

    # Log to audit trail
    log_audit_action(
        "ATTACK_SIMULATION_EXECUTED",
        f"Scenario {scenario_id}: {scenario_name} Result={pass_fail} Detection={observed_detection}"
    )

    return run_id


def get_simulation_runs(limit: int = 50) -> List[Dict[str, Any]]:
    connection = get_connection()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
    SELECT * FROM simulation_runs
    ORDER BY run_id DESC
    LIMIT ?
    """, (limit,))

    rows = [dict(r) for r in cursor.fetchall()]
    connection.close()
    return rows


def clear_simulation_runs() -> int:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("DELETE FROM simulation_runs")
    count = cursor.rowcount
    connection.commit()
    connection.close()

    log_audit_action("ATTACK_SIMULATION_CLEARED", f"Cleared {count} active simulation runs")
    return count


def log_audit_action(action_type: str, details: str, actor: str = "SYSTEM"):
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("""
        INSERT INTO audit_logs (action_type, details, actor)
        VALUES (?, ?, ?)
        """, (action_type, details, actor))
        connection.commit()
        connection.close()
    except Exception as exc:
        print("Audit logging error:", exc)


def get_sdr_captures() -> List[Dict[str, Any]]:
    connection = get_connection()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM sdr_captures ORDER BY capture_id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    connection.close()
    return rows


# ============================================================
# MAIN PACKET PROCESSING (ORIGINAL BACKWARD COMPATIBLE)
# ============================================================

def process_packet(
    device_id,
    imei,
    protocol,
    packet_type,
    packet_data
):
    print("Checking incoming packet...")
    print("IMEI:", imei)

    # --------------------------------------------------------
    # STEP 1: CHECK IMEI
    # --------------------------------------------------------

    if not check_imei(imei):
        print("UNAUTHORIZED IMEI DETECTED")
        print("Packet rejected.")

        packet_id = add_packet(
            device_id,
            imei,
            protocol,
            packet_type,
            "INVALID",
            source_type="REJECTED"
        )

        log_security_event(
            packet_id,
            imei,
            "IMEI Spoofing",
            "HIGH",
            f"Unauthorized IMEI detected: {imei}",
            "REJECT"
        )

        print("Security event logged.")
        return False

    print("Device AUTHORIZED")

    # --------------------------------------------------------
    # STEP 2: CREATE PACKET FINGERPRINT
    # --------------------------------------------------------

    fingerprint = create_fingerprint(
        imei,
        protocol,
        packet_type,
        packet_data
    )

    # --------------------------------------------------------
    # STEP 3: CHECK FOR REPLAY ATTACK
    # --------------------------------------------------------

    if is_replay(fingerprint):
        print("REPLAY ATTACK DETECTED")
        print("Packet rejected.")

        packet_id = add_packet(
            device_id,
            imei,
            protocol,
            packet_type,
            "INVALID",
            source_type="REPLAY"
        )

        log_security_event(
            packet_id,
            imei,
            "Replay Attack",
            "HIGH",
            "Previously received packet detected again (duplicate fingerprint)",
            "BLOCK"
        )

        print("Security event logged.")
        return False

    # --------------------------------------------------------
    # STEP 4: NEW PACKET
    # --------------------------------------------------------

    store_fingerprint(
        fingerprint,
        imei
    )

    packet_id = add_packet(
        device_id,
        imei,
        protocol,
        packet_type,
        "VALID"
    )

    print("New packet accepted and stored.")
    return True


# ============================================================
# PROGRAM START
# ============================================================

if __name__ == "__main__":
    create_tables()
    print("TrackGuard database module ready.")
