import sys
import os
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "parser"))
sys.path.insert(0, os.path.join(BASE_DIR, "database"))
sys.path.insert(0, os.path.join(BASE_DIR, "detection"))
sys.path.insert(0, os.path.join(BASE_DIR, "alerts"))
sys.path.insert(0, os.path.join(BASE_DIR, "mitigation"))
sys.path.insert(0, os.path.join(BASE_DIR, "core"))

from gt06_parser import parse_gt06_packet
from database import create_tables, process_packet
from detection import analyze_packet
from alerts import generate_alert, display_alert
from mitigation import apply_mitigation
from tshark_util import find_tshark

PCAP_FILE = os.path.join(BASE_DIR, "captures", "trackguard_demo.pcap")


def extract_packets():
    tshark_bin = find_tshark()
    if not tshark_bin:
        print("\n[WARNING] TShark executable not found.")
        print("Please ensure Wireshark/TShark is installed and added to PATH or TSHARK_PATH env var.")
        return []

    if not os.path.isfile(PCAP_FILE):
        print(f"\n[WARNING] PCAP file not found: {PCAP_FILE}")
        return []

    try:
        result = subprocess.run(
            [tshark_bin, "-r", PCAP_FILE, "-T", "fields", "-e", "data"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print("TShark execution error:", e)
        return []

    packets = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            packet = bytes.fromhex(line).decode("ascii")
            packets.append(packet)
        except (ValueError, UnicodeDecodeError):
            continue

    return packets


def main():
    print("=" * 70)
    print("          TRACKGUARD PCAP SECURITY DEMONSTRATION")
    print("=" * 70)

    print("\n[1] Initializing database...")
    create_tables()
    print("Database ready.")

    print("\n[2] Reading PCAP file...")
    print("File:", PCAP_FILE)

    packets = extract_packets()
    print("Packets extracted:", len(packets))

    for number, raw_packet in enumerate(packets, start=1):
        print("\n" + "=" * 70)
        print(f"                         PACKET {number}")
        print("=" * 70)

        print("\n[3] Raw packet extracted from PCAP:")
        print(raw_packet)

        print("\n[4] Parsing GT06 packet...")
        try:
            packet = parse_gt06_packet(raw_packet)
        except Exception as error:
            print("Packet parsing failed:", error)
            continue

        print("IMEI:", packet["imei"])
        print("Packet Type:", packet["packet_type"])
        print("Latitude:", packet["latitude"])
        print("Longitude:", packet["longitude"])
        print("Speed:", packet["speed"])
        print("Timestamp:", packet["timestamp"])

        packet_data = (
            str(packet["latitude"]) + "," +
            str(packet["longitude"]) + "," +
            str(packet["speed"]) + "," +
            str(packet["timestamp"])
        )

        print("\n[5] Security validation...")
        accepted = process_packet(
            1,
            packet["imei"],
            packet["protocol"],
            packet["packet_type"],
            packet_data
        )

        if not accepted:
            print("\nPacket rejected by security engine.")
            continue

        print("\nPacket accepted.")

        print("\n[6] Running security detection...")
        packet_for_detection = {
            "imei": packet["imei"],
            "latitude": packet["latitude"],
            "longitude": packet["longitude"],
            "previous_latitude": 18.5204,
            "previous_longitude": 73.8567,
            "speed": packet["speed"]
        }

        detections = analyze_packet(packet_for_detection)

        if detections:
            print("\n[7] Security anomalies detected.")
            for detection in detections:
                print("\n----------------------------------------")
                print("Attack:", detection["type"])
                print("Severity:", detection["severity"])
                print("Description:", detection["description"])
                print("----------------------------------------")

                alert = generate_alert(
                    detection["type"],
                    detection["severity"],
                    detection["description"],
                    packet["imei"]
                )

                display_alert(alert)
                apply_mitigation(alert)
        else:
            print("\n[7] No security anomalies detected.")

    print("\n" + "=" * 70)
    print("       TRACKGUARD PCAP DEMONSTRATION COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()
