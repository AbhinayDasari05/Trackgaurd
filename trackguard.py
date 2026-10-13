import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "parser"))
sys.path.insert(0, os.path.join(BASE_DIR, "database"))
sys.path.insert(0, os.path.join(BASE_DIR, "detection"))
sys.path.insert(0, os.path.join(BASE_DIR, "alerts"))
sys.path.insert(0, os.path.join(BASE_DIR, "mitigation"))

from gt06_parser import parse_gt06_packet
from database import create_tables, process_packet
from detection import analyze_packet
from alerts import generate_alert, display_alert
from mitigation import apply_mitigation


print("=" * 60)
print("              TRACKGUARD")
print("       SECURE GPS MONITORING SYSTEM")
print("=" * 60)


print("\n[1] Initializing database...")
create_tables()
print("Database ready.")


print("\n[2] Receiving GT06 packet...")

raw_packet = (
    "IMEI:123456789012345 "
    "TYPE:LOCATION "
    "LAT:19.0760 "
    "LON:72.8777 "
    "SPEED:150 "
    "TIME:3003"
)

print("Raw packet received.")


print("\n[3] Parsing GT06 packet...")

packet = parse_gt06_packet(raw_packet)

print("IMEI:", packet["imei"])
print("Packet Type:", packet["packet_type"])
print("Latitude:", packet["latitude"])
print("Longitude:", packet["longitude"])
print("Speed:", packet["speed"])
print("Timestamp:", packet["timestamp"])


accepted = process_packet(
    1,
    packet["imei"],
    packet["protocol"],
    packet["packet_type"],
    (
        str(packet["latitude"])
        + ","
        + str(packet["longitude"])
        + ","
        + str(packet["speed"])
        + ","
        + str(packet["timestamp"])
    )
)


if not accepted:
    print("\nPacket rejected by security engine.")
    sys.exit()


print("\n[5] Running security detection...")

packet_for_detection = {
    "imei": packet["imei"],
    "latitude": packet["latitude"],
    "longitude": packet["longitude"],
    "previous_latitude": 17.3852,
    "previous_longitude": 78.4869,
    "speed": packet["speed"]
}

detections = analyze_packet(packet_for_detection)


if detections:

    print("\n[6] Security anomalies detected.")

    for detection in detections:

        alert = generate_alert(
            detection["type"],
            detection["severity"],
            detection["description"],
            packet["imei"]
        )

        display_alert(alert)

        apply_mitigation(alert)

else:

    print("\n[6] No security anomalies detected.")


print("\n" + "=" * 60)
print("       TRACKGUARD PROCESSING COMPLETED")
print("=" * 60)

print("\nSystem status: OPERATIONAL")