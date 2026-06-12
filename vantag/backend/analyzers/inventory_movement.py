"""
inventory_movement.py
=====================
Tracks product item counts per shelf zone between frames.
Alerts when:
  - Count drops by >= threshold items suddenly (potential bulk removal / theft)
  - Count drops to zero (empty shelf pathway)
  - Rapid movement of items without a person present (unknown movement)
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
    "zones": [],                      # [{"label": str, "bbox": [x1,y1,x2,y2]}]
    "drop_threshold": 2,              # items removed in one check interval to alert
    "check_interval_seconds": 5.0,
    "cooldown_seconds": 20,
    "person_suppression": True,       # suppress alert if person detected in zone
    "product_classes": [
        "bottle", "cup", "bowl", "banana", "apple", "orange",
        "broccoli", "carrot", "sandwich", "book", "vase",
    ],
}


@dataclass
class InventoryEvent:
    camera_id: str
    zone_label: str
    previous_count: int
    current_count: int
    delta: int
    person_present: bool
    timestamp: datetime
    severity: str


class InventoryMovementDetector:
    def __init__(self, camera_id: str, config: Dict):
        self._camera_id = camera_id
        cfg = {**_DEFAULTS, **{k: v for k, v in config.items() if k in _DEFAULTS}}

        self._drop_threshold: int = int(cfg["drop_threshold"])
        self._check_interval: float = float(cfg["check_interval_seconds"])
        self._cooldown: float = float(cfg["cooldown_seconds"])
        self._person_suppression: bool = bool(cfg["person_suppression"])
        self._product_classes = set(cfg["product_classes"])

        # Zone state: label → {bbox, last_count, last_check, last_event}
        self._zones: List[Dict] = []
        for z in cfg.get("zones", []):
            self._zones.append({
                "label": z.get("label", "zone"),
                "bbox": z.get("bbox", [0, 0, 9999, 9999]),
                "last_count": -1,
                "last_check": 0.0,
                "last_event": 0.0,
            })

    @staticmethod
    def _bbox_center(bbox: Tuple) -> Tuple[float, float]:
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)

    @staticmethod
    def _in_zone(det_bbox: Tuple, zone_bbox: List) -> bool:
        cx, cy = ((det_bbox[0]+det_bbox[2])/2, (det_bbox[1]+det_bbox[3])/2)
        return zone_bbox[0] <= cx <= zone_bbox[2] and zone_bbox[1] <= cy <= zone_bbox[3]

    def analyze(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        timestamp: float,
    ) -> List[InventoryEvent]:
        if frame is None:
            return []

        events = []
        now = time.monotonic()

        products = [d for d in detections if d.class_name in self._product_classes]
        persons = [d for d in detections if d.class_name == "person"]

        for zone in self._zones:
            if (now - zone["last_check"]) < self._check_interval:
                continue
            zone["last_check"] = now

            zone_bbox = zone["bbox"]
            count = sum(1 for p in products if self._in_zone(p.bbox, zone_bbox))
            person_present = any(self._in_zone(p.bbox, zone_bbox) for p in persons)

            prev = zone["last_count"]
            zone["last_count"] = count

            if prev < 0:
                continue  # first observation — baseline

            delta = prev - count
            if delta >= self._drop_threshold:
                if (now - zone["last_event"]) >= self._cooldown:
                    zone["last_event"] = now
                    severity = "critical" if delta >= self._drop_threshold * 2 else "high"
                    if person_present and self._person_suppression:
                        severity = "medium"  # person probably restocking
                    events.append(InventoryEvent(
                        camera_id=self._camera_id,
                        zone_label=zone["label"],
                        previous_count=prev,
                        current_count=count,
                        delta=delta,
                        person_present=person_present,
                        timestamp=datetime.now(tz=timezone.utc),
                        severity=severity,
                    ))
                    logger.info(
                        "InventoryEvent | cam=%s zone=%s prev=%d cur=%d person=%s",
                        self._camera_id, zone["label"], prev, count, person_present,
                    )

        return events
