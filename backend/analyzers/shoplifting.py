"""
shoplifting.py
==============
Shoplifting / concealment detector for Vantag.

Logic:
  1. Track every person bounding box frame-to-frame using track_id.
  2. For each person, maintain a list of product bounding boxes that were
     near them (within proximity_px pixels) in recent frames.
  3. If a product bbox was present near a person in frame N but disappears
     in frame N+K while the person is still present â†’ concealment event.
  4. Also flags "sweep" behaviour: person bbox sweeps across >=3 shelf items
     within sweep_window_seconds.
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
    "proximity_px": 120,            # pixel distance to count product as "near" person
    "concealment_frames": 8,        # frames product must be absent to trigger
    "sweep_window_seconds": 4.0,    # time window for sweep detection
    "sweep_item_threshold": 3,      # min items swept in window
    "cooldown_seconds": 30,
    "confidence_threshold": 0.45,
    "product_classes": [            # YOLO classes treated as products
        "bottle", "cup", "bowl", "banana", "apple", "sandwich", "orange",
        "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
        "handbag", "backpack", "suitcase", "book", "clock", "vase",
        "scissors", "teddy bear", "cell phone", "laptop", "mouse",
        "remote", "keyboard",
    ],
}

PRODUCT_CLASSES = set(_DEFAULTS["product_classes"])


@dataclass
class ShopliftingEvent:
    camera_id: str
    event_subtype: str          # "concealment" | "sweep"
    person_track_id: int
    confidence: float
    bbox: Tuple[int, int, int, int]
    timestamp: datetime
    severity: str               # "high" | "critical"
    items_involved: int = 1


class _PersonTrack:
    def __init__(self, track_id: int):
        self.track_id = track_id
        self.bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
        # product class_name â†’ consecutive frames absent while person present
        self.nearby_products: Dict[str, int] = {}
        # timestamps of each item contact event (for sweep detection)
        self.item_contact_times: List[float] = []


class ShopliftingDetector:
    def __init__(self, camera_id: str, config: Dict):
        self._camera_id = camera_id
        cfg = {**_DEFAULTS, **{k: v for k, v in config.items() if k in _DEFAULTS}}

        self._proximity_px: int = int(cfg["proximity_px"])
        self._concealment_frames: int = int(cfg["concealment_frames"])
        self._sweep_window: float = float(cfg["sweep_window_seconds"])
        self._sweep_threshold: int = int(cfg["sweep_item_threshold"])
        self._cooldown: float = float(cfg["cooldown_seconds"])
        self._conf_thresh: float = float(cfg["confidence_threshold"])

        self._tracks: Dict[int, _PersonTrack] = {}
        self._last_event_time: Dict[str, float] = {}  # subtype â†’ last emit time

    def _can_emit(self, subtype: str, now: float) -> bool:
        return (now - self._last_event_time.get(subtype, 0.0)) >= self._cooldown

    @staticmethod
    def _bbox_center(bbox: Tuple) -> Tuple[float, float]:
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)

    @staticmethod
    def _distance(a: Tuple, b: Tuple) -> float:
        return ((a[0]-b[0])**2 + (a[1]-b[1])**2) ** 0.5

    def analyze(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        timestamp: float,
    ) -> List[ShopliftingEvent]:
        if frame is None:
            return []

        events: List[ShopliftingEvent] = []
        now = time.monotonic()

        persons = [d for d in detections if d.class_name == "person" and d.confidence >= self._conf_thresh]
        products = [d for d in detections if d.class_name in PRODUCT_CLASSES and d.confidence >= self._conf_thresh]

        # Update / create person tracks
        active_ids = set()
        for person in persons:
            tid = person.track_id if person.track_id >= 0 else id(person)
            active_ids.add(tid)
            track = self._tracks.setdefault(tid, _PersonTrack(tid))
            track.bbox = person.bbox
            person_center = self._bbox_center(person.bbox)

            # Find nearby products
            nearby_now = set()
            for prod in products:
                prod_center = self._bbox_center(prod.bbox)
                if self._distance(person_center, prod_center) <= self._proximity_px:
                    nearby_now.add(prod.class_name)
                    track.item_contact_times.append(now)

            # Concealment: was nearby, now gone
            for cls in list(track.nearby_products):
                if cls in nearby_now:
                    track.nearby_products[cls] = 0   # reset absent counter
                else:
                    track.nearby_products[cls] = track.nearby_products.get(cls, 0) + 1
                    if track.nearby_products[cls] >= self._concealment_frames:
                        if self._can_emit("concealment", now):
                            self._last_event_time["concealment"] = now
                            events.append(ShopliftingEvent(
                                camera_id=self._camera_id,
                                event_subtype="concealment",
                                person_track_id=tid,
                                confidence=min(0.92, person.confidence + 0.15),
                                bbox=person.bbox,
                                timestamp=datetime.now(tz=timezone.utc),
                                severity="critical",
                                items_involved=1,
                            ))
                        del track.nearby_products[cls]

            for cls in nearby_now:
                if cls not in track.nearby_products:
                    track.nearby_products[cls] = 0

            # Sweep detection: many item contacts in short window
            cutoff = now - self._sweep_window
            track.item_contact_times = [t for t in track.item_contact_times if t >= cutoff]
            if len(track.item_contact_times) >= self._sweep_threshold:
                if self._can_emit("sweep", now):
                    self._last_event_time["sweep"] = now
                    events.append(ShopliftingEvent(
                        camera_id=self._camera_id,
                        event_subtype="sweep",
                        person_track_id=tid,
                        confidence=0.85,
                        bbox=person.bbox,
                        timestamp=datetime.now(tz=timezone.utc),
                        severity="critical",
                        items_involved=len(track.item_contact_times),
                    ))
                    track.item_contact_times.clear()

        # Remove stale tracks
        for stale_id in set(self._tracks) - active_ids:
            del self._tracks[stale_id]

        return events

