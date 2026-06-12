"""
product_sweeping.py
===================
Product sweeping (shelf-sweep theft) detector for the Vantag platform.

Detects the rapid removal of multiple items from a shelf zone by a person
within a short time window — a behaviour characteristic of retail theft.

Detection logic:
1. Only track ``person`` detections whose bounding-box centroid falls
   inside the configured ``zone_polygon``.
2. Track *item-class* bounding-box appearances and disappearances inside
   the same zone within a rolling time window.
3. When the combined appearance/disappearance count reaches
   ``sweep_item_threshold``, emit a :class:`SweepingEvent`.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import for shapely – emit a clear error if missing.
# ---------------------------------------------------------------------------

try:
    from shapely.geometry import Point, Polygon  # type: ignore[import]
    _SHAPELY_OK = True
except ImportError:
    _SHAPELY_OK = False
    logger.error(
        "product_sweeping: 'shapely' is not installed. "
        "Zone containment checks will be disabled. "
        "Install with: pip install shapely"
    )

# ---------------------------------------------------------------------------
# Attempt to import Detection from the sibling inference package.
# A fallback stub is defined so the module is importable in isolation.
# ---------------------------------------------------------------------------
try:
    from backend.inference.yolo_engine import Detection  # type: ignore[import]
except ImportError:
    from dataclasses import dataclass as _dc

    @_dc
    class Detection:  # type: ignore[no-redef]
        track_id: int = -1
        class_id: int = 0
        class_name: str = ""
        confidence: float = 0.0
        bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
        keypoints: Optional[list] = None


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULTS: Dict = {
    "zone_polygon": [],              # List of [x, y] points
    "sweep_item_threshold": 3,       # Min item events to trigger
    "sweep_time_window_seconds": 5,  # Rolling window width
    "confidence_threshold": 0.6,     # Min detection confidence
    # Classes considered "items" (anything that isn't a person).
    "item_classes": [
        "bottle", "can", "cup", "book", "cell phone", "handbag",
        "backpack", "suitcase", "scissors", "remote", "vase",
        "product", "item",
    ],
}


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class SweepingEvent:
    """Emitted when a product-sweeping gesture is detected."""

    camera_id: str
    timestamp: datetime
    confidence: float
    bbox_snapshot: List[Tuple[int, int, int, int]]
    """Bounding boxes of item detections that contributed to the event."""
    track_ids: List[int]
    """Person track-IDs that were inside the zone during the event."""


# ---------------------------------------------------------------------------
# ProductSweepingDetector
# ---------------------------------------------------------------------------

class ProductSweepingDetector:
    """
    Stateful product-sweeping detector bound to a single camera.

    Parameters
    ----------
    camera_id:
        Identifier of the camera this detector is bound to.
    config:
        Dict of configuration overrides.  Recognised keys are defined in
        ``_DEFAULTS`` above.
    """

    def __init__(self, camera_id: str, config: Dict) -> None:
        self._camera_id = camera_id

        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._zone_pts: List[List[int]] = cfg["zone_polygon"]
        self._sweep_threshold: int = int(cfg["sweep_item_threshold"])
        self._time_window: float = float(cfg["sweep_time_window_seconds"])
        self._conf_threshold: float = float(cfg["confidence_threshold"])
        self._item_classes: Set[str] = {c.lower() for c in cfg["item_classes"]}

        # Build Shapely polygon once; None if shapely is missing or zone is empty.
        self._zone_polygon: Optional[object] = None
        if _SHAPELY_OK and len(self._zone_pts) >= 3:
            self._zone_polygon = Polygon(self._zone_pts)

        # Rolling deque of (timestamp, bbox) tuples for item events inside zone.
        self._item_event_times: Deque[Tuple[float, Tuple[int, int, int, int]]] = deque()

        # Track which item track-ids were seen last frame (to detect disappearances).
        self._prev_item_ids_in_zone: Set[int] = set()

        # Persons currently in zone.
        self._persons_in_zone: Dict[int, float] = {}  # track_id → first_seen_ts

        # Cooldown: avoid re-emitting for the same sweep episode.
        self._last_event_time: float = 0.0
        self._cooldown: float = self._time_window * 2

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _centroid(self, bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _in_zone(self, bbox: Tuple[int, int, int, int]) -> bool:
        if self._zone_polygon is None:
            return True  # No zone configured → treat everything as inside.
        cx, cy = self._centroid(bbox)
        return self._zone_polygon.contains(Point(cx, cy))  # type: ignore[union-attr]

    def _prune_old_events(self, now: float) -> None:
        cutoff = now - self._time_window
        while self._item_event_times and self._item_event_times[0][0] < cutoff:
            self._item_event_times.popleft()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        detections: List[Detection],
        frame: np.ndarray,
    ) -> Optional[SweepingEvent]:
        """
        Analyse a single frame's detections and return a
        :class:`SweepingEvent` if sweeping is detected, otherwise ``None``.

        Parameters
        ----------
        detections:
            All detections for the current frame from :class:`YOLOEngine`.
        frame:
            The corresponding BGR frame (not used directly but kept for
            consistency with other analyzers that may encode snapshots).
        """
        now = time.monotonic()
        self._prune_old_events(now)

        persons_in_zone: Set[int] = set()
        current_item_ids_in_zone: Set[int] = set()
        item_bboxes_in_zone: List[Tuple[int, int, int, int]] = []

        for det in detections:
            if det.confidence < self._conf_threshold:
                continue

            name = det.class_name.lower()

            if name == "person":
                if self._in_zone(det.bbox):
                    persons_in_zone.add(det.track_id)
                    if det.track_id not in self._persons_in_zone:
                        self._persons_in_zone[det.track_id] = now
                continue

            if name in self._item_classes:
                if self._in_zone(det.bbox):
                    current_item_ids_in_zone.add(det.track_id)
                    item_bboxes_in_zone.append(det.bbox)

        # Clean up persons that left the zone.
        gone_persons = set(self._persons_in_zone.keys()) - persons_in_zone
        for pid in gone_persons:
            del self._persons_in_zone[pid]

        # Count item appearances (new IDs entering zone).
        appeared = current_item_ids_in_zone - self._prev_item_ids_in_zone
        # Count item disappearances (IDs that were in zone but are now gone).
        disappeared = self._prev_item_ids_in_zone - current_item_ids_in_zone

        for bbox in item_bboxes_in_zone:
            for _ in appeared:
                self._item_event_times.append((now, bbox))
                break  # one entry per appearance event (not per bbox)

        for _ in disappeared:
            # Use a zero bbox as a disappearance marker.
            self._item_event_times.append((now, (0, 0, 0, 0)))

        self._prev_item_ids_in_zone = current_item_ids_in_zone

        # Check threshold.
        if (
            len(self._item_event_times) >= self._sweep_threshold
            and bool(self._persons_in_zone)
            and (now - self._last_event_time) > self._cooldown
        ):
            self._last_event_time = now
            snap_bboxes = [ev[1] for ev in self._item_event_times]
            person_ids = list(self._persons_in_zone.keys())
            total_events = len(self._item_event_times)
            confidence = min(
                1.0,
                (total_events / self._sweep_threshold) * 0.5
                + min(len(person_ids), 2) * 0.25,
            )
            logger.warning(
                "SweepingEvent | camera=%s persons=%s item_events=%d",
                self._camera_id,
                person_ids,
                total_events,
            )
            return SweepingEvent(
                camera_id=self._camera_id,
                timestamp=datetime.now(tz=timezone.utc),
                confidence=round(confidence, 4),
                bbox_snapshot=snap_bboxes,
                track_ids=person_ids,
            )

        return None
