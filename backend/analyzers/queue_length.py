"""
queue_length.py
===============
Counts persons in defined queue zones and alerts when queue exceeds
a configurable threshold. Also computes average wait time estimate
based on how long persons remain in the zone.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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
    "queue_zones": [],           # [{"label": str, "bbox": [x1,y1,x2,y2], "max_queue": int}]
    "alert_threshold": 5,        # default max queue before alert
    "check_interval_seconds": 3.0,
    "cooldown_seconds": 60,
    "wait_time_fps": 10,         # assumed FPS for wait time estimation
}


@dataclass
class QueueEvent:
    camera_id: str
    zone_label: str
    queue_length: int
    max_allowed: int
    estimated_wait_minutes: float
    timestamp: datetime
    severity: str


class QueueLengthAnalyzer:
    def __init__(self, camera_id: str, config: Dict):
        self._camera_id = camera_id
        cfg = {**_DEFAULTS, **{k: v for k, v in config.items() if k in _DEFAULTS}}

        self._default_max: int = int(cfg["alert_threshold"])
        self._check_interval: float = float(cfg["check_interval_seconds"])
        self._cooldown: float = float(cfg["cooldown_seconds"])
        self._fps: float = float(cfg["wait_time_fps"])

        self._zones: List[Dict] = []
        for z in cfg.get("queue_zones", []):
            self._zones.append({
                "label": z.get("label", "checkout"),
                "bbox": z.get("bbox", [0, 0, 9999, 9999]),
                "max_queue": int(z.get("max_queue", self._default_max)),
                "last_check": 0.0,
                "last_event": 0.0,
                "track_entry": {},   # track_id â†’ monotonic entry time
                "history": [],       # recent counts for rolling average
            })

    @staticmethod
    def _in_zone(det_bbox: Tuple, zone_bbox: List) -> bool:
        cx = (det_bbox[0] + det_bbox[2]) / 2
        cy = (det_bbox[1] + det_bbox[3]) / 2
        return zone_bbox[0] <= cx <= zone_bbox[2] and zone_bbox[1] <= cy <= zone_bbox[3]

    def get_queue_status(self) -> List[Dict]:
        """Called by the API to get current queue lengths for the dashboard."""
        return [
            {
                "zone": z["label"],
                "current_count": z["history"][-1] if z["history"] else 0,
                "avg_count": round(sum(z["history"][-10:]) / max(len(z["history"][-10:]), 1), 1),
                "max_allowed": z["max_queue"],
            }
            for z in self._zones
        ]

    def analyze(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        timestamp: float,
    ) -> List[QueueEvent]:
        if frame is None:
            return []

        events = []
        now = time.monotonic()
        persons = [d for d in detections if d.class_name == "person"]

        for zone in self._zones:
            if (now - zone["last_check"]) < self._check_interval:
                continue
            zone["last_check"] = now

            zone_bbox = zone["bbox"]
            in_zone = [p for p in persons if self._in_zone(p.bbox, zone_bbox)]
            count = len(in_zone)

            zone["history"].append(count)
            if len(zone["history"]) > 60:
                zone["history"].pop(0)

            # Track entry times for wait estimation
            active_tids = set()
            for p in in_zone:
                tid = p.track_id if p.track_id >= 0 else id(p)
                active_tids.add(tid)
                zone["track_entry"].setdefault(tid, now)
            for stale in set(zone["track_entry"]) - active_tids:
                del zone["track_entry"][stale]

            # Estimate wait: average dwell time of current occupants
            if zone["track_entry"]:
                avg_dwell_sec = sum(now - t for t in zone["track_entry"].values()) / len(zone["track_entry"])
                est_wait_min = round(avg_dwell_sec / 60, 1)
            else:
                est_wait_min = 0.0

            if count > zone["max_queue"]:
                if (now - zone["last_event"]) >= self._cooldown:
                    zone["last_event"] = now
                    severity = "critical" if count >= zone["max_queue"] * 1.5 else "high"
                    events.append(QueueEvent(
                        camera_id=self._camera_id,
                        zone_label=zone["label"],
                        queue_length=count,
                        max_allowed=zone["max_queue"],
                        estimated_wait_minutes=est_wait_min,
                        timestamp=datetime.now(tz=timezone.utc),
                        severity=severity,
                    ))
                    logger.info(
                        "QueueEvent | cam=%s zone=%s count=%d est_wait=%.1fmin",
                        self._camera_id, zone["label"], count, est_wait_min,
                    )

        return events

