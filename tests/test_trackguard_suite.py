"""
TrackGuard Comprehensive Automated Test Suite
Implements and executes all 20 required verification points:
 1. NMEA latitude and longitude conversion
 2. Valid and invalid NMEA checksums
 3. GGA and RMC fix-status interpretation
 4. Serial disconnection and stale data
 5. Missing or malformed coordinates
 6. Haversine distance
 7. Implied-speed calculations
 8. Position jumps
 9. Speed anomalies
 10. Packet replay detection
 11. Unauthorized device rejection
 12. Timestamp inconsistencies
 13. NMEA injection test cases
 14. Simulation source labeling
 15. Database persistence
 16. API validation
 17. PCAP parsing errors
 18. Mitigation actions
 19. Regression of existing dashboard functionality
 20. Separation of real hardware data from synthetic test data
"""

import unittest
import os
import sys
import json
import sqlite3
import time
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


from hardware.gnss_serial import (
    nmea_to_decimal_degrees,
    validate_nmea_checksum,
    GNSSHardwareReceiver
)
from detection.detection import (
    calculate_distance,
    calculate_implied_speed,
    detect_speed_anomaly,
    detect_location_jump,
    detect_timestamp_anomaly,
    detect_fix_integrity_anomaly,
    analyze_packet,
    SPEED_LIMIT,
    LOCATION_JUMP_LIMIT_KM
)
from mitigation.mitigation import determine_action, apply_mitigation
from database.database import (
    create_tables,
    check_imei,
    is_replay,
    store_fingerprint,
    create_fingerprint,
    add_packet,
    log_security_event,
    get_connection,
    log_simulation_run
)
from core.telemetry import NormalizedTelemetry
from dashboard.app import app, extract_pcap_packets
from simulator.attack_lab import run_scenario


class TrackGuardTestSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        create_tables()

    # -------------------------------------------------------------
    # 1. NMEA latitude and longitude conversion
    # -------------------------------------------------------------
    def test_01_nmea_lat_lon_conversion(self):
        # 13 degrees, 15.65794 minutes North = 13 + 15.65794/60 = 13.2609657
        lat_dec = nmea_to_decimal_degrees("1315.65794", "N", is_longitude=False)
        self.assertIsNotNone(lat_dec)
        self.assertAlmostEqual(lat_dec, 13.2609657, places=5)

        # 080 degrees, 01.35745 minutes East = 80 + 1.35745/60 = 80.0226242
        lon_dec = nmea_to_decimal_degrees("08001.35745", "E", is_longitude=True)
        self.assertIsNotNone(lon_dec)
        self.assertAlmostEqual(lon_dec, 80.0226242, places=5)

        # Southern and Western hemisphere checks
        lat_south = nmea_to_decimal_degrees("1315.65794", "S", is_longitude=False)
        self.assertAlmostEqual(lat_south, -13.2609657, places=5)

        lon_west = nmea_to_decimal_degrees("08001.35745", "W", is_longitude=True)
        self.assertAlmostEqual(lon_west, -80.0226242, places=5)

    # -------------------------------------------------------------
    # 2. Valid and invalid NMEA checksums
    # -------------------------------------------------------------
    def test_02_nmea_checksums(self):
        valid_sentence = "$GNRMC,050434.00,A,1315.65794,N,08001.35745,E,0.046,,111026,,,D,V*16"
        self.assertTrue(validate_nmea_checksum(valid_sentence))

        invalid_sentence = "$GNRMC,050434.00,A,1315.65794,N,08001.35745,E,0.046,,111026,,,D,V*99"
        self.assertFalse(validate_nmea_checksum(invalid_sentence))

        empty_or_broken = "$BROKEN"
        self.assertFalse(validate_nmea_checksum(empty_or_broken))

    # -------------------------------------------------------------
    # 3. GGA and RMC fix-status interpretation
    # -------------------------------------------------------------
    def test_03_gga_rmc_fix_interpretation(self):
        receiver = GNSSHardwareReceiver(port="TEST")
        now = receiver.last_read_timestamp

        # GGA with quality 1 (SPS) and 10 sats -> Fix Valid
        gga_valid = "$GNGGA,050434.00,1315.65794,N,08001.35745,E,1,10,0.8,25.0,M,-86.8,M,,*67"
        receiver._parse_nmea_sentence(gga_valid, now)
        self.assertTrue(receiver.fix_valid)
        self.assertEqual(receiver.fix_quality, 1)
        self.assertEqual(receiver.satellites_used, 10)

        # GGA with quality 0 (No fix) -> Fix Invalid
        gga_invalid = "$GNGGA,050434.00,1315.65794,N,08001.35745,E,0,00,99.9,0.0,M,0.0,M,,0000*7A"
        receiver._parse_nmea_sentence(gga_invalid, now)
        self.assertFalse(receiver.fix_valid)
        self.assertEqual(receiver.fix_quality, 0)

        # RMC with status 'A' (Valid)
        rmc_valid = "$GNRMC,050434.00,A,1315.65794,N,08001.35745,E,0.046,,111026,,,D,V*16"
        receiver._parse_nmea_sentence(rmc_valid, now)
        self.assertTrue(receiver.fix_valid)

        # RMC with status 'V' (Warning / Invalid)
        rmc_invalid = "$GNRMC,050434.00,V,1315.65794,N,08001.35745,E,0.046,,111026,,,D,V*01"
        receiver._parse_nmea_sentence(rmc_invalid, now)
        self.assertFalse(receiver.fix_valid)

    # -------------------------------------------------------------
    # 4. Serial disconnection and stale data
    # -------------------------------------------------------------
    def test_04_serial_disconnection_and_stale_data(self):
        receiver = GNSSHardwareReceiver(port="TEST_PORT")
        status = receiver.get_status()
        # Initial state when disconnected
        self.assertFalse(status["connected"])
        self.assertEqual(status["fix_state"], "DISCONNECTED")
        # Ensure coordinates are None (no fabricated random positions)
        self.assertIsNone(status["latitude"])
        self.assertIsNone(status["longitude"])

    # -------------------------------------------------------------
    # 5. Missing or malformed coordinates
    # -------------------------------------------------------------
    def test_05_missing_malformed_coordinates(self):
        packet = NormalizedTelemetry(
            device_id="TEST01",
            source="test",
            source_type="HARDWARE",
            latitude=999.0,   # Out of bounds
            longitude=80.0,
            fix_valid=True
        )
        report = packet.validate()
        self.assertFalse(report["valid"])
        self.assertTrue(any("out of bounds" in e.lower() for e in report["errors"]))

    # -------------------------------------------------------------
    # 6. Haversine distance
    # -------------------------------------------------------------
    def test_06_haversine_distance(self):
        # Chennai to New Delhi is approx 1750-1770 km
        dist = calculate_distance(13.0827, 80.2707, 28.6139, 77.2090)
        self.assertGreater(dist, 1740.0)
        self.assertLess(dist, 1780.0)

        # Same point distance must be 0.0
        same_dist = calculate_distance(13.0827, 80.2707, 13.0827, 80.2707)
        self.assertAlmostEqual(same_dist, 0.0, places=5)

    # -------------------------------------------------------------
    # 7. Implied-speed calculations
    # -------------------------------------------------------------
    def test_07_implied_speed(self):
        # 100 km in 1 hour (3600 seconds) = 100 km/h
        spd = calculate_implied_speed(100.0, 3600.0)
        self.assertAlmostEqual(spd, 100.0, places=2)

        # 50 km in 30 minutes (1800 seconds) = 100 km/h
        spd2 = calculate_implied_speed(50.0, 1800.0)
        self.assertAlmostEqual(spd2, 100.0, places=2)

        # Zero or negative seconds must return None
        self.assertIsNone(calculate_implied_speed(50.0, 0.0))
        self.assertIsNone(calculate_implied_speed(50.0, -10.0))

    # -------------------------------------------------------------
    # 8. Position jumps
    # -------------------------------------------------------------
    def test_08_position_jumps(self):
        # Hop from Chennai to Bhopal (approx 1200 km) in 2 seconds
        detected, dist, implied = detect_location_jump(
            13.0827, 80.2707, 23.2599, 77.4126,
            maximum_distance=LOCATION_JUMP_LIMIT_KM,
            elapsed_seconds=2.0
        )
        self.assertTrue(detected)
        self.assertGreater(dist, 1000.0)
        self.assertIsNotNone(implied)

    # -------------------------------------------------------------
    # 9. Speed anomalies
    # -------------------------------------------------------------
    def test_09_speed_anomalies(self):
        # Normal speed (60 km/h <= 100 km/h limit)
        self.assertFalse(detect_speed_anomaly(60.0, speed_limit=SPEED_LIMIT))

        # Excessive speed (160 km/h > 100 km/h limit)
        self.assertTrue(detect_speed_anomaly(160.0, speed_limit=SPEED_LIMIT))

    # -------------------------------------------------------------
    # 10. Packet replay detection
    # -------------------------------------------------------------
    def test_10_packet_replay(self):
        imei = "REPLAY_TEST_DEV"
        unique_ts = int(time.time() * 1000)
        fp = create_fingerprint(imei, "TCP", "GPS", f"13.0_80.0_50_{unique_ts}")

        # First presentation -> not a replay
        self.assertFalse(is_replay(fp))

        # Store fingerprint
        store_fingerprint(fp, imei)

        # Second presentation -> detected replay!
        self.assertTrue(is_replay(fp))

    # -------------------------------------------------------------
    # 11. Unauthorized device rejection
    # -------------------------------------------------------------
    def test_11_unauthorized_device_rejection(self):
        # Authorized default device
        self.assertTrue(check_imei("TG001"))

        # Rogue unauthorized device
        self.assertFalse(check_imei("ROGUE_999999999999999"))

    # -------------------------------------------------------------
    # 12. Timestamp inconsistencies
    # -------------------------------------------------------------
    def test_12_timestamp_inconsistencies(self):
        # Backward timestamp step (-60s)
        anomalies = detect_timestamp_anomaly(current_timestamp=1000, previous_timestamp=1060)
        self.assertTrue(any(a["subtype"] == "BACKWARD_TIME_STEP" for a in anomalies))

        # Future timestamp drift (> 1 hour)
        future_epoch = time.time() + 7200
        future_anomalies = detect_timestamp_anomaly(current_timestamp=future_epoch)
        self.assertTrue(any(a["subtype"] == "FUTURE_CLOCK_DRIFT" for a in future_anomalies))

    # -------------------------------------------------------------
    # 13. NMEA injection test cases
    # -------------------------------------------------------------
    def test_13_nmea_injection_test_cases(self):
        valid = "$GNRMC,050434.00,A,1315.65794,N,08001.35745,E,0.046,,111026,,,D,V*16"
        injected_bad_cs = "$GNRMC,050434.00,A,1315.65794,N,08001.35745,E,0.046,,111026,,,D,V*00"
        self.assertTrue(validate_nmea_checksum(valid))
        self.assertFalse(validate_nmea_checksum(injected_bad_cs))

    # -------------------------------------------------------------
    # 14. Simulation source labeling
    # -------------------------------------------------------------
    def test_14_simulation_source_labeling(self):
        sim_packet = NormalizedTelemetry(
            device_id="TG001",
            source="attack_lab",
            source_type="SIMULATION",
            simulation=True,
            latitude=13.0,
            longitude=80.0
        )
        self.assertTrue(sim_packet.simulation)
        self.assertEqual(sim_packet.source_type, "SIMULATION")

        hw_packet = NormalizedTelemetry(
            device_id="trackguard-gnss-01",
            source="neo_m9n",
            source_type="HARDWARE",
            simulation=False,
            latitude=13.0,
            longitude=80.0
        )
        self.assertFalse(hw_packet.simulation)
        self.assertEqual(hw_packet.source_type, "HARDWARE")

    # -------------------------------------------------------------
    # 15. Database persistence
    # -------------------------------------------------------------
    def test_15_database_persistence(self):
        packet_id = add_packet(
            device_id="TEST_DEV",
            imei="TEST_DEV",
            protocol="TEST",
            packet_type="GPS",
            validation_status="NORMAL",
            latitude=13.0827,
            longitude=80.2707,
            speed=45.0,
            source="unit_test",
            source_type="HARDWARE"
        )
        self.assertIsNotNone(packet_id)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT latitude, longitude, source_type FROM packets WHERE packet_id=?", (packet_id,))
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertAlmostEqual(row[0], 13.0827, places=4)
        self.assertEqual(row[2], "HARDWARE")

    # -------------------------------------------------------------
    # 16. API validation
    # -------------------------------------------------------------
    def test_16_api_validation(self):
        client = app.test_client()

        # Health endpoint
        res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "OK")

        # GNSS status endpoint
        res_gnss = client.get("/api/gnss/status")
        self.assertEqual(res_gnss.status_code, 200)

        # Simulation run endpoint
        res_sim = client.post("/api/simulation/run/1")
        self.assertEqual(res_sim.status_code, 200)
        sim_data = res_sim.get_json()
        self.assertEqual(sim_data["status"], "success")

        # Packet detail endpoint
        res_live = client.get("/api/live-data")
        self.assertEqual(res_live.status_code, 200)
        packets = res_live.get_json().get("packets", [])
        if packets:
            pid = packets[0]["packet_id"]
            res_pkt = client.get(f"/api/packet/{pid}")
            self.assertEqual(res_pkt.status_code, 200)
            pkt_data = res_pkt.get_json()
            self.assertEqual(pkt_data["packet_id"], pid)
            self.assertIn("validation_status", pkt_data)

    # -------------------------------------------------------------
    # 17. PCAP parsing errors
    # -------------------------------------------------------------
    def test_17_pcap_parsing_errors(self):
        # Non-existent file must raise FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            extract_pcap_packets("non_existent_file.pcap")

    # -------------------------------------------------------------
    # 18. Mitigation actions
    # -------------------------------------------------------------
    def test_18_mitigation_actions(self):
        # Replay attack -> BLOCK
        act_replay = determine_action("HIGH", "Replay Attack")
        self.assertEqual(act_replay["action"], "BLOCK")
        self.assertEqual(act_replay["status"], "MITIGATED")

        # IMEI Spoofing -> REJECT
        act_spoof = determine_action("HIGH", "IMEI Spoofing")
        self.assertEqual(act_spoof["action"], "REJECT")
        self.assertEqual(act_spoof["status"], "MITIGATED")

        # Location jump -> QUARANTINE_POSITION
        act_jump = determine_action("HIGH", "Location Jump")
        self.assertEqual(act_jump["action"], "QUARANTINE_POSITION")

        # Speed anomaly -> ALERT
        act_speed = determine_action("MEDIUM", "Speed Anomaly")
        self.assertEqual(act_speed["action"], "ALERT")

    # -------------------------------------------------------------
    # 19. Regression of existing dashboard functionality
    # -------------------------------------------------------------
    def test_19_regression_existing_dashboard(self):
        client = app.test_client()
        res = client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        # Verify key headings and sections exist
        self.assertIn("TrackGuard", html)            # title / sidebar branding
        self.assertIn("Live GPS Telemetry Stream", html)
        self.assertIn("Security Events", html)
        self.assertIn("Wireshark / PCAP", html)
        self.assertIn("Attack Simulation", html)

    # -------------------------------------------------------------
    # 20. Separation of real hardware data from synthetic test data
    # -------------------------------------------------------------
    def test_20_separation_hardware_synthetic_data(self):
        # Run Scenario 1 synthetic test
        result = run_scenario("1")
        self.assertEqual(result["pass_fail"], "PASS")

        # Verify simulation flag in database record
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT is_simulation, scenario_id FROM simulation_runs ORDER BY run_id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)  # is_simulation must be explicitly 1
        self.assertEqual(row[1], "SCENARIO_1")


if __name__ == "__main__":
    unittest.main()
