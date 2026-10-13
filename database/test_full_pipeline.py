import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "parser"))
sys.path.insert(0, os.path.join(BASE_DIR, "database"))

from gt06_parser import parse_gt06_packet
from database import process_packet


print("=" * 60)
print("        TRACKGUARD FULL PIPELINE TEST")
print("=" * 60)


# ---------------------------------------------------------
# SIMULATED GT06 PACKET
# ---------------------------------------------------------

raw_packet = (
    "IMEI:123456789012345 "
    "TYPE:LOCATION "
    "LAT:17.3852 "
    "LON:78.4869 "
    "SPEED:45 "
    "TIME:2001"
)


# ---------------------------------------------------------
# STEP 1: PARSE PACKET
# ---------------------------------------------------------

print("\n[1] Parsing GT06 packet...")

parsed = parse_gt06_packet(raw_packet)

print("IMEI:", parsed["imei"])
print("Packet Type:", parsed["packet_type"])
print("Latitude:", parsed["latitude"])
print("Longitude:", parsed["longitude"])
print("Speed:", parsed["speed"])
print("Timestamp:", parsed["timestamp"])


# ---------------------------------------------------------
# STEP 2: SECURITY PROCESSING
# ---------------------------------------------------------

print("\n[2] Sending packet to security engine...")

process_packet(
    1,
    parsed["imei"],
    parsed["protocol"],
    parsed["packet_type"],
    parsed["raw_data"]
)


print("\n" + "=" * 60)
print("        PIPELINE TEST COMPLETED")
print("=" * 60)