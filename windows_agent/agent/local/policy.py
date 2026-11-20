from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

CORE_FEATURES = frozenset({"people_count", "shoplifting", "inventory_movement", "fall_detected", "restricted_zone", "loitering", "suspicious_behavior", "crowding"})


def feature_enabled(camera: dict, feature: str, claims: dict, timezone_name: str, now: datetime | None = None) -> bool:
    if feature not in CORE_FEATURES or feature not in claims.get("features", []):
        return False
    if not camera.get("enabled", True) or not camera.get("detections", {}).get(feature, False):
        return False
    schedule = camera.get("detection_schedule", {})
    if feature == "shoplifting" or not schedule.get("enabled"):
        return True
    local = (now or datetime.now(ZoneInfo(timezone_name))).astimezone(ZoneInfo(timezone_name))
    current = local.strftime("%H:%M")
    start, end = schedule["start"], schedule["end"]
    if start == end:
        return True
    return start <= current < end if start < end else current >= start or current < end
