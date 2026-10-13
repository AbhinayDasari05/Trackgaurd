from database import process_packet

print("Testing unauthorized GT06 packet...\n")

process_packet(
    1,
    "999999999999999",
    "GT06",
    "LOCATION"
)