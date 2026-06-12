"""
restricted_zone.py
==================
Detects when a person enters a defined restricted polygon zone.

Supports multiple named zones per camera, each with:
  - polygon: list of [x, y] pixel coordinates
  - allowed_hours: optional time restriction (e.g. [22, 6] = 10pmâ€“6am)
  - alert_severity: "medium" | "high" | "critical"
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    from backend.inference.yolo_engine import Detection
except ImportError:
    from dataclasses import dataclass as _dc
    @_dc
    class Detection:
        track_id: int = -1
        class_name: str = ""
        confidence: float = 0.0
        bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
        keypoints: Optional[list] = None

_DEFAULTS = {
    "restricted_zones": [],     # see _ZoneDef below
    "cooldown_seconds": 15,
    "min_frames_inside": 3,     # must be inside zone for N consecutive frames
}


@dataclass
class ZoneEntryEvent:
    camera_id: str
    zone_name: str
    person_track_id: int
    confidence: float
    bbox: Tuple[int, int, int, int]
    timestamp: datetime
    severity: str


class _ZoneDef:
    def __init__(self, raw: Dict):
        self.name: str = raw.get("name", "restricted")
        pts = raw.get("polygon", [])
        self.polygon = np.array(pts, dtype=np.float32) if pts else None
        self.severity: str = raw.get("severity", "high")
        self.allowed_hours: Optional[Tuple[int, int]] = None
        if "allowed_hours" in raw:
            self.allowed_hours = tuple(raw["allowed_hours"])
        # Runtime state
        self.person_frame_count: Dict[int, int] = {}
        self.last_event: Dict[int, float] = {}

    def point_inside(self, x: float, y: float) -> bool:
        if self.polygon is None or len(self.polygon) < 3:
            return False
        return cv2.pointPolygonTest(self.polygon, (float(x), float(y)), False) >= 0

    def is_active_now(self) -> bool:
        if self.allowed_hours is None:
            return True
        h = datetime.now().hour
        start, end = self.allowed_hours
        if start <= end:
            return not (start <= h < end)   # restricted outside allowed hours
        return h >= start or h < end

import cv2


class RestrictedZoneDetector:
    def __init__(self, camera_id: str, config: Dict):
        self._camera_id = camera_id
        cfg = {**_DEFAULTS, **{k: v for k, v in config.items() if k in _DEFAULTS}}
        self._cooldown: float = float(cfg["cooldown_seconds"])
        self._min_frames: int = int(cfg["min_frames_inside"])
        self._zones: List[_ZoneDef] = [
            _ZoneDef(z) for z in cfg.get("restricted_zones", [])
        ]

    def analyze(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        timestamp: float,
    ) -> List[ZoneEntryEvent]:
        if frame is None or not self._zones:
            return []

        events: List[ZoneEntryEvent] = []
        now = time.monotonic()
        persons = [d for d in detections if d.class_name == "person"]

        for zone in self._zones:
            if not zone.is_active_now():
                continue

            active_tids = set()
            for person in persons:
                tid = person.track_id if person.track_id >= 0 else id(person)
                active_tids.add(tid)
                x1, y1, x2, y2 = person.bbox
                foot_x, foot_y = (x1 + x2) / 2, y2   # use foot point

                if zone.point_inside(foot_x, foot_y):
                    zone.person_frame_count[tid] = zone.person_frame_count.get(tid, 0) + 1
                    if zone.person_frame_count[tid] >= self._min_frames:
                        last = zone.last_event.get(tid, 0.0)
                        if (now - last) >= self._cooldown:
                            zone.last_event[tid] = now
                            events.append(ZoneEntryEvent(
                                camera_id=self._camera_id,
                                zone_name=zone.name,
                                person_track_id=tid,
                                confidence=person.confidence,
                                bbox=person.bbox,
                                timestamp=datetime.now(tz=timezone.utc),
                                severity=zone.severity,
                            ))
                            logger.warning(
                                "RestrictedZone | cam=%s zone=%s track=%d",
                                self._camera_id, zone.name, tid,
                            )
                else:
                    zone.person_frame_count.pop(tid, None)

            # Clean up stale tracks
            for stale in set(zone.person_frame_count) - active_tids:
                zone.person_frame_count.pop(stale, None)

        return events

