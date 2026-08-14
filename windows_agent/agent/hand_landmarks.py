"""
Hand landmark detection for the Vantag Edge Agent (21-point, per-finger).

Ported from ``backend/inference/hand_landmarks.py`` so the on-box
``jewelry_handover`` detector measures a reach from the *actual fingertips*
(landmarks 4, 8, 12, 16, 20) instead of a bounding-box guess — matching the
backend pipeline.

Uses the MediaPipe Tasks Python API (``mediapipe.tasks.python.vision``). The
module never raises when ``mediapipe`` is not installed or the model bundle is
missing: ``get_hand_detector()`` returns a detector whose ``available`` is
``False`` and ``detect()`` returns ``[]``, so the bbox fallback keeps working.

The ``hand_landmarker.task`` bundle is resolved from (in order):

  1. ``<agent>/../models/hand_landmarker.task``  (extracted download zip)
  2. ``<agent>/../../models/hand_landmarker.task`` (repo checkout)
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

log = logging.getLogger("vantag.hand_landmarks")

WRIST = 0
FINGERTIPS = (4, 8, 12, 16, 20)  # thumb, index, middle, ring, pinky tips

# MediaPipe Hands 21-landmark order (for reference / debugging):
# wrist(0), thumb_cmc..tip(1-4), index_mcp..tip(5-8), middle(9-12),
# ring(13-16), pinky(17-20).


def _candidate_model_paths() -> List[str]:
    here = Path(__file__).resolve()
    return [
        str(here.parent.parent / "models" / "hand_landmarker.task"),      # zip layout
        str(here.parent.parent.parent / "models" / "hand_landmarker.task"),  # repo layout
    ]


class HandDetection:
    """One detected hand with its 21 landmarks in pixel coordinates."""

    def __init__(self, landmarks: List[Tuple[float, float, float]]):
        self.landmarks = landmarks

    def fingertips(self) -> List[Tuple[float, float]]:
        return [
            (self.landmarks[i][0], self.landmarks[i][1]) for i in FINGERTIPS
        ]

    def bbox(self) -> Tuple[int, int, int, int]:
        xs = [p[0] for p in self.landmarks]
        ys = [p[1] for p in self.landmarks]
        return (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))


class HandLandmarkDetector:
    """Lazy, thread-safe MediaPipe HandLandmarker wrapper."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        max_hands: int = 2,
        min_confidence: float = 0.5,
    ):
        self._model_path = model_path
        self._max_hands = int(max_hands)
        self._min_confidence = float(min_confidence)
        self._landmarker = None
        self._mp_image = None
        self._mp_format = None
        self.available = False
        self._loaded = False
        self._lock = threading.Lock()

    def _load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            self._loaded = True

            path = self._model_path
            if not path:
                for cand in _candidate_model_paths():
                    if os.path.isfile(cand):
                        path = cand
                        break
            if not path or not os.path.isfile(path):
                log.info("HandLandmarkDetector skipped (model not found)")
                return

            try:
                import mediapipe as mp  # type: ignore[import]

                options = mp.tasks.vision.HandLandmarkerOptions(
                    base_options=mp.tasks.BaseOptions(model_asset_path=path),
                    running_mode=mp.tasks.vision.RunningMode.IMAGE,
                    num_hands=self._max_hands,
                    min_hand_detection_confidence=self._min_confidence,
                    min_hand_presence_confidence=self._min_confidence,
                    min_tracking_confidence=self._min_confidence,
                )
                self._landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
                self._mp_image = mp.Image
                self._mp_format = mp.ImageFormat
                self.available = True
                log.info("HandLandmarkDetector loaded | model=%s", path)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "HandLandmarkDetector init failed (%s) — per-finger tracking disabled.",
                    exc,
                )
                self._landmarker = None
                self.available = False

    def detect(self, frame: np.ndarray) -> List[HandDetection]:
        """Detect hands in a BGR frame. Returns [] when unavailable. Never raises."""
        if not self._loaded:
            self._load()
        if not self.available or self._landmarker is None:
            return []
        if frame is None or getattr(frame, "size", 0) == 0 or frame.ndim < 2:
            return []

        try:
            rgb = np.ascontiguousarray(frame[:, :, ::-1])  # BGR -> RGB
            mp_image = self._mp_image(image_format=self._mp_format.SRGB, data=rgb)
            result = self._landmarker.detect(mp_image)
        except Exception as exc:  # noqa: BLE001
            log.debug("HandLandmarkDetector.detect failed: %s", exc)
            return []

        hands: List[HandDetection] = []
        h, w = frame.shape[:2]
        for lm_list in result.hand_landmarks or []:
            pts: List[Tuple[float, float, float]] = []
            for lm in lm_list:
                pts.append(
                    (
                        float(lm.x) * w,
                        float(lm.y) * h,
                        float(getattr(lm, "visibility", 1.0) or 1.0),
                    )
                )
            hands.append(HandDetection(pts))
        return hands


_DETECTOR: Optional[HandLandmarkDetector] = None
_DETECTOR_LOCK = threading.Lock()


def get_hand_detector() -> HandLandmarkDetector:
    """Return a shared, lazily-created hand landmark detector singleton."""
    global _DETECTOR  # noqa: PLW0603
    if _DETECTOR is None:
        with _DETECTOR_LOCK:
            if _DETECTOR is None:
                _DETECTOR = HandLandmarkDetector()
    return _DETECTOR
