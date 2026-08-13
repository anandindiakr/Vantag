"""
jewelry_handover.py
===================
Jewellery hand-reach detector for the Vantag platform.

In a jewellery shop the theft act is a *hand* crossing into the display case
/ tray and withdrawing — not a product being swept off a shelf.  This
detector flags a ``reach-in → withdraw`` gesture:

1. A tracked person is at the counter (their centroid is inside
   ``counter_polygon``, when configured).
2. One of that person's estimated hand points enters ``tray_polygon`` and
   stays there for at least ``min_hand_inside_frames`` consecutive frames.
3. The hand then leaves the tray — this withdraw transition emits a
   :class:`HandoverEvent`.

Hand positions come from :func:`backend.analyzers.jewelry_scene.hand_points`
(pose wrists when available, otherwise a bbox-proportional approximation).
Because a single detector cannot distinguish a staff member servicing the
case from a customer, this signal is intentionally a *review candidate*:
it feeds the incident log with a conservative cooldown and is meant to be
confirmed by an operator, not treated as proof on its own.
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
    any_point_in,
    centroid,
    hand_points,
    point_in_polygon,
)


_DEFAULTS: Dict = {
    "counter_polygon": [],
    "tray_polygon": [],
    "min_hand_inside_frames": 2,
    "cooldown_seconds": 30.0,
    "confidence_threshold": 0.45,
    "require_person_at_counter": True,
}


@dataclass
class HandoverEvent:
    """Emitted when a hand reaches into the tray and withdraws."""

    camera_id: str
    person_track_id: int
    confidence: float
    bbox: Tuple[int, int, int, int]
    timestamp: datetime
    severity: str  # 'high' (uppercased by the pipeline)
    frames_inside: int
    event_subtype: str  # 'reach_in_withdraw'


class _PersonTrack:
    def __init__(self) -> None:
        self.hand_in_frames: int = 0
        self.was_inside: bool = False
        self.last_bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
        self.last_event_time: float = 0.0


class JewelryHandoverDetector:
    """Stateful reach-in/withdraw detector bound to a single camera."""

    def __init__(self, camera_id: str, config: Dict) -> None:
        self._camera_id = camera_id
        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._scene = JewelryScene.from_config(cfg)
        self._min_inside: int = int(cfg["min_hand_inside_frames"])
        self._cooldown: float = float(cfg["cooldown_seconds"])
        self._conf_thresh: float = float(cfg["confidence_threshold"])
        self._require_at_counter: bool = bool(cfg["require_person_at_counter"])

        self._tracks: Dict[int, _PersonTrack] = {}

    @property
    def scene(self) -> JewelryScene:
        return self._scene

    def analyze(
        self,
        frame: object,
        detections: List[Detection],
        timestamp: float,
    ) -> List[HandoverEvent]:
        """Process one frame's detections and return new handover events."""
        if frame is None or self._scene.tray_polygon is None:
            return []

        events: List[HandoverEvent] = []
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

            at_counter = True
            if self._require_at_counter and self._scene.counter_polygon is not None:
                cx, cy = centroid(person.bbox)
                at_counter = point_in_polygon(cx, cy, self._scene.counter_polygon)

            hand_inside = any_point_in(hand_points(person), self._scene.tray_polygon)

            if at_counter and hand_inside:
                track.hand_in_frames += 1
                track.was_inside = True
                continue

            # Hand not inside now — treat as a withdraw if it had been inside
            # long enough. Emit once per episode, subject to cooldown.
            if track.was_inside and track.hand_in_frames >= self._min_inside:
                if (now - track.last_event_time) >= self._cooldown:
                    track.last_event_time = now
                    events.append(
                        HandoverEvent(
                            camera_id=self._camera_id,
                            person_track_id=tid,
                            confidence=min(0.95, person.confidence + 0.05),
                            bbox=person.bbox,
                            timestamp=datetime.now(tz=timezone.utc),
                            severity="high",
                            frames_inside=track.hand_in_frames,
                            event_subtype="reach_in_withdraw",
                        )
                    )
            track.hand_in_frames = 0
            track.was_inside = False

        # Drop tracks that disappeared this frame.
        for stale in set(self._tracks) - active_ids:
            del self._tracks[stale]

        return events
