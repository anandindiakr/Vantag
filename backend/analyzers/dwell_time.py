"""
dwell_time.py
=============
Anomalous dwell-time analyser for the Vantag platform.

Tracks how long each person (identified by ByteTrack ``track_id``) spends
inside each named ROI zone.  Emits a :class:`DwellEvent` the first time a
person's zone-residence duration exceeds ``dwell_threshold_seconds``.  A
per-track-per-zone cooldown prevents the same event from being repeatedly
emitted within the same lingering episode.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shapely – optional but strongly recommended.
# ---------------------------------------------------------------------------

try:
    from shapely.geometry import Point, Polygon  # type: ignore[import]
    _SHAPELY_OK = True
except ImportError:
    _SHAPELY_OK = False
    logger.error(
        "dwell_time: 'shapely' is not installed. "
        "Zone containment will be disabled. "
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
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULTS: Dict = {
    "zones": [],                       # List of {"label": str, "polygon": [[x,y]…]}
    "dwell_threshold_seconds": 45.0,
    "cooldown_seconds": 60.0,
}

# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class DwellEvent:
    """Emitted when a tracked person lingers in a zone beyond the threshold."""

    camera_id: str
    track_id: int
    zone_label: str
    dwell_seconds: float
    timestamp: datetime
    bbox: Tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# DwellTimeAnalyzer
# ---------------------------------------------------------------------------

class DwellTimeAnalyzer:
    """
    Stateful dwell-time analyser bound to a single camera.

    Parameters
    ----------
    camera_id:
        Identifier of the camera this analyser is bound to.
    config:
        Dict of configuration overrides.  Recognised keys:

        * ``zones`` — list of ``{"label": str, "polygon": [[x,y], …]}``
        * ``dwell_threshold_seconds`` — seconds before an event is emitted
          (default 45).
        * ``cooldown_seconds`` — minimum time between events for the same
          (track_id, zone_label) pair (default 60).
    """

    def __init__(self, camera_id: str, config: Dict) -> None:
        self._camera_id = camera_id

        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._dwell_threshold: float = float(cfg["dwell_threshold_seconds"])
        self._cooldown: float = float(cfg["cooldown_seconds"])

        # Build zone list: [(label, shapely_polygon_or_None)]
        self._zones: List[Tuple[str, Optional[object]]] = []
        for zone_def in cfg.get("zones", []):
            label: str = zone_def.get("label", "zone")
            pts: List[List[int]] = zone_def.get("polygon", [])
            poly = None
            if _SHAPELY_OK and len(pts) >= 3:
                poly = Polygon(pts)
            self._zones.append((label, poly))

        # entry_times[track_id][zone_label] = monotonic time when person entered zone
        self._entry_times: Dict[int, Dict[str, float]] = {}

        # last_event_time[track_id][zone_label] = monotonic time of last emitted event
        self._last_event_time: Dict[int, Dict[str, float]] = {}

        # Remember last known bbox per track_id for the event payload.
        self._last_bbox: Dict[int, Tuple[int, int, int, int]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _centroid(self, bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _in_zone(
        self,
        bbox: Tuple[int, int, int, int],
        poly: Optional[object],
    ) -> bool:
        if poly is None:
            return True  # No polygon → treat whole frame as zone.
        cx, cy = self._centroid(bbox)
        return poly.contains(Point(cx, cy))  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        detections: List[Detection],
        timestamp: float,
    ) -> List[DwellEvent]:
        """
        Process detections for one frame and return any new dwell events.

        Parameters
        ----------
        detections:
            All detections for the current frame (only ``'person'`` class
            is considered).
        timestamp:
            Monotonic timestamp of the frame (e.g. ``time.monotonic()``).
            Used for dwell-time accumulation and cooldown tracking.

        Returns
        -------
        Possibly empty list of :class:`DwellEvent`.
        """
        events: List[DwellEvent] = []

        # Gather current person track_ids and their bboxes.
        active_ids: Dict[int, Tuple[int, int, int, int]] = {}
        for det in detections:
            if det.class_name.lower() == "person" and det.track_id >= 0:
                active_ids[det.track_id] = det.bbox
                self._last_bbox[det.track_id] = det.bbox

        # For each active person, check each zone.
        for track_id, bbox in active_ids.items():
            if track_id not in self._entry_times:
                self._entry_times[track_id] = {}
            if track_id not in self._last_event_time:
                self._last_event_time[track_id] = {}

            for zone_label, poly in self._zones:
                if self._in_zone(bbox, poly):
                    # Person is inside this zone.
                    if zone_label not in self._entry_times[track_id]:
                        # Just entered – record entry time.
                        self._entry_times[track_id][zone_label] = timestamp
                    else:
                        dwell = timestamp - self._entry_times[track_id][zone_label]
                        if dwell >= self._dwell_threshold:
                            last_evt = self._last_event_time[track_id].get(
                                zone_label, 0.0
                            )
                            if (timestamp - last_evt) >= self._cooldown:
                                self._last_event_time[track_id][zone_label] = timestamp
                                event = DwellEvent(
                                    camera_id=self._camera_id,
                                    track_id=track_id,
                                    zone_label=zone_label,
                                    dwell_seconds=round(dwell, 2),
                                    timestamp=datetime.now(tz=timezone.utc),
                                    bbox=bbox,
                                )
                                logger.warning(
                                    "DwellEvent | camera=%s track=%d zone='%s' dwell=%.1fs",
                                    self._camera_id,
                                    track_id,
                                    zone_label,
                                    dwell,
                                )
                                events.append(event)
                else:
                    # Person left the zone – clear entry time.
                    self._entry_times[track_id].pop(zone_label, None)

        # Clean up state for track_ids no longer active.
        gone_ids = set(self._entry_times.keys()) - set(active_ids.keys())
        for tid in gone_ids:
            del self._entry_times[tid]
            self._last_event_time.pop(tid, None)
            self._last_bbox.pop(tid, None)

        return events
