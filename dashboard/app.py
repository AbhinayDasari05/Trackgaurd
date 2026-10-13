from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    send_from_directory,
    Response
)
import sqlite3
import os
import sys
import subprocess
import re
import math
import time
import random
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename

# ============================================================
# TRACKGUARD DASHBOARD & INTEGRATED BACKEND
# ============================================================

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "core"))
sys.path.insert(0, str(BASE_DIR / "hardware"))
sys.path.insert(0, str(BASE_DIR / "simulator"))

DB_PATH = str(BASE_DIR / "trackguard.db")
CAPTURE_DIR = str(BASE_DIR / "captures")
os.makedirs(CAPTURE_DIR, exist_ok=True)

from core.tshark_util import find_tshark, get_tshark_version
from hardware.gnss_serial import gnss_hardware, auto_detect_serial_port
from simulator.attack_lab import run_scenario, run_all_scenarios, GLOBAL_SPOOFING_LOCATIONS
from database.database import (
    create_tables,
    add_packet,
    log_security_event,
    get_simulation_runs,
    clear_simulation_runs,
    get_sdr_captures,
    log_audit_action
)
from dashboard.attack_report import (
    generate_attack_report_html,
    generate_attack_report_csv,
    fetch_all_attack_events
)

_last_hw_fix = {}

def log_hardware_telemetry(pdata):
    global _last_hw_fix
    try:
        lat = pdata.get("latitude")
        lon = pdata.get("longitude")
        speed = pdata.get("speed", 0.0) or 0.0
        alt = pdata.get("altitude")
        timestamp = pdata.get("timestamp") or int(time.time())
        sats = pdata.get("satellites_used", 0) or 0
        hdop = pdata.get("hdop")

        anomalies = []

        # 1. Kinematic Velocity Check
        if speed > 180.0:
            anomalies.append({
                "type": "Speed Anomaly",
                "severity": "HIGH",
                "desc": f"Hardware GNSS receiver reported implausible velocity: {speed:.1f} km/h (exceeds 180 km/h threshold)",
                "action": "RATE_LIMIT_VELOCITY"
            })

        # 2. Geodesic Location Jump Check
        if lat is not None and lon is not None and "lat" in _last_hw_fix and "lon" in _last_hw_fix:
            elapsed = max(1.0, timestamp - _last_hw_fix.get("timestamp", timestamp))
            dist_km = calculate_distance(_last_hw_fix["lat"], _last_hw_fix["lon"], lat, lon)
            implied_spd = (dist_km / (elapsed / 3600.0)) if elapsed > 0 else 0.0
            if dist_km > 50.0 and implied_spd > 300.0:
                anomalies.append({
                    "type": "Location Jump",
                    "severity": "HIGH",
                    "desc": f"Hardware GPS fix jumped {dist_km:.1f} km in {elapsed:.0f}s (implied {implied_spd:.0f} km/h)",
                    "action": "QUARANTINE_POSITION"
                })

        # 3. Altitude Spoofing Check
        if alt is not None and _last_hw_fix.get("alt") is not None:
            alt_diff = abs(alt - _last_hw_fix["alt"])
            if alt_diff > 500.0:
                anomalies.append({
                    "type": "Altitude Spoofing",
                    "severity": "HIGH",
                    "desc": f"Hardware vertical axis manipulation: altitude shifted {alt_diff:.1f}m abruptly",
                    "action": "LOCK_ALTITUDE_BASELINE"
                })

        # 4. GNSS Fix Semantic Contradiction / Jamming
        if pdata.get("fix_valid") and sats == 0:
            anomalies.append({
                "type": "GNSS Fix Contradiction",
                "severity": "HIGH",
                "desc": "Hardware reported valid navigation fix with 0 satellites tracked",
                "action": "REJECT_FIX"
            })
        elif hdop is not None and hdop > 10.0:
            anomalies.append({
                "type": "GNSS Signal Loss / Jamming",
                "severity": "MEDIUM",
                "desc": f"Severe precision dilution (HDOP {hdop}): potential satellite jamming or RF distortion",
                "action": "FLAG_DEGRADED_SIGNAL"
            })

        is_anomaly = len(anomalies) > 0
        val_status = "ANOMALY_DETECTED" if is_anomaly else "NORMAL"

        pkt_id = add_packet(
            device_id=pdata["device_id"],
            imei=pdata["device_id"],
            protocol="NMEA",
            packet_type="RMC",
            validation_status=val_status,
            latitude=lat,
            longitude=lon,
            speed=speed,
            timestamp=timestamp,
            source="neo_m9n",
            source_type="HARDWARE",
            is_simulation=0,
            fix_valid=1 if pdata.get("fix_valid") else 0,
            satellites_used=sats,
            hdop=hdop,
            altitude=alt,
            payload=pdata.get("raw_sentence")
        )

        if is_anomaly:
            for a in anomalies:
                log_security_event(
                    packet_id=pkt_id,
                    imei=pdata["device_id"],
                    attack_type=a["type"],
                    severity=a["severity"],
                    description=a["desc"],
                    action=a["action"]
                )
        else:
            if lat is not None and lon is not None:
                _last_hw_fix = {"lat": lat, "lon": lon, "timestamp": timestamp, "alt": alt}

    except Exception as exc:
        print("Hardware telemetry logging error:", exc)

gnss_hardware.on_packet_callback = log_hardware_telemetry

# Start hardware receiver service in background
try:
    gnss_hardware.start()
except Exception as exc:
    print("Failed to start hardware GNSS service:", exc)

# ============================================================
# CONFIGURATION
# ============================================================

ALLOWED_EXTENSIONS = {
    ".pcap",
    ".pcapng",
    ".cap"
}

SPEED_LIMIT = 100.0
LOCATION_JUMP_LIMIT_KM = 50.0


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# DATABASE DATA
# ============================================================

def get_dashboard_data():
    conn = get_connection()
    cursor = conn.cursor()

    # Ensure all tables exist
    create_tables()

    # Devices
    devices = cursor.execute(
        """
        SELECT device_id, imei, device_name, status, registered_at
        FROM devices
        ORDER BY device_id DESC
        """
    ).fetchall()

    # Live / Recent Packets
    packets = cursor.execute(
        """
        SELECT
            packet_id, device_id, imei, protocol, packet_type,
            received_at, validation_status, latitude, longitude,
            speed, timestamp, detection_time_ms,
            source, source_type, is_simulation, fix_valid, satellites_used, hdop, altitude, payload
        FROM packets
        ORDER BY packet_id DESC
        LIMIT 100
        """
    ).fetchall()

    # Live Security Events
    events = cursor.execute(
        """
        SELECT
            event_id, packet_id, imei, attack_type, severity,
            description, action, event_time, status
        FROM security_events
        ORDER BY event_id DESC
        LIMIT 100
        """
    ).fetchall()

    # History Packets
    history_packets = cursor.execute(
        """
        SELECT
            history_id, packet_id, device_id, imei, protocol, packet_type,
            received_at, validation_status, latitude, longitude,
            speed, timestamp, detection_time_ms, archived_at,
            source, source_type, is_simulation, payload
        FROM packet_history
        ORDER BY history_id DESC
        LIMIT 200
        """
    ).fetchall()

    # History Events
    history_events = cursor.execute(
        """
        SELECT
            history_event_id, event_id, packet_id, imei, attack_type,
            severity, description, action, event_time, status, archived_at
        FROM security_events_history
        ORDER BY history_event_id DESC
        LIMIT 200
        """
    ).fetchall()

    # Attack Summary Counts across both live events and historical archives
    attack_counts = cursor.execute(
        """
        SELECT attack_type, COUNT(*) as count
        FROM (
            SELECT attack_type FROM security_events
            UNION ALL
            SELECT attack_type FROM security_events_history
        )
        WHERE attack_type IS NOT NULL AND attack_type != ''
        GROUP BY attack_type
        ORDER BY count DESC
        """
    ).fetchall()

    # Counts
    total_packets = cursor.execute("SELECT COUNT(*) FROM packets").fetchone()[0]
    total_events = cursor.execute("SELECT COUNT(*) FROM security_events").fetchone()[0]
    detected_events = cursor.execute("SELECT COUNT(*) FROM security_events WHERE status = 'DETECTED'").fetchone()[0]
    normal_packets = cursor.execute("SELECT COUNT(*) FROM packets WHERE validation_status = 'NORMAL'").fetchone()[0]
    anomaly_packets = cursor.execute("SELECT COUNT(*) FROM packets WHERE validation_status = 'ANOMALY_DETECTED'").fetchone()[0]
    history_total_packets = cursor.execute("SELECT COUNT(*) FROM packet_history").fetchone()[0]
    history_total_events = cursor.execute("SELECT COUNT(*) FROM security_events_history").fetchone()[0]

    # Simulation runs
    simulation_runs = get_simulation_runs(limit=25)
    sdr_captures = get_sdr_captures()

    conn.close()

    return {
        "devices": devices,
        "packets": packets,
        "events": events,
        "history_packets": history_packets,
        "history_events": history_events,
        "attack_counts": attack_counts,
        "total_packets": total_packets,
        "total_events": total_events,
        "detected_events": detected_events,
        "normal_packets": normal_packets,
        "anomaly_packets": anomaly_packets,
        "history_total_packets": history_total_packets,
        "history_total_events": history_total_events,
        "simulation_runs": simulation_runs,
        "sdr_captures": sdr_captures,
        "gnss_status": gnss_hardware.get_status(),
        "tshark_version": get_tshark_version()
    }


# ============================================================
# PCAP FILES
# ============================================================

def get_pcap_files():
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    files = []
    for filename in sorted(os.listdir(CAPTURE_DIR)):
        filepath = os.path.join(CAPTURE_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        ext = os.path.splitext(filename)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            files.append({
                "name": filename,
                "size": os.path.getsize(filepath)
            })
    return files


def extract_pcap_packets(filepath):
    if not os.path.isfile(filepath):
        raise FileNotFoundError("PCAP file not found.")

    tshark_bin = find_tshark()
    if not tshark_bin:
        raise RuntimeError("TShark is not installed or not in PATH. Please install Wireshark to enable PCAP analysis.")

    count_command = [tshark_bin, "-r", filepath, "-T", "fields", "-e", "frame.number"]
    count_result = subprocess.run(count_command, capture_output=True, text=True, timeout=30)
    if count_result.returncode != 0:
        raise RuntimeError(count_result.stderr.strip() or "Error reading packet count")

    captured_packets = len([l for l in count_result.stdout.splitlines() if l.strip()])

    command = [tshark_bin, "-r", filepath, "-T", "fields", "-e", "frame.number", "-e", "data"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Error reading packet payloads")

    gps_packets = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        frame_number = parts[0]
        payload_hex = parts[1].strip()
        if not payload_hex:
            continue

        try:
            raw_bytes = bytes.fromhex(payload_hex)
            decoded = raw_bytes.decode("utf-8", errors="ignore").strip()
        except Exception:
            continue

        if not decoded:
            continue

        if "IMEI:" in decoded or "TYPE:" in decoded or "GPS" in decoded or "{" in decoded:
            gps_packets.append({
                "frame": frame_number,
                "payload": decoded
            })

    return {
        "captured_packets": captured_packets,
        "gps_packets": gps_packets
    }


def analyze_pcap_file(filepath):
    data = extract_pcap_packets(filepath)
    attacks = []
    normal = 0

    for item in data["gps_packets"]:
        payload = item["payload"]
        attack = None

        speed_match = re.search(r'"speed"\s*:\s*([0-9.]+)|SPEED[:=]\s*([0-9.]+)', payload)
        if speed_match:
            try:
                spd_val = speed_match.group(1) or speed_match.group(2)
                speed = float(spd_val)
                if speed > SPEED_LIMIT:
                    attack = "Speed Anomaly"
            except ValueError:
                pass

        lat_match = re.search(r'"latitude"\s*:\s*(-?[0-9.]+)|LAT[:=]\s*(-?[0-9.]+)', payload)
        lon_match = re.search(r'"longitude"\s*:\s*(-?[0-9.]+)|LON[:=]\s*(-?[0-9.]+)', payload)
        if not attack and lat_match and lon_match:
            try:
                lat_val = lat_match.group(1) or lat_match.group(2)
                lon_val = lon_match.group(1) or lon_match.group(2)
                latitude = float(lat_val)
                longitude = float(lon_val)
                base_lat, base_lon = 13.0827, 80.2707
                dist = calculate_distance(base_lat, base_lon, latitude, longitude)
                if dist > LOCATION_JUMP_LIMIT_KM:
                    attack = "Location Jump"
            except ValueError:
                pass

        if attack:
            attacks.append({
                "frame": item["frame"],
                "attack": attack,
                "payload": payload
            })
        else:
            normal += 1

    return {
        "captured_packets": data["captured_packets"],
        "gps_packets": len(data["gps_packets"]),
        "normal_packets": normal,
        "attacks": attacks
    }


def calculate_distance(lat1, lon1, lat2, lon2):
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
    return radius * c


# ============================================================
# ROUTES: MAIN DASHBOARD & WEB PAGES
# ============================================================

@app.route("/")
def dashboard():
    data = get_dashboard_data()
    pcap_files = get_pcap_files()
    return render_template(
        "dashboard.html",
        **data,
        pcap_files=pcap_files
    )


# ============================================================
# ROUTES: REST APIS
# ============================================================

@app.route("/api/dashboard")
def api_dashboard():
    data = get_dashboard_data()
    return jsonify({
        "total_packets": data["total_packets"],
        "total_events": data["total_events"],
        "detected_events": data["detected_events"],
        "normal_packets": data["normal_packets"],
        "anomaly_packets": data["anomaly_packets"],
        "gnss_status": data["gnss_status"]
    })


@app.route("/api/packets")
def api_packets():
    data = get_dashboard_data()
    return jsonify([dict(row) for row in data["packets"]])


@app.route("/api/packet/<int:packet_id>")
def api_packet_detail(packet_id):
    conn = get_connection()
    cursor = conn.cursor()
    pkt = cursor.execute("SELECT * FROM packets WHERE packet_id = ?", (packet_id,)).fetchone()
    if not pkt:
        pkt = cursor.execute("SELECT * FROM packet_history WHERE packet_id = ?", (packet_id,)).fetchone()
    if not pkt:
        conn.close()
        return jsonify({"error": "Packet not found", "packet_id": packet_id}), 404

    pkt_dict = dict(pkt)
    # Check for corresponding security event
    evt = cursor.execute(
        "SELECT * FROM security_events WHERE packet_id = ? ORDER BY event_id DESC LIMIT 1",
        (packet_id,)
    ).fetchone()
    if not evt:
        evt = cursor.execute(
            "SELECT * FROM security_events_history WHERE packet_id = ? ORDER BY history_event_id DESC LIMIT 1",
            (packet_id,)
        ).fetchone()

    conn.close()
    pkt_dict["security_event"] = dict(evt) if evt else None
    return jsonify(pkt_dict)


@app.route("/api/events")
def api_events():
    data = get_dashboard_data()
    return jsonify([dict(row) for row in data["events"]])


@app.route("/api/devices")
def api_devices():
    data = get_dashboard_data()
    return jsonify([dict(row) for row in data["devices"]])


@app.route("/api/history/packets")
def api_history_packets():
    data = get_dashboard_data()
    return jsonify([dict(row) for row in data["history_packets"]])


@app.route("/api/history/events")
def api_history_events():
    data = get_dashboard_data()
    return jsonify([dict(row) for row in data["history_events"]])


@app.route("/api/live-data")
def api_live_data():
    data = get_dashboard_data()
    packets = [dict(row) for row in data["packets"]]
    events = [dict(row) for row in data["events"]]
    history_packets = [dict(row) for row in data["history_packets"]]
    history_events = [dict(row) for row in data["history_events"]]
    attack_counts = [dict(row) for row in data["attack_counts"]]
    sim_runs = data["simulation_runs"]

    return jsonify({
        "total_packets": data["total_packets"],
        "total_events": data["total_events"],
        "detected_events": data["detected_events"],
        "normal_packets": data["normal_packets"],
        "anomaly_packets": data["anomaly_packets"],
        "history_total_packets": data["history_total_packets"],
        "history_total_events": data["history_total_events"],
        "packets": packets,
        "events": events,
        "history_packets": history_packets,
        "history_events": history_events,
        "attack_counts": attack_counts,
        "simulation_runs": sim_runs,
        "gnss_status": data["gnss_status"]
    })


# ============================================================
# ROUTES: REPORT VIEW & DOWNLOAD (LIVE ATTACKS & DETECTION)
# ============================================================

@app.route("/view-report")
def view_report():
    """Dynamically renders the live detected attacks & incident forensic report."""
    report_type = request.args.get("type", "attacks").lower()
    if report_type == "engineering":
        report_path = BASE_DIR / "dashboard" / "static" / "reports" / "TrackGuard_Comprehensive_Project_Report.html"
        if report_path.exists():
            return report_path.read_text(encoding="utf-8")

    # Generate live report of all registered & detected attacks from database
    hw_status = gnss_hardware.get_status()
    html_content = generate_attack_report_html(hw_status)
    return html_content


@app.route("/download-report")
def download_report():
    """Downloads the registered attacks report in CSV, JSON, or HTML format."""
    fmt = request.args.get("format", "html").lower()
    
    if fmt == "csv":
        csv_data = generate_attack_report_csv()
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=TrackGuard_Detected_Attacks.csv"}
        )
    elif fmt == "json":
        data = fetch_all_attack_events()
        return jsonify(data)
    elif fmt in ("md", "markdown"):
        reports_dir = BASE_DIR / "dashboard" / "static" / "reports"
        filename = "TrackGuard_Comprehensive_Project_Report.md"
        return send_from_directory(
            directory=str(reports_dir),
            path=filename,
            as_attachment=True,
            download_name=filename
        )
    else:
        hw_status = gnss_hardware.get_status()
        html_data = generate_attack_report_html(hw_status)
        return Response(
            html_data,
            mimetype="text/html",
            headers={"Content-Disposition": "attachment;filename=TrackGuard_Detected_Attacks_Report.html"}
        )


# ============================================================
# ROUTES: HARDWARE GNSS RECEIVER INTEGRATION
# ============================================================

@app.route("/api/gnss/status")
def api_gnss_status():
    """Returns thread-safe real-time status of physical GNSS hardware."""
    return jsonify(gnss_hardware.get_status())


@app.route("/api/gnss/config", methods=["POST"])
def api_gnss_config():
    """Allows dynamic reconfiguration of GNSS serial port and baud rate."""
    payload = request.get_json(silent=True) or request.form
    new_port = payload.get("port")
    new_baud = payload.get("baud")

    if not new_port:
        return jsonify({"status": "error", "message": "Missing 'port' parameter"}), 400

    baud_int = int(new_baud) if new_baud else 38400
    updated_status = gnss_hardware.reconnect(new_port, baud_int)
    log_audit_action("HARDWARE_PORT_RECONFIGURED", f"Port set to {new_port} at {baud_int} baud")

    return jsonify({
        "status": "updated",
        "port": new_port,
        "baud": baud_int,
        "current_status": updated_status
    })


@app.route("/api/gnss/reconnect", methods=["POST", "GET"])
def api_gnss_reconnect():
    """Forces an immediate reconnect to GNSS receiver on given or auto-detected port."""
    payload = request.get_json(silent=True) or request.args or request.form or {}
    req_port = payload.get("port")
    req_baud = payload.get("baud")
    baud_int = int(req_baud) if req_baud else 38400

    if not req_port or str(req_port).strip().lower() in ("auto", "auto-detect", ""):
        req_port = auto_detect_serial_port() or "COM9"

    status = gnss_hardware.reconnect(port=req_port, baud=baud_int)
    log_audit_action("HARDWARE_RECONNECT", f"Reconnection requested for {req_port}")

    return jsonify({
        "status": "success",
        "port": req_port,
        "baud": baud_int,
        "gnss_status": status
    })


def get_random_spoofing_location():
    """Returns a randomly selected global target location for coordinate spoofing."""
    loc = random.choice(GLOBAL_SPOOFING_LOCATIONS)
    return loc, loc["name"]


@app.route("/api/hardware/simulate-attack", methods=["POST"])
def api_hardware_simulate_attack():
    """Injects a hardware-tagged GNSS anomaly directly into the active telemetry stream."""
    payload = request.get_json(silent=True) or request.args or request.form or {}
    attack_kind = payload.get("attack_type", "location_jump")

    hw_status = gnss_hardware.get_status()
    base_lat = hw_status.get("latitude") or 13.0827
    base_lon = hw_status.get("longitude") or 80.2707

    if attack_kind == "location_jump":
        loc, _ = get_random_spoofing_location()
        pkt_lat, pkt_lon = loc["lat"], loc["lon"]
        atk_name = "Location Jump"
        desc = f"Hardware receiver spoofed: abrupt {calculate_distance(base_lat, base_lon, pkt_lat, pkt_lon):.1f} km jump to {loc['name']}"
        action = "QUARANTINE_POSITION"
        speed = 85.0
        alt = hw_status.get("altitude_m") or 15.0
    elif attack_kind == "speed_surge":
        pkt_lat, pkt_lon = base_lat, base_lon
        atk_name = "Speed Anomaly"
        desc = "Hardware GNSS Doppler receiver reported implausible velocity surge: 285.4 km/h"
        action = "RATE_LIMIT_VELOCITY"
        speed = 285.4
        alt = hw_status.get("altitude_m") or 15.0
    elif attack_kind == "altitude_spoof":
        pkt_lat, pkt_lon = base_lat, base_lon
        atk_name = "Altitude Spoofing"
        desc = "Hardware vertical axis manipulation: impossible altitude shift to 8,450 m MSL"
        action = "LOCK_ALTITUDE_BASELINE"
        speed = 12.0
        alt = 8450.0
    elif attack_kind == "nmea_corruption":
        pkt_lat, pkt_lon = base_lat, base_lon
        atk_name = "NMEA Data Injection"
        desc = "Corrupted XOR checksum & malformed frame injected into hardware UART bus"
        action = "DROP_INVALID_FRAME"
        speed = 0.0
        alt = hw_status.get("altitude_m") or 15.0
    elif attack_kind == "jamming_loss":
        pkt_lat, pkt_lon = base_lat, base_lon
        atk_name = "GNSS Signal Loss / Jamming"
        desc = "Simulated carrier RF jamming: satellite tracking dropped to 0 and C/N0 collapsed"
        action = "DEAD_RECKONING_FALLBACK"
        speed = 0.0
        alt = None
    elif attack_kind == "constellation_drift":
        pkt_lat = base_lat + 0.045
        pkt_lon = base_lon + 0.038
        atk_name = "Multi-Constellation Drift"
        desc = "Stealth creeping ephemeris drift across GPS/Galileo/BeiDou pseudorange solution"
        action = "KALMAN_FILTER_SANITY_CHECK"
        speed = 25.0
        alt = hw_status.get("altitude_m") or 15.0
    elif attack_kind == "timestamp_manipulation":
        pkt_lat, pkt_lon = base_lat, base_lon
        atk_name = "Timestamp Manipulation"
        desc = "Chronological inversion: hardware receiver UTC time stepped backward by 300 seconds"
        action = "REJECT_OUT_OF_ORDER"
        speed = 0.0
        alt = hw_status.get("altitude_m") or 15.0
    else:
        pkt_lat, pkt_lon = base_lat, base_lon
        atk_name = "GNSS Fix Contradiction"
        desc = "Fabricated Autonomous Fix flag with 0 satellites tracked"
        action = "REJECT_FIX"
        speed = 0.0
        alt = None

    pkt_id = add_packet(
        device_id="trackguard-gnss-01",
        imei="trackguard-gnss-01",
        protocol="NMEA",
        packet_type="HARDWARE_INJECTED_ATTACK",
        validation_status="ANOMALY_DETECTED",
        latitude=pkt_lat,
        longitude=pkt_lon,
        speed=speed,
        timestamp=int(time.time()),
        source="neo_m9n",
        source_type="HARDWARE",
        is_simulation=0,
        fix_valid=1 if attack_kind != "jamming_loss" else 0,
        satellites_used=8 if attack_kind != "jamming_loss" else 0,
        altitude=alt,
        payload=f"$GNRMC_INJECTED_ATTACK,TYPE={atk_name},LAT={pkt_lat},LON={pkt_lon},SPD={speed}*TEST"
    )

    log_security_event(
        packet_id=pkt_id,
        imei="trackguard-gnss-01",
        attack_type=atk_name,
        severity="HIGH",
        description=desc,
        action=action
    )

    return jsonify({
        "status": "success",
        "attack_type": atk_name,
        "packet_id": pkt_id,
        "description": desc,
        "action": action,
        "target_coordinates": {"lat": pkt_lat, "lon": pkt_lon} if pkt_lat else None
    })


# ============================================================
# ROUTES: ATTACK SIMULATION & DETECTION LABORATORY
# ============================================================

@app.route("/api/simulation/locations")
def api_simulation_locations():
    """Returns list of global spoofing target locations available for simulation."""
    return jsonify({
        "status": "success",
        "count": len(GLOBAL_SPOOFING_LOCATIONS),
        "locations": GLOBAL_SPOOFING_LOCATIONS
    })


@app.route("/api/simulation/run/<scenario_id>", methods=["POST"])
def api_simulation_run(scenario_id):
    """Executes a specific attack laboratory simulation scenario, optionally with custom target location."""
    try:
        data = request.get_json(silent=True) or {}
        target_location = data.get("target_location")
        result = run_scenario(scenario_id, target_location=target_location)
        return jsonify({
            "status": "success",
            "result": result
        })
    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": str(exc)
        }), 400


@app.route("/api/simulation/run-all", methods=["POST"])
def api_simulation_run_all():
    """Executes all 12 attack laboratory simulation scenarios sequentially."""
    try:
        results = run_all_scenarios()
        return jsonify({
            "status": "success",
            "count": len(results),
            "results": results
        })
    except Exception as exc:
        return jsonify({
            "status": "error",
            "message": str(exc)
        }), 500


@app.route("/api/simulation/runs")
def api_simulation_runs():
    """Retrieves execution history of attack laboratory runs."""
    runs = get_simulation_runs(limit=50)
    return jsonify(runs)


@app.route("/api/simulation/clear", methods=["POST"])
def api_simulation_clear():
    """Clears active attack laboratory execution records."""
    cleared = clear_simulation_runs()
    return jsonify({
        "status": "cleared",
        "cleared_count": cleared
    })


# ============================================================
# ROUTES: SDR & FORENSICS
# ============================================================

@app.route("/api/sdr/status")
def api_sdr_status():
    """Returns ADALM-PLUTO SDR offline sample analysis and metadata."""
    captures = get_sdr_captures()
    return jsonify({
        "device": "ADALM-PLUTO SDR, Rev.C, AD9363A",
        "ip_address": "192.168.2.1",
        "captures": captures,
        "notice": "ADALM-PLUTO SDR capture was recorded with LO at 2.4 GHz. It has not established presence of GPS L1 (1575.42 MHz) signals. Nonzero I/Q samples are RF energy, not proof of GNSS signals."
    })


# ============================================================
# ROUTES: PCAP SCANNING & DOWNLOAD
# ============================================================

@app.route("/scan_pcap", methods=["POST"])
def scan_pcap():
    filename = request.form.get("filename")
    if not filename:
        return redirect(url_for("dashboard"))
    safe_filename = os.path.basename(filename)
    return redirect(url_for("analyze_pcap", filename=safe_filename))


@app.route("/analyze_pcap/<path:filename>")
def analyze_pcap(filename):
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(CAPTURE_DIR, safe_filename)

    if not os.path.isfile(filepath):
        return ("PCAP file not found.", 404)

    try:
        result = analyze_pcap_file(filepath)
        return render_template(
            "pcap_result.html",
            filename=safe_filename,
            result=result
        )
    except Exception as exc:
        return (
            f"<h1>PCAP Analysis Error</h1><p>{exc}</p><p><a href='/'>Back</a></p>",
            500
        )


@app.route("/pcap/<path:filename>")
def serve_pcap(filename):
    safe_filename = os.path.basename(filename)
    return send_from_directory(CAPTURE_DIR, safe_filename, as_attachment=False)


@app.route("/upload_pcap", methods=["POST"])
def upload_pcap():
    if "pcap_file" not in request.files:
        return redirect(url_for("dashboard"))

    file = request.files["pcap_file"]
    if not file.filename:
        return redirect(url_for("dashboard"))

    filename = secure_filename(file.filename)
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        return ("Invalid PCAP file type.", 400)

    filepath = os.path.join(CAPTURE_DIR, filename)
    file.save(filepath)

    return redirect(url_for("analyze_pcap", filename=filename))


# ============================================================
# ROUTES: HEALTH & SESSION CONTROLS
# ============================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "OK",
        "database": DB_PATH,
        "database_exists": os.path.exists(DB_PATH),
        "tshark_installed": find_tshark() is not None,
        "gnss_connected": gnss_hardware.connected
    })


@app.route("/clear", methods=["POST"])
def clear_data():
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO packet_history (
                packet_id, device_id, imei, protocol, packet_type,
                received_at, validation_status, latitude, longitude,
                speed, timestamp, detection_time_ms
            )
            SELECT
                p.packet_id, p.device_id, p.imei, p.protocol, p.packet_type,
                p.received_at, p.validation_status, p.latitude, p.longitude,
                p.speed, p.timestamp, p.detection_time_ms
            FROM packets p
            WHERE NOT EXISTS (
                SELECT 1 FROM packet_history ph
                WHERE ph.packet_id = p.packet_id AND ph.timestamp = p.timestamp
            )
            """
        )

        cursor.execute(
            """
            INSERT INTO security_events_history (
                event_id, packet_id, imei, attack_type, severity,
                description, action, event_time, status
            )
            SELECT
                e.event_id, e.packet_id, e.imei, e.attack_type, e.severity,
                e.description, e.action, e.event_time, e.status
            FROM security_events e
            WHERE NOT EXISTS (
                SELECT 1 FROM security_events_history eh
                WHERE eh.event_id = e.event_id
            )
            """
        )

        cursor.execute("DELETE FROM security_events")
        events_deleted = cursor.rowcount
        cursor.execute("DELETE FROM packets")
        packets_deleted = cursor.rowcount
        cursor.execute("DELETE FROM packet_fingerprints")
        fingerprints_deleted = cursor.rowcount

        cursor.execute(
            "DELETE FROM sqlite_sequence "
            "WHERE name IN ('packets','security_events','packet_fingerprints')"
        )

        connection.commit()
        connection.close()

        log_audit_action("SESSION_CLEARED", f"Archived and cleared {packets_deleted} live packets")

        return jsonify({
            "status": "cleared",
            "packets_deleted": packets_deleted,
            "events_deleted": events_deleted,
            "fingerprints_deleted": fingerprints_deleted
        })

    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/clear-history", methods=["POST"])
def clear_history():
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        cursor.execute("DELETE FROM security_events_history")
        events_deleted = cursor.rowcount
        cursor.execute("DELETE FROM packet_history")
        packets_deleted = cursor.rowcount

        cursor.execute(
            "DELETE FROM sqlite_sequence "
            "WHERE name IN ('packet_history','security_events_history')"
        )

        connection.commit()
        connection.close()

        log_audit_action("HISTORY_PURGED", f"Permanently purged {packets_deleted} historical packets")

        return jsonify({
            "status": "cleared",
            "history_packets_deleted": packets_deleted,
            "history_events_deleted": events_deleted
        })

    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


# ============================================================
# START DASHBOARD
# ============================================================

def get_available_port(default_port=5001):
    import socket
    for p in [default_port, 5000, 5050, 8080]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return default_port


if __name__ == "__main__":
    target_port = int(os.environ.get("PORT", "5001"))
    chosen_port = get_available_port(target_port)

    print("=" * 60)
    print("       TRACKGUARD UNIFIED SECURITY DASHBOARD")
    print("=" * 60)
    print("Database  :", DB_PATH)
    print("Dashboard :", f"http://127.0.0.1:{chosen_port}")
    print("GNSS Port :", gnss_hardware.active_port or "Scanning...")
    print("TShark    :", find_tshark() or "Not detected")
    print("=" * 60)

    app.run(
        host="127.0.0.1",
        port=chosen_port,
        debug=False
    )
