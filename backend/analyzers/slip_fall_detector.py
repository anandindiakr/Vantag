"""
slip_fall_detector.py
=====================
Slip-and-fall / accident detector for the Vantag platform.

Uses pose-estimation keypoints (from YOLOv8-pose via ``detect_pose()``) to
determine the orientation of each tracked person's torso.  A person is
considered prone when the hip-to-shoulder vector is tilted more than
``(90° - prone_angle_threshold)`` from the vertical axis for
``confirmation_frames`` consecutive frames.

COCO keypoint indices used:
    5  – left shoulder
    6  – right shoulder
    11 – left hip
    12 – right hip

A fall episode is considered over when the person returns to an upright
posture.  Only one event is emitted per episode per track_id.
"""

from __future__ import annotations

import base64
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

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
# COCO keypoint index constants (YOLOv8-pose)
# ---------------------------------------------------------------------------

_KP_LEFT_SHOULDER = 5
_KP_RIGHT_SHOULDER = 6
_KP_LEFT_HIP = 11
_KP_RIGHT_HIP = 12

# Minimum keypoint confidence to use a keypoint.
_KP_CONF_MIN = 0.3

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULTS: Dict = {
    "prone_angle_threshold": 45.0,   # degrees from horizontal
    "confirmation_frames": 5,
}


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class AccidentEvent:
    """Emitted when a person is detected as having fallen."""

    camera_id: str
    track_id: int
    timestamp: datetime
    confidence: float
    keypoints_snapshot: List[Tuple[float, float, float]]
    """Keypoints at the moment the event was confirmed."""
    frame_b64: str
    """Base-64-encoded JPEG of the frame at the moment of confirmation."""


# ---------------------------------------------------------------------------
# _TrackState – per-person fall state machine
# ---------------------------------------------------------------------------

@dataclass
class _TrackState:
    prone_frame_count: int = 0
    event_emitted: bool = False   # True during current fall episode.
    last_angle: float = 90.0      # Upright = 90° from horizontal.


# ---------------------------------------------------------------------------
# SlipFallDetector
# ---------------------------------------------------------------------------

class SlipFallDetector:
    """
    Stateful slip-and-fall detector bound to a single camera.

    Parameters
    ----------
    camera_id:
        Identifier of the camera.
    config:
        Dict of configuration overrides (see ``_DEFAULTS``).
    """

    def __init__(self, camera_id: str, config: Dict) -> None:
        self._camera_id = camera_id

        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._prone_angle_thresh: float = float(cfg["prone_angle_threshold"])
        self._confirmation_frames: int = int(cfg["confirmation_frames"])

        # State machine per track_id.
        self._track_states: Dict[int, _TrackState] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _keypoint(
        keypoints: List[Tuple[float, float, float]],
        idx: int,
    ) -> Optional[Tuple[float, float]]:
        """Return (x, y) for keypoint *idx* if confidence is sufficient."""
        if idx >= len(keypoints):
            return None
        x, y, conf = keypoints[idx]
        if conf < _KP_CONF_MIN:
            return None
        return (x, y)

    def _body_angle(
        self,
        keypoints: List[Tuple[float, float, float]],
    ) -> Optional[float]:
        """
        Compute the angle (degrees) of the hip-to-shoulder midpoint vector
        measured from the horizontal axis.

        Returns ``None`` when insufficient keypoints are visible.
        """
        ls = self._keypoint(keypoints, _KP_LEFT_SHOULDER)
        rs = self._keypoint(keypoints, _KP_RIGHT_SHOULDER)
        lh = self._keypoint(keypoints, _KP_LEFT_HIP)
        rh = self._keypoint(keypoints, _KP_RIGHT_HIP)

        # Need at least one shoulder and one hip.
        shoulder = None
        if ls and rs:
            shoulder = ((ls[0] + rs[0]) / 2.0, (ls[1] + rs[1]) / 2.0)
        elif ls:
            shoulder = ls
        elif rs:
            shoulder = rs

        hip = None
        if lh and rh:
            hip = ((lh[0] + rh[0]) / 2.0, (lh[1] + rh[1]) / 2.0)
        elif lh:
            hip = lh
        elif rh:
            hip = rh

        if shoulder is None or hip is None:
            return None

        dx = shoulder[0] - hip[0]
        dy = shoulder[1] - hip[1]
        # In image coordinates y increases downward.  Upright person: dx≈0,
        # dy<0 (shoulder above hip).  Angle from horizontal:
        angle_rad = math.atan2(abs(dy), abs(dx))
        return math.degrees(angle_rad)  # 90° = fully upright

    @staticmethod
    def _frame_to_b64(frame: np.ndarray) -> str:
        """Encode a BGR frame as a base-64 JPEG string."""
        try:
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception:  # noqa: BLE001
            return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        detections: List[Detection],
        frame: np.ndarray,
        timestamp: float,
    ) -> List[AccidentEvent]:
        """
        Analyse one frame's pose detections and return fall events.

        Parameters
        ----------
        detections:
            Detections from :meth:`YOLOEngine.detect_pose`.  Must have the
            ``keypoints`` field populated.
        frame:
            BGR frame used for the event snapshot image.
        timestamp:
            Monotonic timestamp (unused but kept for API consistency).

        Returns
        -------
        List of :class:`AccidentEvent`, possibly empty.
        """
        events: List[AccidentEvent] = []
        active_ids: set = set()

        for det in detections:
            if det.class_name.lower() != "person":
                continue
            if det.track_id < 0 or det.keypoints is None:
                continue

            track_id = det.track_id
            active_ids.add(track_id)

            if track_id not in self._track_states:
                self._track_states[track_id] = _TrackState()

            state = self._track_states[track_id]
            angle = self._body_angle(det.keypoints)

            if angle is None:
                # Cannot determine orientation — do not count as prone.
                continue

            state.last_angle = angle
            is_prone = angle < self._prone_angle_thresh

            if is_prone:
                state.prone_frame_count += 1
            else:
                # Person has recovered; reset episode.
                state.prone_frame_count = 0
                state.event_emitted = False
                continue

            if (
                state.prone_frame_count >= self._confirmation_frames
                and not state.event_emitted
            ):
                state.event_emitted = True
                confidence = min(
                    1.0,
                    1.0 - (angle / self._prone_angle_thresh),
                )
                frame_b64 = self._frame_to_b64(frame) if frame is not None else ""
                logger.warning(
                    "AccidentEvent | camera=%s track=%d angle=%.1f°",
                    self._camera_id,
                    track_id,
                    angle,
                )
                events.append(
                    AccidentEvent(
                        camera_id=self._camera_id,
                        track_id=track_id,
                        timestamp=datetime.now(tz=timezone.utc),
                        confidence=round(confidence, 4),
                        keypoints_snapshot=list(det.keypoints),
                        frame_b64=frame_b64,
                    )
                )

        # Clean up stale track states.
        stale = set(self._track_states.keys()) - active_ids
        for tid in stale:
            del self._track_states[tid]

        return events
