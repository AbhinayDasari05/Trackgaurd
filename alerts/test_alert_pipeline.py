import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "detection"))
sys.path.insert(0, os.path.join(BASE_DIR, "alerts"))

from detection import analyze_packet
from alerts import generate_alert, display_alert


print("=" * 55)
print("       TRACKGUARD DETECTION -> ALERT TEST")
print("=" * 55)


# Simulated packet received from the GT06 parser

packet = {
    "imei": "123456789012345",
    "latitude": 18.5204,
    "longitude": 73.8567,
    "previous_latitude": 17.3852,
    "previous_longitude": 78.4869,
    "speed": 150
}


# Run detection

print("\nAnalyzing packet...")

detections = analyze_packet(packet)


# Convert detections into alerts

if detections:

    print("\nSuspicious activity detected.")

    for detection in detections:

        alert = generate_alert(
            detection["type"],
            detection["severity"],
            detection["description"],
            packet["imei"]
        )

        display_alert(alert)

else:

    print("\nNo suspicious activity detected.")


print("\n" + "=" * 55)
print("       ALERT PIPELINE TEST COMPLETED")
print("=" * 55)
