import socket
import time

SERVER = "127.0.0.1"
PORT = 5006

packets = [
    "IMEI:123456789012345 TYPE:LOCATION LAT:18.5204 LON:73.8567 SPEED:60 TIME:7001",
    "IMEI:123456789012345 TYPE:LOCATION LAT:18.5210 LON:73.8570 SPEED:65 TIME:7002",
    "IMEI:123456789012345 TYPE:LOCATION LAT:18.5210 LON:73.8570 SPEED:65 TIME:7002",
    "IMEI:999999999999999 TYPE:LOCATION LAT:18.5210 LON:73.8570 SPEED:65 TIME:7003",
    "IMEI:123456789012345 TYPE:LOCATION LAT:18.5220 LON:73.8580 SPEED:150 TIME:7004",
    "IMEI:123456789012345 TYPE:LOCATION LAT:23.2599 LON:77.4126 SPEED:80 TIME:7005"
]

print("==============================================")
print("TRACKGUARD LIVE GPS SIMULATOR")
print("==============================================")

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((SERVER, PORT))

    print(f"Connected to {SERVER}:{PORT}")
    print()

    for i, packet in enumerate(packets, 1):
        print(f"Packet {i}")
        print(packet)
        print()

        sock.sendall((packet + "\n").encode())
        time.sleep(3)

    print("==============================================")
    print("Simulation completed")
    print("==============================================")

    sock.close()

except ConnectionRefusedError:
    print("ERROR: Live server is not running.")
    print("Start Terminal 1 first:")
    print("python3 live_server/server.py")
