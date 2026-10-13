import sqlite3
import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "trackguard.db")


def get_data():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    devices = cursor.execute(
        """
        SELECT device_id, imei, device_name, status, registered_at
        FROM devices
        ORDER BY device_id DESC
        """
    ).fetchall()

    packets = cursor.execute(
        """
        SELECT packet_id, device_id, imei, protocol,
               packet_type, received_at, validation_status
        FROM packets
        ORDER BY packet_id DESC
        LIMIT 10
        """
    ).fetchall()

    events = cursor.execute(
        """
        SELECT event_id, packet_id, imei, attack_type,
               severity, description, action,
               event_time, status
        FROM security_events
        ORDER BY event_id DESC
        LIMIT 10
        """
    ).fetchall()

    conn.close()

    return devices, packets, events


def display_dashboard():

    devices, packets, events = get_data()

    print("\n" + "=" * 70)
    print("                    TRACKGUARD DASHBOARD")
    print("=" * 70)

    print("\nDEVICE STATUS")
    print("-" * 70)

    if devices:

        for device in devices:

            print("Device ID :", device[0])
            print("IMEI      :", device[1])
            print("Name      :", device[2])
            print("Status    :", device[3])
            print("Registered:", device[4])
            print("-" * 70)

    else:

        print("No devices found.")


    print("\nRECENT PACKETS")
    print("-" * 70)

    if packets:

        for packet in packets:

            print(
                "Packet ID:", packet[0],
                "| IMEI:", packet[2],
                "| Type:", packet[4],
                "| Status:", packet[6]
            )

    else:

        print("No packets found.")


    print("\nSECURITY EVENTS")
    print("-" * 70)

    if events:

        for event in events:

            print(
                "Event ID:", event[0],
                "| IMEI:", event[2],
                "| Attack:", event[3],
                "| Severity:", event[4],
                "| Action:", event[6],
                "| Status:", event[8]
            )

    else:

        print("No security events found.")


    print("\n" + "=" * 70)
    print("                    DASHBOARD ACTIVE")
    print("=" * 70)


if __name__ == "__main__":

    display_dashboard()