import re


def parse_gt06_packet(raw_packet):

    """
    Basic TrackGuard GT06 packet parser.

    This development version extracts:
    - IMEI
    - protocol
    - packet type
    - latitude
    - longitude
    - speed
    - timestamp

    The parser is currently designed for simulated
    GT06 data. Real GT06 packet decoding will be
    integrated when the physical tracker is available.
    """

    packet = raw_packet.strip()

    result = {
        "imei": None,
        "protocol": "GT06",
        "packet_type": None,
        "latitude": None,
        "longitude": None,
        "speed": None,
        "timestamp": None,
        "raw_data": packet
    }

    # ---------------------------------------------------------
    # Extract IMEI
    # ---------------------------------------------------------

    imei_match = re.search(
        r"IMEI[:=]\s*(\d{15})",
        packet,
        re.IGNORECASE
    )

    if imei_match:
        result["imei"] = imei_match.group(1)

    # ---------------------------------------------------------
    # Packet type
    # ---------------------------------------------------------

    type_match = re.search(
        r"TYPE[:=]\s*([A-Za-z_]+)",
        packet,
        re.IGNORECASE
    )

    if type_match:
        result["packet_type"] = type_match.group(1).upper()

    # ---------------------------------------------------------
    # Latitude
    # ---------------------------------------------------------

    lat_match = re.search(
        r"LAT[:=]\s*(-?\d+(?:\.\d+)?)",
        packet,
        re.IGNORECASE
    )

    if lat_match:
        result["latitude"] = float(lat_match.group(1))

    # ---------------------------------------------------------
    # Longitude
    # ---------------------------------------------------------

    lon_match = re.search(
        r"LON[:=]\s*(-?\d+(?:\.\d+)?)",
        packet,
        re.IGNORECASE
    )

    if lon_match:
        result["longitude"] = float(lon_match.group(1))

    # ---------------------------------------------------------
    # Speed
    # ---------------------------------------------------------

    speed_match = re.search(
        r"SPEED[:=]\s*(\d+(?:\.\d+)?)",
        packet,
        re.IGNORECASE
    )

    if speed_match:
        result["speed"] = float(speed_match.group(1))

    # ---------------------------------------------------------
    # Timestamp
    # ---------------------------------------------------------

    time_match = re.search(
        r"TIME[:=]\s*([^\s,]+)",
        packet,
        re.IGNORECASE
    )

    if time_match:
        result["timestamp"] = time_match.group(1)

    return result


if __name__ == "__main__":

    test_packet = (
        "IMEI:123456789012345 "
        "TYPE:LOCATION "
        "LAT:17.3852 "
        "LON:78.4869 "
        "SPEED:45 "
        "TIME:2001"
    )

    parsed = parse_gt06_packet(test_packet)

    print("=== GT06 PARSER TEST ===")
    print("IMEI:", parsed["imei"])
    print("Protocol:", parsed["protocol"])
    print("Packet Type:", parsed["packet_type"])
    print("Latitude:", parsed["latitude"])
    print("Longitude:", parsed["longitude"])
    print("Speed:", parsed["speed"])
    print("Timestamp:", parsed["timestamp"])