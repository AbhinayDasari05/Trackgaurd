import serial
import time

PORT = "COM10"
BAUD = 38400

print(f"Opening {PORT} at {BAUD} baud...")
print("Press Ctrl+C to stop.")

try:
    with serial.Serial(PORT, BAUD, timeout=2) as gps:
        while True:
            line = gps.readline().decode("ascii", errors="replace").strip()
            if line:
                print(line)
except KeyboardInterrupt:
    print("\nStopped.")
except serial.SerialException as exc:
    print(f"Serial error: {exc}")
