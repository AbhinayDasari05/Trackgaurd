import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import process_packet

AUTHORIZED_IMEI = "123456789012345"
UNAUTHORIZED_IMEI = "999999999999999"

print("=" * 50)
print("       TRACKGUARD SECURITY TEST")
print("=" * 50)

print("\n[TEST 1] Authorized New Packet")

process_packet(
    1,
    AUTHORIZED_IMEI,
    "GT06",
    "LOCATION",
    "LAT:17.3852,LON:78.4869,TIME:2001"
)

print("\n[TEST 2] Replay Attack")

process_packet(
    1,
    AUTHORIZED_IMEI,
    "GT06",
    "LOCATION",
    "LAT:17.3852,LON:78.4869,TIME:2001"
)

print("\n[TEST 3] Unauthorized Device")

process_packet(
    1,
    UNAUTHORIZED_IMEI,
    "GT06",
    "LOCATION",
    "LAT:18.0000,LON:79.0000,TIME:2002"
)

print("\n" + "=" * 50)
print("       TEST COMPLETED")
print("=" * 50)
