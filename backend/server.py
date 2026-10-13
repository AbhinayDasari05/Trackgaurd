
from flask import Flask, jsonify, request
from threading import Thread, Lock
from datetime import datetime, timezone
from math import radians, sin, cos, asin, sqrt
import random
import serial
import pynmea2
import time

app = Flask(__name__)

SERIAL_PORT = "COM9"
BAUD_RATE = 38400

STALE_SECONDS = 5
MAX_SPEED_KMH = 180
MAX_JUMP_SPEED_KMH = 220

lock = Lock()

gps_state = {
    "connected": False,
    "fix_valid": False,
    "latitude": None,
    "longitude": None,
    "speed_kmh": None,
    "satellites_used": None,
    "last_update": None,
    "error": None,
    "alerts": [],
    "mode": "live",
}

demo_state = {
    "active": False,
    "latitude": None,
    "longitude": None,
    "label": None,
    "started_at": None,
    "run_id": 0,
}

previous_position = None

# Clearly identified, application-only test destinations.
# These coordinates are not sent to the physical GNSS receiver.
TEST_LOCATIONS = [
    # Asia & Middle East
    {"label": "New Delhi demo", "latitude": 28.6139, "longitude": 77.2090},
    {"label": "Mumbai demo", "latitude": 19.0760, "longitude": 72.8777},
    {"label": "Bengaluru demo", "latitude": 12.9716, "longitude": 77.5946},
    {"label": "Hyderabad demo", "latitude": 17.3850, "longitude": 78.4867},
    {"label": "Kolkata demo", "latitude": 22.5726, "longitude": 88.3639},
    {"label": "Jaipur demo", "latitude": 26.9124, "longitude": 75.7873},
    {"label": "Pune demo", "latitude": 18.5204, "longitude": 73.8567},
    {"label": "Kochi demo", "latitude": 9.9312, "longitude": 76.2673},
    {"label": "Dubai, UAE demo", "latitude": 25.2048, "longitude": 55.2708},
    {"label": "Singapore demo", "latitude": 1.3521, "longitude": 103.8198},
    {"label": "Tokyo, Japan demo", "latitude": 35.6762, "longitude": 139.6503},
    {"label": "Seoul, South Korea demo", "latitude": 37.5665, "longitude": 126.9780},
    # Europe
    {"label": "London, UK demo", "latitude": 51.5074, "longitude": -0.1278},
    {"label": "Paris, France demo", "latitude": 48.8566, "longitude": 2.3522},
    {"label": "Berlin, Germany demo", "latitude": 52.5200, "longitude": 13.4050},
    {"label": "Geneva, Switzerland demo", "latitude": 46.2044, "longitude": 6.1432},
    {"label": "Reykjavik, Iceland demo", "latitude": 64.1466, "longitude": -21.9426},
    # Americas
    {"label": "New York City, USA demo", "latitude": 40.7128, "longitude": -74.0060},
    {"label": "San Francisco, USA demo", "latitude": 37.7749, "longitude": -122.4194},
    {"label": "Toronto, Canada demo", "latitude": 43.6532, "longitude": -79.3832},
    {"label": "Rio de Janeiro, Brazil demo", "latitude": -22.9068, "longitude": -43.1729},
    # Oceania & Africa
    {"label": "Sydney, Australia demo", "latitude": -33.8688, "longitude": 151.2093},
    {"label": "Cairo, Egypt demo", "latitude": 30.0444, "longitude": 31.2357},
    {"label": "Cape Town, South Africa demo", "latitude": -33.9249, "longitude": 18.4241},
]


def utc_now():
    return datetime.now(timezone.utc)


def add_alert(code, message):
    now = utc_now().isoformat()
    with lock:
        if not any(a["code"] == code for a in gps_state["alerts"]):
            gps_state["alerts"].append({
                "code": code,
                "message": message,
                "time": now,
            })
        gps_state["alerts"] = gps_state["alerts"][-20:]


def clear_alert(code):
    with lock:
        gps_state["alerts"] = [
            a for a in gps_state["alerts"] if a["code"] != code
        ]


def distance_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(
        radians, (lat1, lon1, lat2, lon2)
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )
    return 6371.0 * 2 * asin(sqrt(min(1.0, a)))


def inspect_position(lat, lon, speed_kmh, timestamp):
    global previous_position

    if speed_kmh is not None and speed_kmh > MAX_SPEED_KMH:
        add_alert(
            "HIGH_SPEED",
            f"Reported speed exceeds {MAX_SPEED_KMH} km/h"
        )
    else:
        clear_alert("HIGH_SPEED")

    if previous_position is not None:
        old_lat, old_lon, old_time = previous_position
        elapsed = (timestamp - old_time).total_seconds()

        if elapsed > 0:
            distance = distance_km(old_lat, old_lon, lat, lon)
            implied_speed = distance / (elapsed / 3600)

            if implied_speed > MAX_JUMP_SPEED_KMH:
                add_alert(
                    "POSITION_JUMP",
                    "Live GNSS position changed faster than the configured threshold"
                )
            else:
                clear_alert("POSITION_JUMP")

    previous_position = (lat, lon, timestamp)


def read_gnss():
    while True:
        try:
            with serial.Serial(
                SERIAL_PORT, BAUD_RATE, timeout=2
            ) as ser:
                with lock:
                    gps_state["connected"] = True
                    gps_state["error"] = None

                while True:
                    raw = ser.readline().decode(
                        "ascii", errors="ignore"
                    ).strip()

                    if not raw.startswith("$") or "*" not in raw:
                        continue

                    try:
                        msg = pynmea2.parse(raw, check=True)
                    except (pynmea2.ParseError, ValueError):
                        continue

                    if msg.sentence_type == "GGA":
                        try:
                            satellites = int(msg.num_sats or 0)
                            quality = int(msg.gps_qual or 0)
                        except (ValueError, TypeError):
                            continue

                        with lock:
                            gps_state["satellites_used"] = satellites

                        # GGA provides fix-quality information.
                        if quality == 0:
                            add_alert(
                                "INVALID_FIX",
                                "Live GNSS receiver reports no position fix"
                            )
                        else:
                            clear_alert("INVALID_FIX")

                    elif msg.sentence_type == "RMC":
                        valid = getattr(msg, "status", "V") == "A"
                        now = utc_now()

                        with lock:
                            gps_state["fix_valid"] = valid
                            gps_state["last_update"] = now.isoformat()

                            if valid:
                                lat = float(msg.latitude)
                                lon = float(msg.longitude)
                                speed = round(
                                    float(msg.spd_over_grnd or 0) * 1.852,
                                    2
                                )

                                gps_state["latitude"] = lat
                                gps_state["longitude"] = lon
                                gps_state["speed_kmh"] = speed
                            else:
                                gps_state["latitude"] = None
                                gps_state["longitude"] = None
                                gps_state["speed_kmh"] = None

                        if valid:
                            inspect_position(lat, lon, speed, now)
                        else:
                            add_alert(
                                "INVALID_FIX",
                                "Live GNSS receiver reports invalid position"
                            )

        except (serial.SerialException, OSError) as exc:
            with lock:
                gps_state["connected"] = False
                gps_state["fix_valid"] = False
                gps_state["error"] = str(exc)

            time.sleep(3)


@app.get("/")
def home():
    return """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Track Guard</title>
<style>
body {
    margin: 0; padding: 24px;
    background: #101827; color: #e8eef8;
    font-family: Arial, sans-serif;
}
main { max-width: 1000px; margin: auto; }
h1 { margin-bottom: 4px; }
.sub { color: #aab8cc; margin-bottom: 24px; }
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit,minmax(210px,1fr));
    gap: 14px;
}
.card {
    background: #1c293c; padding: 18px;
    border: 1px solid #34445c; border-radius: 12px;
}
.label { color: #aab8cc; font-size: 13px; }
.value { font-size: 22px; font-weight: bold; margin-top: 10px; }
button {
    border: 0; border-radius: 8px; padding: 11px 15px;
    margin: 5px 5px 5px 0; cursor: pointer; font-weight: bold;
}
.start { background: #69e0b0; color: #10251f; }
.stop { background: #ffb4a8; color: #35130f; }
.secondary { background: #354761; color: white; }
.notice { color: #ffd68a; margin: 14px 0; }
#alerts { padding-left: 20px; }
.alert { margin: 8px 0; }
a { color: #8ecbff; }
</style>
</head>
<body>
<main>
<h1>Track Guard</h1>
<div class="sub">Live GNSS telemetry and controlled location demo</div>

<div class="grid">
  <section class="card">
    <div class="label">Receiver connection</div>
    <div class="value" id="connected">Checking...</div>
  </section>
  <section class="card">
    <div class="label">Live GNSS fix</div>
    <div class="value" id="fix">Checking...</div>
  </section>
  <section class="card">
    <div class="label">Satellites used</div>
    <div class="value" id="satellites">--</div>
  </section>
  <section class="card">
    <div class="label">Live speed</div>
    <div class="value" id="speed">--</div>
  </section>
</div>

<h2>Displayed location</h2>
<section class="card">
  <div class="label">Display source</div>
  <div class="value" id="source">Live GNSS</div>
  <p id="location">Waiting for coordinates...</p>
  <p id="demoLabel"></p>
  <p class="notice">
    Demo locations are simulated application data and do not alter
    the physical receiver or transmit radio signals.
  </p>
  <button class="start" onclick="startDemo()">Start randomized demo</button>
  <button class="stop" onclick="stopDemo()">Return to live location</button>
  <button class="secondary" onclick="refreshStatus()">Refresh</button>
  <p><a id="mapLink" target="_blank" rel="noopener">Open displayed location in map</a></p>
</section>

<h2>Alerts</h2>
<section class="card">
  <ul id="alerts"><li>No alerts loaded yet.</li></ul>
</section>
<p class="sub">API: <a href="/api/status">/api/status</a></p>
</main>

<script>
async function refreshStatus() {
    try {
        const response = await fetch('/api/status', {cache: 'no-store'});
        const s = await response.json();

        document.getElementById('connected').textContent =
            s.connected ? 'Connected' : 'Disconnected';
        document.getElementById('fix').textContent =
            s.fix_valid ? 'Valid' : 'No valid fix';
        document.getElementById('satellites').textContent =
            s.satellites_used ?? '--';
        document.getElementById('speed').textContent =
            s.speed_kmh == null ? '--' : s.speed_kmh + ' km/h';

        const displayed = s.displayed_location;
        document.getElementById('source').textContent =
            displayed.source === 'simulated'
                ? 'SIMULATED DEMO LOCATION'
                : 'LIVE GNSS LOCATION';

        if (displayed.latitude != null && displayed.longitude != null) {
            document.getElementById('location').textContent =
                'Latitude: ' + Number(displayed.latitude).toFixed(6) +
                ' | Longitude: ' + Number(displayed.longitude).toFixed(6);
            document.getElementById('mapLink').href =
                'https://www.openstreetmap.org/?mlat=' +
                encodeURIComponent(displayed.latitude) +
                '&mlon=' + encodeURIComponent(displayed.longitude) +
                '#map=12/' + encodeURIComponent(displayed.latitude) +
                '/' + encodeURIComponent(displayed.longitude);
        } else {
            document.getElementById('location').textContent =
                'No coordinates available yet.';
            document.getElementById('mapLink').removeAttribute('href');
        }

        document.getElementById('demoLabel').textContent =
            displayed.label || '';

        const list = document.getElementById('alerts');
        list.replaceChildren();

        if (!s.alerts || s.alerts.length === 0) {
            const li = document.createElement('li');
            li.textContent = 'No active alerts';
            list.appendChild(li);
        } else {
            s.alerts.forEach(a => {
                const li = document.createElement('li');
                li.className = 'alert';
                li.textContent = '[' + a.code + '] ' + a.message;
                list.appendChild(li);
            });
        }
    } catch (e) {
        document.getElementById('connected').textContent =
            'API unavailable';
    }
}

async function startDemo() {
    const response = await fetch('/api/demo/start', {method: 'POST'});
    const result = await response.json();
    if (!response.ok) {
        alert(result.error || 'Could not start demo');
        return;
    }
    await refreshStatus();
}

async function stopDemo() {
    const response = await fetch('/api/demo/stop', {method: 'POST'});
    await response.json();
    await refreshStatus();
}

refreshStatus();
setInterval(refreshStatus, 1500);
</script>
</body>
</html>
"""


@app.get("/api/status")
def status():
    with lock:
        live = dict(gps_state)
        live["alerts"] = list(gps_state["alerts"])
        demo = dict(demo_state)

    if live["last_update"]:
        age = (
            utc_now() - datetime.fromisoformat(live["last_update"])
        ).total_seconds()

        if age > STALE_SECONDS:
            live["alerts"].append({
                "code": "STALE_DATA",
                "message": (
                    f"No RMC update for more than {STALE_SECONDS} seconds"
                ),
                "time": utc_now().isoformat(),
            })

    if demo["active"]:
        displayed = {
            "source": "simulated",
            "latitude": demo["latitude"],
            "longitude": demo["longitude"],
            "label": demo["label"],
        }
    else:
        displayed = {
            "source": "live",
            "latitude": live["latitude"],
            "longitude": live["longitude"],
            "label": "Live NEO-M9N receiver",
        }

    live["displayed_location"] = displayed
    live["demo"] = demo
    return jsonify(live)


@app.post("/api/demo/start")
def start_demo():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"error": "Local access only"}), 403

    with lock:
        previous_label = demo_state["label"]
        choices = [
            location for location in TEST_LOCATIONS
            if location["label"] != previous_label
        ]
        selected = random.choice(choices or TEST_LOCATIONS)

        demo_state.update({
            "active": True,
            "latitude": selected["latitude"],
            "longitude": selected["longitude"],
            "label": selected["label"],
            "started_at": utc_now().isoformat(),
            "run_id": demo_state["run_id"] + 1,
        })
        result = dict(demo_state)

    return jsonify({
        "ok": True,
        "message": "Randomized simulated location selected",
        "demo": result,
    })


@app.post("/api/demo/stop")
def stop_demo():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"error": "Local access only"}), 403

    with lock:
        demo_state["active"] = False
        result = dict(demo_state)

    return jsonify({
        "ok": True,
        "message": "Display returned to live GNSS location",
        "demo": result,
    })


@app.post("/api/simulate")
def simulate():
    # Local defensive software tests only.
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"error": "Local access only"}), 403

    payload = request.get_json(silent=True) or {}
    scenario = payload.get("scenario")

    scenarios = {
        "invalid_fix": (
            "SIM_INVALID_FIX",
            "Simulation: receiver reports invalid fix",
        ),
        "high_speed": (
            "SIM_HIGH_SPEED",
            "Simulation: reported speed exceeds test threshold",
        ),
        "position_jump": (
            "SIM_POSITION_JUMP",
            "Simulation: implausible position jump detected",
        ),
        "stale_data": (
            "SIM_STALE_DATA",
            "Simulation: GNSS updates have stopped",
        ),
    }

    if scenario == "clear":
        with lock:
            gps_state["alerts"] = [
                a for a in gps_state["alerts"]
                if not a["code"].startswith("SIM_")
            ]
        return jsonify({"ok": True, "alerts": gps_state["alerts"]})

    if scenario not in scenarios:
        return jsonify({
            "error": (
                "Use invalid_fix, high_speed, position_jump, "
                "stale_data, or clear"
            )
        }), 400

    code, message = scenarios[scenario]
    now = utc_now().isoformat()

    with lock:
        if not any(a["code"] == code for a in gps_state["alerts"]):
            gps_state["alerts"].append({
                "code": code,
                "message": message,
                "time": now,
            })
        gps_state["alerts"] = gps_state["alerts"][-20:]
        result = list(gps_state["alerts"])

    return jsonify({"ok": True, "alerts": result})


if __name__ == "__main__":
    Thread(target=read_gnss, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False)

