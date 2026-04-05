"""
queue_detector.py
=================
Queue and checkout wait-time detector for the Vantag platform.

For each named lane zone the detector:
1. Counts persons currently inside the zone (queue depth).
2. Tracks per-track-id entry/exit timestamps to compute individual wait times.
3. Maintains a rolling window of completed wait-time measurements to compute
   an average.
4. Emits a :class:`QueueEvent` whenever depth exceeds ``depth_threshold``.

Severity levels:
    * ``'LOW'``     – depth in (threshold, threshold × 1.5]
    * ``'MEDIUM'``  – depth in (threshold × 1.5, threshold × 2.5]
    * ``'HIGH'``    – depth > threshold × 2.5
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shapely for zone containment.
# ---------------------------------------------------------------------------

try:
    from shapely.geometry import Point, Polygon  # type: ignore[import]
    _SHAPELY_OK = True
except ImportError:
    _SHAPELY_OK = False
    logger.warning(
        "queue_detector: 'shapely' not installed — zone containment disabled. "
        "Install with: pip install shapely"
    )

# ---------------------------------------------------------------------------
# Detection import with fallback stub.
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
# Defaults
# ---------------------------------------------------------------------------

_DEFAULTS: Dict = {
    "lane_zones": [],             # [{"label": str, "polygon": [[x,y]…]}]
    "depth_threshold": 4,
    "rolling_window_seconds": 300.0,
}


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class QueueEvent:
    """Emitted when a lane exceeds its depth threshold."""

    camera_id: str
    lane_id: str
    depth: int
    avg_wait_seconds: float
    timestamp: datetime
    severity: str  # 'LOW' | 'MEDIUM' | 'HIGH'


# ---------------------------------------------------------------------------
# _LaneState – per-lane internal state
# ---------------------------------------------------------------------------

class _LaneState:
    def __init__(self, label: str, polygon: Optional[object]) -> None:
        self.label = label
        self.polygon = polygon
        # track_id → entry monotonic timestamp
        self.entry_times: Dict[int, float] = {}
        # Completed wait-time samples (timestamp, wait_seconds).
        self.wait_samples: Deque[Tuple[float, float]] = deque()


# ---------------------------------------------------------------------------
# QueueDetector
# ---------------------------------------------------------------------------

class QueueDetector:
    """
    Stateful queue detector bound to a single camera.

    Parameters
    ----------
    camera_id:
        Identifier of the camera.
    config:
        Configuration dict (see ``_DEFAULTS``).
    """

    def __init__(self, camera_id: str, config: Dict) -> None:
        self._camera_id = camera_id

        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._depth_threshold: int = int(cfg["depth_threshold"])
        self._rolling_window: float = float(cfg["rolling_window_seconds"])

        self._lanes: List[_LaneState] = []
        for zone_def in cfg.get("lane_zones", []):
            label: str = zone_def.get("label", "lane")
            pts: List[List[int]] = zone_def.get("polygon", [])
            poly = None
            if _SHAPELY_OK and len(pts) >= 3:
                poly = Polygon(pts)
            self._lanes.append(_LaneState(label, poly))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _centroid(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _in_zone(
        self,
        bbox: Tuple[int, int, int, int],
        poly: Optional[object],
    ) -> bool:
        if poly is None:
            return True
        cx, cy = self._centroid(bbox)
        return poly.contains(Point(cx, cy))  # type: ignore[union-attr]

    def _prune_samples(self, lane: _LaneState, now: float) -> None:
        cutoff = now - self._rolling_window
        while lane.wait_samples and lane.wait_samples[0][0] < cutoff:
            lane.wait_samples.popleft()

    def _avg_wait(self, lane: _LaneState) -> float:
        if not lane.wait_samples:
            return 0.0
        return float(np.mean([ws for _, ws in lane.wait_samples]))

    def _severity(self, depth: int) -> str:
        t = self._depth_threshold
        if depth > t * 2.5:
            return "HIGH"
        if depth > t * 1.5:
            return "MEDIUM"
        return "LOW"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        detections: List[Detection],
        timestamp: float,
    ) -> List[QueueEvent]:
        """
        Process one frame's detections and return queue events.

        Parameters
        ----------
        detections:
            Frame detections; only ``'person'`` class is considered.
        timestamp:
            Monotonic timestamp of the frame (``time.monotonic()``).

        Returns
        -------
        List of :class:`QueueEvent` — one per lane that exceeds the threshold.
        """
        events: List[QueueEvent] = []

        # Collect persons and their bboxes.
        persons: Dict[int, Tuple[int, int, int, int]] = {
            det.track_id: det.bbox
            for det in detections
            if det.class_name.lower() == "person" and det.track_id >= 0
        }

        for lane in self._lanes:
            self._prune_samples(lane, timestamp)

            current_ids_in_lane: set = set()

            for track_id, bbox in persons.items():
                if self._in_zone(bbox, lane.polygon):
                    current_ids_in_lane.add(track_id)
                    if track_id not in lane.entry_times:
                        lane.entry_times[track_id] = timestamp

            # Detect exits: persons who were tracked but are now gone.
            exited = set(lane.entry_times.keys()) - current_ids_in_lane
            for track_id in exited:
                wait = timestamp - lane.entry_times.pop(track_id)
                lane.wait_samples.append((timestamp, wait))

            depth = len(current_ids_in_lane)
            if depth >= self._depth_threshold:
                avg_wait = self._avg_wait(lane)
                severity = self._severity(depth)
                logger.info(
                    "QueueEvent | camera=%s lane='%s' depth=%d avg_wait=%.1fs",
                    self._camera_id,
                    lane.label,
                    depth,
                    avg_wait,
                )
                events.append(
                    QueueEvent(
                        camera_id=self._camera_id,
                        lane_id=lane.label,
                        depth=depth,
                        avg_wait_seconds=round(avg_wait, 2),
                        timestamp=datetime.now(tz=timezone.utc),
                        severity=severity,
                    )
                )

        return events
