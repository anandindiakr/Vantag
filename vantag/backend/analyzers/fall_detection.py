"""
fall_detection.py
=================
Fall / person-down detector using YOLOv8-Pose keypoints or,
as a fallback, bounding-box aspect-ratio heuristics.

Pose-based method (preferred when keypoints available):
  - Hip keypoints drop below knee keypoints â†’ person is horizontal
  - Head keypoint at similar height to hip â†’ person is on ground

Aspect-ratio fallback (when no pose model):
  - Person bbox width > height * 1.4 â†’ likely horizontal (fallen)
  - Sustained for min_fallen_frames frames to avoid false positives
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
    "min_fallen_frames": 5,         # consecutive frames must be horizontal
    "aspect_ratio_threshold": 1.4,  # width/height ratio for bbox method
    "pose_confidence_threshold": 0.4,
    "cooldown_seconds": 45,
    "alert_severity": "critical",
}

# COCO keypoint indices
_KP_NOSE = 0
_KP_LEFT_HIP = 11
_KP_RIGHT_HIP = 12
_KP_LEFT_KNEE = 13
_KP_RIGHT_KNEE = 14
_KP_LEFT_ANKLE = 15
_KP_RIGHT_ANKLE = 16


@dataclass
class FallEvent:
    camera_id: str
    person_track_id: int
    method: str           # "pose" | "bbox_ratio"
    confidence: float
    bbox: Tuple[int, int, int, int]
    duration_frames: int
    timestamp: datetime
    severity: str


class FallDetector:
    def __init__(self, camera_id: str, config: Dict):
        self._camera_id = camera_id
        cfg = {**_DEFAULTS, **{k: v for k, v in config.items() if k in _DEFAULTS}}

        self._min_frames: int = int(cfg["min_fallen_frames"])
        self._ar_thresh: float = float(cfg["aspect_ratio_threshold"])
        self._kp_conf: float = float(cfg["pose_confidence_threshold"])
        self._cooldown: float = float(cfg["cooldown_seconds"])
        self._severity: str = cfg["alert_severity"]

        # track_id â†’ consecutive fallen frames
        self._fallen_frames: Dict[int, int] = {}
        self._last_event: Dict[int, float] = {}

    def _is_fallen_bbox(self, bbox: Tuple) -> bool:
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        if h <= 0:
            return False
        return (w / h) >= self._ar_thresh

    def _is_fallen_pose(self, keypoints: list) -> Tuple[bool, float]:
        """
        keypoints: list of [x, y, confidence] for 17 COCO keypoints.
        Returns (is_fallen, confidence).
        """
        if not keypoints or len(keypoints) < 17:
            return False, 0.0

        def kp(idx):
            k = keypoints[idx]
            return k[0], k[1], k[2] if len(k) > 2 else 1.0

        lhx, lhy, lhc = kp(_KP_LEFT_HIP)
        rhx, rhy, rhc = kp(_KP_RIGHT_HIP)
        lkx, lky, lkc = kp(_KP_LEFT_KNEE)
        rkx, rky, rkc = kp(_KP_RIGHT_KNEE)

        if min(lhc, rhc, lkc, rkc) < self._kp_conf:
            return False, 0.0

        hip_y = (lhy + rhy) / 2
        knee_y = (lky + rky) / 2

        # In image coords: y increases downward.
        # Standing: hip_y < knee_y (hips above knees)
        # Fallen: hip_y â‰ˆ knee_y or hip_y > knee_y
        if abs(hip_y - knee_y) < 30:  # within 30px â†’ horizontal
            conf = min(lhc, rhc, lkc, rkc)
            return True, float(conf)
        return False, 0.0

    def analyze(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        timestamp: float,
    ) -> List[FallEvent]:
        if frame is None:
            return []

        events: List[FallEvent] = []
        now = time.monotonic()
        persons = [d for d in detections if d.class_name == "person"]

        active_tids = set()
        for person in persons:
            tid = person.track_id if person.track_id >= 0 else id(person)
            active_tids.add(tid)

            fallen = False
            method = "bbox_ratio"
            confidence = 0.6

            # Try pose-based detection first
            if person.keypoints and len(person.keypoints) >= 17:
                fallen_pose, kp_conf = self._is_fallen_pose(person.keypoints)
                if fallen_pose:
                    fallen = True
                    method = "pose"
                    confidence = kp_conf

            # Fallback to aspect ratio
            if not fallen:
                if self._is_fallen_bbox(person.bbox):
                    fallen = True
                    method = "bbox_ratio"
                    confidence = 0.65

            if fallen:
                self._fallen_frames[tid] = self._fallen_frames.get(tid, 0) + 1
                if self._fallen_frames[tid] >= self._min_frames:
                    last = self._last_event.get(tid, 0.0)
                    if (now - last) >= self._cooldown:
                        self._last_event[tid] = now
                        events.append(FallEvent(
                            camera_id=self._camera_id,
                            person_track_id=tid,
                            method=method,
                            confidence=confidence,
                            bbox=person.bbox,
                            duration_frames=self._fallen_frames[tid],
                            timestamp=datetime.now(tz=timezone.utc),
                            severity=self._severity,
                        ))
                        logger.warning(
                            "FallEvent | cam=%s track=%d method=%s dur=%d frames",
                            self._camera_id, tid, method, self._fallen_frames[tid],
                        )
            else:
                self._fallen_frames.pop(tid, None)

        # Clean stale
        for stale in set(self._fallen_frames) - active_tids:
            self._fallen_frames.pop(stale, None)

        return events

