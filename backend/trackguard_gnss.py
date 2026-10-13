
import json
from datetime import datetime, timezone

import serial
import pynmea2

PORT = "COM10"
BAUD = 38400

latest = {
    "timestamp_utc": None,
    "latitude": None,
    "longitude": None,
    "speed_kmh": None,
    "fix_valid": False,
    "source": "NEO-M9N"
}

print("TRACK GUARD - LIVE GNSS MONITOR")
print(f"Connecting to {PORT} at {BAUD} baud...")
print("Press Ctrl+C to stop.\n")

try:
    with serial.Serial(PORT, BAUD, timeout=2) as gps:
        while True:
            raw = gps.readline().decode(
                "ascii", errors="ignore"
            ).strip()

            if not raw.startswith(("$GNRMC", "$GPRMC")):
                continue

            try:
                msg = pynmea2.parse(raw)

                latest["timestamp_utc"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                latest["fix_valid"] = msg.status == "A"

                if latest["fix_valid"]:
                    latest["latitude"] = msg.latitude
                    latest["longitude"] = msg.longitude

                    knots = float(msg.spd_over_grnd or 0)
                    latest["speed_kmh"] = round(
                        knots * 1.852, 2
                    )

                print(json.dumps(latest, indent=2))
                print("-" * 40)

            except (pynmea2.ParseError, ValueError) as exc:
                print("Message parse error:", exc)

except KeyboardInterrupt:
    print("\nTrack Guard GNSS monitor stopped.")

except serial.SerialException as exc:
    print("Serial connection error:", exc)
