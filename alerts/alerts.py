from datetime import datetime


def generate_alert(alert_type, severity, description, imei):

    alert = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "imei": imei,
        "alert_type": alert_type,
        "severity": severity,
        "description": description,
        "status": "ACTIVE"
    }

    return alert


def display_alert(alert):

    print("\n==========================================")
    print("       TRACKGUARD SECURITY ALERT")
    print("==========================================")

    print("Time:", alert["timestamp"])
    print("IMEI:", alert["imei"])
    print("Alert Type:", alert["alert_type"])
    print("Severity:", alert["severity"])
    print("Description:", alert["description"])
    print("Status:", alert["status"])

    print("==========================================")


if __name__ == "__main__":

    print("TRACKGUARD ALERT MODULE TEST")

    alert = generate_alert(
        "Speed Anomaly",
        "MEDIUM",
        "Vehicle speed exceeds configured limit",
        "123456789012345"
    )

    display_alert(alert)
