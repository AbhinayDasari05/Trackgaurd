import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay_detector import create_fingerprint, is_replay, store_fingerprint


def test_packet(imei, protocol, packet_type, packet_data):

    fingerprint = create_fingerprint(
        imei,
        protocol,
        packet_type,
        packet_data
    )

    if is_replay(fingerprint):

        print("[WARNING] REPLAY ATTACK DETECTED")
        print("Packet rejected.")

    else:

        print("New packet detected.")
        store_fingerprint(fingerprint, imei)
        print("Packet accepted and fingerprint stored.")


print("=== TRACKGUARD REPLAY DETECTION TEST ===\n")


# Packet A
print("Testing Packet A:")
test_packet(
    "123456789012345",
    "GT06",
    "LOCATION",
    "LAT:17.3850,LON:78.4867,TIME:1001"
)

print()


# Packet B - different packet data
print("Testing Packet B:")
test_packet(
    "123456789012345",
    "GT06",
    "LOCATION",
    "LAT:17.3851,LON:78.4868,TIME:1002"
)

print()


# Packet A again - exact duplicate
print("Testing Packet A again:")
test_packet(
    "123456789012345",
    "GT06",
    "LOCATION",
    "LAT:17.3850,LON:78.4867,TIME:1001"
)