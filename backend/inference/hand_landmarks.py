"""
backend/inference/hand_landmarks.py
===================================
MediaPipe HandLandmarker wrapper for 21-point per-finger hand tracking.

Used by the High-Value Counter ``jewelry_handover`` detector so a hand reach
into a display tray is measured from the *actual fingertips* (landmarks 4, 8,
12, 16, 20) rather than a bounding-box guess.

Uses the MediaPipe Tasks Python API (``mediapipe.tasks.python.vision``) — the
legacy ``mp.solutions`` API was removed in mediapipe 0.10.31+, so Tasks is the
only forward-compatible path.

The ``.task`` model bundle (palm detector + 21-landmark hand model) ships in
``models/hand_landmarker.task``.

Importing this module never raises when ``mediapipe`` is not installed: the
engine reports ``available=False`` and ``detect_hands()`` returns ``[]``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# MediaPipe Hands 21-landmark layout — indices of interest.
WRIST = 0
FINGERTIPS = (4, 8, 12, 16, 20)  # thumb, index, middle, ring, pinky tips

_DEFAULT_MODEL_PATH = "models/hand_landmarker.task"


@dataclass
class HandDetection:
    """One detected hand with its 21 landmarks in pixel coordinates."""

    handedness: str
    score: float
    landmarks: List[Tuple[float, float, float]]
    """21 ``(x, y, visibility)`` tuples in pixel coordinates."""

    def fingertips(self) -> List[Tuple[float, float]]:
        """Return the five fingertip pixel points (thumb..pinky)."""
        return [
            (self.landmarks[i][0], self.landmarks[i][1])
            for i in FINGERTIPS
        ]

    def wrist(self) -> Tuple[float, float]:
        x, y, _ = self.landmarks[WRIST]
        return (x, y)

    def bbox(self) -> Tuple[int, int, int, int]:
        """Bounding box of all 21 landmarks as ``(x1, y1, x2, y2)``."""
        xs = [p[0] for p in self.landmarks]
        ys = [p[1] for p in self.landmarks]
        return (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))


class HandLandmarkEngine:
    """Thin wrapper around MediaPipe's HandLandmarker (Tasks API)."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        max_hands: int = 2,
        min_confidence: float = 0.5,
    ) -> None:
        self._model_path = model_path or _DEFAULT_MODEL_PATH
        self._max_hands = int(max_hands)
        self._min_confidence = float(min_confidence)
        self._landmarker = None
        self._mp_image = None
        self._mp_format = None
        self.available = False
        self._load()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not os.path.isfile(self._model_path):
            logger.info(
                "HandLandmarkEngine skipped (model not found) | path=%s",
                self._model_path,
            )
            return
        try:
            import mediapipe as mp  # type: ignore[import]

            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=self._model_path),
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
            logger.info("HandLandmarkEngine loaded | model=%s", self._model_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "HandLandmarkEngine init failed (%s) – per-finger tracking disabled.",
                exc,
            )
            self._landmarker = None
            self.available = False

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def detect_hands(self, frame: np.ndarray) -> List[HandDetection]:
        """Detect hands in a BGR frame and return 21-point landmark sets.

        Returns an empty list when the engine is unavailable or no hands are
        detected.  Never raises.
        """
        if not self.available or self._landmarker is None:
            return []
        if frame is None or frame.size == 0 or frame.ndim < 2:
            return []

        try:
            rgb = np.ascontiguousarray(frame[:, :, ::-1])  # BGR → RGB
            mp_image = self._mp_image(
                image_format=self._mp_format.SRGB,
                data=rgb,
            )
            result = self._landmarker.detect(mp_image)
        except Exception as exc:  # noqa: BLE001
            logger.debug("HandLandmarkEngine.detect_hands failed: %s", exc)
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
            hands.append(HandDetection(handedness="Unknown", score=1.0, landmarks=pts))
        return hands
