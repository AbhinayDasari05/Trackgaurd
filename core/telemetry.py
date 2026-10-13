"""
TrackGuard Normalized Telemetry Model
Standardizes GNSS and vehicle tracking telemetry across all ingestion pipelines
(Hardware NEO-M9N / ESP32, TCP Port 5006, GT06 Parser, PCAP Replay, Attack Simulator).
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any


@dataclass
class NormalizedTelemetry:
    device_id: str
    source: str                          # e.g., 'neo_m9n', 'esp32_uart', 'gt06_tcp', 'simulator', 'pcap'
    source_type: str                     # 'HARDWARE', 'SIMULATION', 'REPLAY'
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_kmh: Optional[float] = None
    altitude_m: Optional[float] = None
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fix_valid: bool = False
    fix_quality: int = 0                 # 0=Invalid, 1=GPS SPS, 2=DGPS, etc.
    satellites_used: int = 0
    satellites_in_view: int = 0
    hdop: Optional[float] = None
    simulation: bool = False
    raw_payload: Optional[str] = None

    def validate(self) -> Dict[str, Any]:
        """
        Validates telemetry fields and returns validation report:
        {"valid": bool, "errors": list, "warnings": list}
        """
        errors = []
        warnings = []

        if not self.device_id or not str(self.device_id).strip():
            errors.append("Missing device_id / IMEI")

        if self.latitude is not None:
            try:
                lat = float(self.latitude)
                if not (-90.0 <= lat <= 90.0):
                    errors.append(f"Latitude out of bounds [-90, +90]: {lat}")
            except (ValueError, TypeError):
                errors.append(f"Malformed latitude: {self.latitude}")

        if self.longitude is not None:
            try:
                lon = float(self.longitude)
                if not (-180.0 <= lon <= 180.0):
                    errors.append(f"Longitude out of bounds [-180, +180]: {lon}")
            except (ValueError, TypeError):
                errors.append(f"Malformed longitude: {self.longitude}")

        if self.speed_kmh is not None:
            try:
                spd = float(self.speed_kmh)
                if spd < 0.0:
                    errors.append(f"Negative speed: {spd}")
            except (ValueError, TypeError):
                errors.append(f"Malformed speed: {self.speed_kmh}")

        if self.fix_valid and (self.latitude is None or self.longitude is None):
            errors.append("Fix declared valid but coordinates are missing")

        if not self.fix_valid and (self.latitude is not None and self.longitude is not None):
            warnings.append("Coordinates present while fix validity status is False")

        # Timestamp parsing check
        try:
            if isinstance(self.timestamp_utc, str):
                # Accepts ISO format or numeric timestamp
                if self.timestamp_utc.replace(".", "", 1).isdigit():
                    pass
                else:
                    datetime.fromisoformat(self.timestamp_utc.replace("Z", "+00:00"))
        except Exception:
            errors.append(f"Invalid timestamp format: {self.timestamp_utc}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NormalizedTelemetry":
        """Factory from dictionary with flexible field name mapping."""
        device_id = str(data.get("device_id") or data.get("imei") or "UNKNOWN")
        source = str(data.get("source") or ("simulator" if data.get("simulation") else "tcp_packet"))
        is_sim = bool(data.get("simulation", False) or data.get("is_simulation", False))
        source_type = data.get("source_type") or ("SIMULATION" if is_sim else "HARDWARE")

        # Convert speed if needed
        speed = data.get("speed_kmh")
        if speed is None and "speed" in data:
            speed = data.get("speed")

        # Timestamp
        ts = data.get("timestamp_utc")
        if not ts and "timestamp" in data:
            raw_ts = data["timestamp"]
            if isinstance(raw_ts, (int, float)):
                ts = datetime.fromtimestamp(raw_ts, tz=timezone.utc).isoformat()
            else:
                ts = str(raw_ts)
        if not ts:
            ts = datetime.now(timezone.utc).isoformat()

        # Fix validity
        fix_valid = bool(data.get("fix_valid", True if (data.get("latitude") and data.get("longitude")) else False))

        return cls(
            device_id=device_id,
            source=source,
            source_type=source_type,
            latitude=float(data["latitude"]) if data.get("latitude") is not None else None,
            longitude=float(data["longitude"]) if data.get("longitude") is not None else None,
            speed_kmh=float(speed) if speed is not None else None,
            altitude_m=float(data["altitude_m"]) if data.get("altitude_m") is not None else None,
            timestamp_utc=ts,
            fix_valid=fix_valid,
            fix_quality=int(data.get("fix_quality", 1 if fix_valid else 0)),
            satellites_used=int(data.get("satellites_used", 0)),
            satellites_in_view=int(data.get("satellites_in_view", 0)),
            hdop=float(data["hdop"]) if data.get("hdop") is not None else None,
            simulation=is_sim,
            raw_payload=data.get("raw_payload")
        )
