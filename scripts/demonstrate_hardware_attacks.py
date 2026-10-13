"""
TrackGuard Hardware Attack Demonstration CLI Tool
Author: TrackGuard Cyber-Physical Security Suite
Usage:
    python scripts/demonstrate_hardware_attacks.py [OPTIONS]

Options:
    --attack <type>   Inject a single attack:
                      location_jump, speed_surge, altitude_spoof,
                      nmea_corruption, jamming_loss, constellation_drift,
                      timestamp_manipulation
    --demo-all        Run an automated 7-step presentation demonstration cycle.
    --interactive     Launch an interactive menu for live demonstrations.
    --api <url>       Dashboard base URL (default: http://localhost:5001)
"""

import sys
import time
import json
import argparse
import urllib.request
import urllib.error

DEFAULT_URL = "http://localhost:5001"

ATTACK_TYPES = [
    {
        "id": "location_jump",
        "name": "Location Jump (Geodesic Teleportation)",
        "desc": "Simulates 3,300+ km instantaneous spoofing jump (e.g., Chennai -> Doha / London)",
        "vector": "Geodesic Haversine Delta > 50 km / 2s",
        "mitigation": "QUARANTINE_POSITION"
    },
    {
        "id": "speed_surge",
        "name": "Speed Anomaly (Doppler Velocity Surge)",
        "desc": "Simulates impossible kinetic surge to 285.4 km/h",
        "vector": "Kinematic Velocity > 180 km/h Threshold",
        "mitigation": "RATE_LIMIT_VELOCITY"
    },
    {
        "id": "altitude_spoof",
        "name": "Altitude Spoofing (Vertical Axis Jump)",
        "desc": "Simulates vertical manipulation: elevation jumps abruptly to 8,450 m MSL",
        "vector": "Vertical Delta > 500 m / Implausible Altitude",
        "mitigation": "LOCK_ALTITUDE_BASELINE"
    },
    {
        "id": "nmea_corruption",
        "name": "NMEA Data Injection (Corrupted Checksum)",
        "desc": "Injects malformed sentence & corrupted 8-bit XOR checksum into hardware UART stream",
        "vector": "UART Bus Protocol Tampering",
        "mitigation": "DROP_INVALID_FRAME"
    },
    {
        "id": "jamming_loss",
        "name": "GNSS Jamming / Signal Loss (RF Blackout)",
        "desc": "Simulates RF carrier blackout: satellites drop to 0, carrier-to-noise collapses",
        "vector": "RF Physical Layer Denial of Service",
        "mitigation": "DEAD_RECKONING_FALLBACK"
    },
    {
        "id": "constellation_drift",
        "name": "Multi-Constellation Drift (Selective Spoof)",
        "desc": "Simulates selective drift between GPS and GLONASS pseudorange solutions (> 0.05 deg)",
        "vector": "Inter-Constellation Divergence",
        "mitigation": "KALMAN_FILTER_SANITY_CHECK"
    },
    {
        "id": "timestamp_manipulation",
        "name": "Timestamp Inversion (Temporal Rewind)",
        "desc": "Inverts chronological epoch: steps UTC time backward by 300 seconds",
        "vector": "Temporal Monotonicity Breach",
        "mitigation": "REJECT_OUT_OF_ORDER"
    }
]


def send_attack(api_url: str, attack_type: str):
    endpoint = f"{api_url.rstrip('/')}/api/hardware/simulate-attack"
    payload = json.dumps({"attack_type": attack_type}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data
    except urllib.error.URLError as e:
        print(f"\n[!] Error connecting to TrackGuard at {endpoint}: {e}")
        print("    Ensure the dashboard is running (python dashboard/app.py).")
        return None


def print_attack_result(result: dict):
    if not result:
        return
    print("\n" + "="*60)
    print("  TRACKGUARD HARDWARE DEFENSE ENGINE: ANOMALY INTERCEPTED")
    print("="*60)
    print(f"  [+] Attack Category    : {result.get('attack_type')}")
    print(f"  [+] Security Action    : {result.get('action')}")
    print(f"  [+] Packet ID Logged   : #{result.get('packet_id')}")
    print(f"  [+] Forensic Details   : {result.get('description')}")
    coords = result.get('target_coordinates', {})
    if coords:
        print(f"  [+] Target Coordinates : Lat {coords.get('lat')}, Lon {coords.get('lon')}")
    print("  [+] Dashboard UI Status: Updated in Real-Time (Map & Attack Counts)")
    print("="*60 + "\n")


def run_interactive_menu(api_url: str):
    while True:
        print("\n" + "="*65)
        print("   TRACKGUARD HARDWARE ATTACK DEMONSTRATION CONSOLE")
        print("="*65)
        print("  Select an attack to inject directly into the live hardware pipeline:\n")
        for i, atk in enumerate(ATTACK_TYPES, 1):
            print(f"  [{i}] {atk['name']}")
            print(f"      Threat: {atk['desc']}")
        print("\n  [8] Run Complete Automated 7-Step Attack Cycle")
        print("  [0] Exit Demonstration Console")
        print("-"*65)
        
        choice = input("\nSelect Option [0-8]: ").strip()
        if choice == "0":
            print("\nExiting. Stay secure!\n")
            break
        elif choice == "8":
            run_demo_all(api_url)
        elif choice in [str(i) for i in range(1, len(ATTACK_TYPES) + 1)]:
            idx = int(choice) - 1
            selected = ATTACK_TYPES[idx]
            print(f"\n[*] Injecting {selected['name']}...")
            res = send_attack(api_url, selected["id"])
            print_attack_result(res)
            input("Press Enter to continue...")
        else:
            print("\n[!] Invalid selection. Please choose 0-8.")


def run_demo_all(api_url: str):
    print("\n" + "#"*65)
    print("  LAUNCHING FULL HARDWARE ATTACK DEMONSTRATION SEQUENCE (7 ATTACKS)")
    print("#"*65)
    
    for i, atk in enumerate(ATTACK_TYPES, 1):
        print(f"\n[Step {i}/7] Injecting: {atk['name']}...")
        print(f"         Vector: {atk['vector']}")
        res = send_attack(api_url, atk["id"])
        print_attack_result(res)
        if i < len(ATTACK_TYPES):
            print("  Pausing 3 seconds for dashboard observation...")
            time.sleep(3.0)
            
    print("\n" + "#"*65)
    print("  DEMONSTRATION CYCLE COMPLETED SUCCESSFULLY!")
    print("  All 7 attacks were detected, mitigated, and recorded into the database.")
    print("#"*65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="TrackGuard Hardware Attack Injection Tool")
    parser.add_argument("--attack", choices=[a["id"] for a in ATTACK_TYPES], help="Single attack type to inject")
    parser.add_argument("--demo-all", action="store_true", help="Run automated 7-step presentation demonstration")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive demonstration menu")
    parser.add_argument("--api", default=DEFAULT_URL, help=f"TrackGuard API base URL (default: {DEFAULT_URL})")
    
    args = parser.parse_args()
    
    if args.attack:
        print(f"\n[*] Injecting hardware attack: {args.attack}...")
        res = send_attack(args.api, args.attack)
        print_attack_result(res)
    elif args.demo_all:
        run_demo_all(args.api)
    else:
        run_interactive_menu(args.api)


if __name__ == "__main__":
    main()
