"""
TrackGuard Mitigation & Response Engine
Executes automated security responses for detected anomalies and attacks:
  - Rejection of unauthorized identities (IMEI spoofing)
  - Blocking duplicate packet replay
  - Quarantining implausible location transitions (preserving last valid fix)
  - Flagging vehicle speed excursions
  - Rejection of corrupt or injected NMEA sentences
  - Auditing mitigation actions into SQLite database
"""

import os
import sqlite3
from typing import Dict, Any


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "trackguard.db")


def determine_action(severity: str, alert_type: str) -> Dict[str, Any]:
    """
    Maps anomaly classification to mitigation action, status, and auditable reason.
    """
    alert_lower = alert_type.lower()

    if "imei" in alert_lower or "unauthorized" in alert_lower:
        return {
            "action": "REJECT",
            "status": "MITIGATED",
            "policy": "DEVICE_AUTHENTICATION_POLICY",
            "message": "Unauthorized device identity. Ingestion connection rejected."
        }

    elif "replay" in alert_lower or "duplicate" in alert_lower:
        return {
            "action": "BLOCK",
            "status": "MITIGATED",
            "policy": "CRYPTOGRAPHIC_REPLAY_POLICY",
            "message": "Duplicate telemetry fingerprint detected. Packet blocked from navigation state."
        }

    elif "jump" in alert_lower or "position" in alert_lower or "spoofing" in alert_lower:
        return {
            "action": "QUARANTINE_POSITION",
            "status": "MITIGATED",
            "policy": "KINEMATIC_PLAUSIBILITY_POLICY",
            "message": "Implausible position transition. Current coordinate quarantined; last valid fix retained."
        }

    elif "nmea" in alert_lower or "injection" in alert_lower or "integrity" in alert_lower:
        return {
            "action": "REJECT_MALFORMED",
            "status": "MITIGATED",
            "policy": "PROTOCOL_INTEGRITY_POLICY",
            "message": "Corrupt or injected NMEA message rejected. Parser state preserved."
        }

    elif "fix" in alert_lower or "manipulation" in alert_lower:
        return {
            "action": "REJECT_INCONSISTENT",
            "status": "MITIGATED",
            "policy": "GNSS_HEALTH_POLICY",
            "message": "Contradictory GNSS fix indicators. Coordinate discarded from active track."
        }

    elif "signal loss" in alert_lower or "antenna" in alert_lower:
        return {
            "action": "PRESERVE_LAST_FIX",
            "status": "MONITORED",
            "policy": "GNSS_LIVENESS_POLICY",
            "message": "GNSS fix lost. Last valid position preserved with staleness timer."
        }

    elif "timestamp" in alert_lower:
        return {
            "action": "FLAG_CLOCK_SKEW",
            "status": "MONITORED",
            "policy": "TIME_SYNCHRONIZATION_POLICY",
            "message": "Telemetry timestamp anomaly flagged for operator inspection."
        }

    elif "speed" in alert_lower or severity == "MEDIUM":
        return {
            "action": "ALERT",
            "status": "MONITORED",
            "policy": "SPEED_COMPLIANCE_POLICY",
            "message": f"{alert_type} detected. Security monitoring alert raised."
        }

    elif severity == "HIGH":
        return {
            "action": "BLOCK",
            "status": "MITIGATED",
            "policy": "GENERAL_SECURITY_POLICY",
            "message": f"High severity anomaly ({alert_type}) mitigated."
        }

    else:
        return {
            "action": "LOG",
            "status": "LOGGED",
            "policy": "DEFAULT_AUDIT_POLICY",
            "message": f"{alert_type} recorded in audit ledger."
        }


def log_mitigation_audit(alert: Dict[str, Any], result: Dict[str, Any]):
    """Records mitigation action to audit_logs table."""
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            details = (
                f"Action={result['action']} Status={result['status']} "
                f"Alert='{alert.get('alert_type')}' IMEI='{alert.get('imei')}' "
                f"Policy={result.get('policy')} Msg='{result.get('message')}'"
            )
            cur.execute("""
            INSERT INTO audit_logs (action_type, details, actor)
            VALUES (?, ?, ?)
            """, ("MITIGATION_APPLIED", details, "MITIGATION_ENGINE"))
            conn.commit()
            conn.close()
    except Exception as exc:
        print("Audit log error:", exc)


def apply_mitigation(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applies automated mitigation policy to incoming alert
    and writes to audit log.
    """
    alert_type = alert.get("alert_type") or alert.get("type") or "Unknown"
    severity = alert.get("severity") or "MEDIUM"

    result = determine_action(severity, alert_type)

    print("\n==========================================")
    print("       TRACKGUARD MITIGATION")
    print("==========================================")
    print("IMEI:", alert.get("imei"))
    print("Alert:", alert_type)
    print("Severity:", severity)
    print("Action:", result["action"])
    print("Status:", result["status"])
    print("Policy:", result.get("policy"))
    print("Response:", result["message"])
    print("==========================================")

    log_mitigation_audit(alert, result)

    return result


if __name__ == "__main__":
    print("TRACKGUARD MITIGATION TEST")

    high_alert = {
        "imei": "123456789012345",
        "alert_type": "Location Jump",
        "severity": "HIGH"
    }

    medium_alert = {
        "imei": "123456789012345",
        "alert_type": "Speed Anomaly",
        "severity": "MEDIUM"
    }

    print("\nTesting HIGH severity alert...")
    apply_mitigation(high_alert)

    print("\nTesting MEDIUM severity alert...")
    apply_mitigation(medium_alert)
