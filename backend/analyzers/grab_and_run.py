"""
grab_and_run.py
===============
Grab-and-run detector for the Vantag platform.

Detects the classic jewellery snatch sequence using pure person-track
geometry — no object detection required:

1. (Optional) the person is seen in ``approach_polygon``;
2. the person enters ``case_polygon`` (the counter / display case);
3. within ``max_window_seconds`` the person reaches ``exit_polygon`` (the
   door) moving faster than ``min_exit_speed_px_s``.

A fast, near-immediate case→exit traversal is behaviourally distinct from a
customer browsing and exiting at a normal pace, which is what makes this
signal useful without a POS integration.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from backend.inference.yolo_engine import Detection
except ImportError:
    from dataclasses import dataclass as _dc

    @_dc
    class Detection:  # type: ignore[no-redef]
        track_id: int = -1
        class_name: str = ""
        confidence: float = 0.0
        bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
        keypoints: Optional[list] = None

from backend.analyzers.jewelry_scene import (
    JewelryScene,
    Point2D,
    centroid,
    distance,
    point_in_polygon,
)


_DEFAULTS: Dict = {
    "case_polygon": [],
    "exit_polygon": [],
    "approach_polygon": [],
    "max_window_seconds": 8.0,
    "min_exit_speed_px_s": 120.0,
    "cooldown_seconds": 30.0,
    "confidence_threshold": 0.45,
}


@dataclass
class GrabAndRunEvent:
    """Emitted when a person moves case → exit unusually fast."""

    camera_id: str
    person_track_id: int
    confidence: float
    bbox: Tuple[int, int, int, int]
    timestamp: datetime
    severity: str  # 'critical' (uppercased by the pipeline)
    travel_seconds: float
    exit_speed_px_s: float


class _PersonTrack:
    def __init__(self) -> None:
        self.case_time: Optional[float] = None
        self.case_pos: Optional[Point2D] = None
        self.approach_seen: bool = False
        self.last_bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
        self.last_event_time: float = 0.0


class GrabAndRunDetector:
    """Stateful grab-and-run detector bound to a single camera."""

    def __init__(self, camera_id: str, config: Dict) -> None:
        self._camera_id = camera_id
        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._scene = JewelryScene.from_config(cfg)
        self._max_window: float = float(cfg["max_window_seconds"])
        self._min_speed: float = float(cfg["min_exit_speed_px_s"])
        self._cooldown: float = float(cfg["cooldown_seconds"])
        self._conf_thresh: float = float(cfg["confidence_threshold"])

        self._tracks: Dict[int, _PersonTrack] = {}

    @property
    def scene(self) -> JewelryScene:
        return self._scene

    def analyze(
        self,
        frame: object,
        detections: List[Detection],
        timestamp: float,
    ) -> List[GrabAndRunEvent]:
        """Process one frame's detections and return new grab-and-run events."""
        if frame is None or self._scene.case_polygon is None or self._scene.exit_polygon is None:
            return []

        events: List[GrabAndRunEvent] = []
        now = time.monotonic()

        persons = [
            d for d in detections
            if d.class_name == "person" and d.confidence >= self._conf_thresh
        ]

        active_ids = set()
        for person in persons:
            tid = person.track_id if person.track_id >= 0 else id(person)
            active_ids.add(tid)
            track = self._tracks.setdefault(tid, _PersonTrack())
            track.last_bbox = person.bbox

            center = centroid(person.bbox)
            in_case = point_in_polygon(*center, self._scene.case_polygon)
            in_exit = point_in_polygon(*center, self._scene.exit_polygon)

            # Optional approach gate: if an approach polygon is configured the
            # person must have passed through it before the case→exit run.
            if self._scene.approach_polygon is not None:
                if point_in_polygon(*center, self._scene.approach_polygon):
                    track.approach_seen = True
                approach_ok = track.approach_seen
            else:
                approach_ok = True

            # Record the moment the person arrives at the case.
            if in_case and track.case_time is None:
                track.case_time = now
                track.case_pos = center
                continue

            # Detect the case→exit traversal.
            if track.case_time is not None and in_exit:
                travel = now - track.case_time
                speed = 0.0
                if track.case_pos is not None and travel > 0:
                    speed = distance(center, track.case_pos) / travel

                if (
                    approach_ok
                    and 0 < travel <= self._max_window
                    and speed >= self._min_speed
                    and (now - track.last_event_time) >= self._cooldown
                ):
                    track.last_event_time = now
                    events.append(
                        GrabAndRunEvent(
                            camera_id=self._camera_id,
                            person_track_id=tid,
                            confidence=min(0.95, 0.5 + speed / (self._min_speed * 4)),
                            bbox=person.bbox,
                            timestamp=datetime.now(tz=timezone.utc),
                            severity="critical",
                            travel_seconds=round(travel, 2),
                            exit_speed_px_s=round(speed, 1),
                        )
                    )
                # Episode over — reset so a new approach can start fresh.
                track.case_time = None
                track.case_pos = None
                track.approach_seen = False
                continue

            # Expire a stale case entry that never made it to the exit.
            if track.case_time is not None and (now - track.case_time) > self._max_window:
                track.case_time = None
                track.case_pos = None
                track.approach_seen = False

        for stale in set(self._tracks) - active_ids:
            del self._tracks[stale]

        return events
