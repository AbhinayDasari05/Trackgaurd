import socket
import json
import time
import sys
import os

# ============================================================
# TRACKGUARD GPS ATTACK SIMULATOR
# ============================================================

SERVER_IP = os.environ.get("TRACKGUARD_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("TRACKGUARD_PORT", "5006"))
DEVICE_ID = "TG001"


def send_packet(sock, latitude, longitude, speed, timestamp, device_id=DEVICE_ID):
    packet = {
        "device_id": device_id,
        "latitude": latitude,
        "longitude": longitude,
        "speed": speed,
        "timestamp": timestamp,
        "source": "gps_simulator",
        "source_type": "SIMULATION",
        "simulation": True,
        "is_simulation": 1,
        "fix_valid": True,
        "satellites_used": 10
    }

    message = json.dumps(packet) + "\n"
    sock.sendall(message.encode("utf-8"))

    print()
    print("Sent simulated packet:")
    print("----------------------------------------")
    print("Device     :", device_id)
    print("Source Type: SIMULATION (synthetic)")
    print("Latitude   :", latitude)
    print("Longitude  :", longitude)
    print("Speed      :", speed)
    print("Timestamp  :", timestamp)
    print("----------------------------------------")


def connect():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"Connecting to TrackGuard server ({SERVER_IP}:{SERVER_PORT})...")
    sock.connect((SERVER_IP, SERVER_PORT))
    print("Connected to TrackGuard server.")
    return sock


def normal_test(sock):
    print()
    print("==========================================")
    print("       NORMAL TRAFFIC TEST")
    print("==========================================")

    base_time = int(time.time())
    packets = [
        {"latitude": 13.0827, "longitude": 80.2707, "speed": 50},
        {"latitude": 13.0828, "longitude": 80.2708, "speed": 55},
        {"latitude": 13.0829, "longitude": 80.2709, "speed": 48}
    ]

    for i, packet in enumerate(packets):
        send_packet(
            sock,
            packet["latitude"],
            packet["longitude"],
            packet["speed"],
            base_time + i
        )
        time.sleep(1)


def speed_attack(sock):
    print()
    print("==========================================")
    print("       SPEED ANOMALY ATTACK")
    print("==========================================")

    timestamp = int(time.time())
    send_packet(
        sock,
        13.0830,
        80.2710,
        150,
        timestamp
    )


import random

GLOBAL_JUMP_TARGETS = [
    {"name": "New Delhi, India", "lat": 28.6139, "lon": 77.2090},
    {"name": "Mumbai, India", "lat": 19.0760, "lon": 72.8777},
    {"name": "Bhopal, India", "lat": 23.2599, "lon": 77.4126},
    {"name": "Tokyo, Japan", "lat": 35.6762, "lon": 139.6503},
    {"name": "Singapore", "lat": 1.3521, "lon": 103.8198},
    {"name": "Dubai, UAE", "lat": 25.2048, "lon": 55.2708},
    {"name": "London, UK", "lat": 51.5074, "lon": -0.1278},
    {"name": "Paris, France", "lat": 48.8566, "lon": 2.3522},
    {"name": "Berlin, Germany", "lat": 52.5200, "lon": 13.4050},
    {"name": "New York City, USA", "lat": 40.7128, "lon": -74.0060},
    {"name": "San Francisco, USA", "lat": 37.7749, "lon": -122.4194},
    {"name": "Rio de Janeiro, Brazil", "lat": -22.9068, "lon": -43.1729},
    {"name": "Cape Town, South Africa", "lat": -33.9249, "lon": 18.4241},
    {"name": "Sydney, Australia", "lat": -33.8688, "lon": 151.2093}
]


def location_jump_attack(sock):
    print()
    print("==========================================")
    print("       LOCATION JUMP ATTACK (GLOBAL)")
    print("==========================================")

    target = random.choice(GLOBAL_JUMP_TARGETS)
    print(f"Injecting random global spoofed target: {target['name']} ({target['lat']}, {target['lon']})")

    timestamp = int(time.time())
    send_packet(
        sock,
        target["lat"],
        target["lon"],
        80,
        timestamp
    )


def replay_attack(sock):
    print()
    print("==========================================")
    print("       REPLAY ATTACK TEST")
    print("==========================================")

    timestamp = int(time.time())
    packet = {
        "device_id": DEVICE_ID,
        "latitude": 13.0827,
        "longitude": 80.2707,
        "speed": 50,
        "timestamp": timestamp,
        "source": "gps_simulator",
        "source_type": "SIMULATION",
        "simulation": True,
        "is_simulation": 1
    }

    message = json.dumps(packet) + "\n"

    print("Sending original packet...")
    sock.sendall(message.encode("utf-8"))
    time.sleep(1)

    print("Sending identical packet again (duplicate replay)...")
    sock.sendall(message.encode("utf-8"))


def imei_spoof_attack(sock):
    print()
    print("==========================================")
    print("       IMEI SPOOFING ATTACK TEST")
    print("==========================================")

    timestamp = int(time.time())
    spoofed_imei = "999999999999999"

    print("Sending packet claiming unauthorized device identity:")
    print("Spoofed Device:", spoofed_imei)

    send_packet(
        sock,
        13.0827,
        80.2707,
        50,
        timestamp,
        device_id=spoofed_imei
    )


def run_test(test_name):
    sock = connect()
    try:
        if test_name == "normal":
            normal_test(sock)
        elif test_name == "speed":
            normal_test(sock)
            time.sleep(1)
            speed_attack(sock)
        elif test_name == "location":
            normal_test(sock)
            time.sleep(1)
            location_jump_attack(sock)
        elif test_name == "replay":
            replay_attack(sock)
        elif test_name in ("spoof", "imei"):
            imei_spoof_attack(sock)
        elif test_name == "all":
            normal_test(sock)
            time.sleep(1)
            speed_attack(sock)
            time.sleep(1)
            location_jump_attack(sock)
            time.sleep(1)
            replay_attack(sock)
            time.sleep(1)
            imei_spoof_attack(sock)
        else:
            print("Unknown test. Available: normal, speed, location, replay, spoof, all")
    finally:
        time.sleep(1)
        sock.close()
        print("\nConnection closed.")


if __name__ == "__main__":
    print("==========================================")
    print("     TRACKGUARD GPS ATTACK SIMULATOR")
    print("==========================================")

    if len(sys.argv) < 2:
        print("\nUsage:")
        print("python simulator/gps_simulator.py normal")
        print("python simulator/gps_simulator.py speed")
        print("python simulator/gps_simulator.py location")
        print("python simulator/gps_simulator.py replay")
        print("python simulator/gps_simulator.py spoof")
        print("python simulator/gps_simulator.py all")
        sys.exit(0)

    test_name = sys.argv[1].lower()
    run_test(test_name)
    print("\nSimulation completed.")
