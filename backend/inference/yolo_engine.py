"""
yolo_engine.py
==============
Full YOLOv8 inference engine for the Vantag platform.

Wraps ``ultralytics.YOLO`` with integrated ByteTrack tracking.  Supports
both standard object detection and pose-estimation models.  Returns typed
``Detection`` dataclass objects to keep downstream consumers decoupled from
the ultralytics API surface.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detection dataclass
# ---------------------------------------------------------------------------

@dataclass
class Detection:
    """Single detected object (or pose skeleton) in one video frame."""

    track_id: int
    """Persistent ByteTrack identity; -1 when tracking is unavailable."""

    class_id: int
    """YOLO class integer index."""

    class_name: str
    """Human-readable class label, e.g. ``'person'``."""

    confidence: float
    """Detection confidence in [0, 1]."""

    bbox: Tuple[int, int, int, int]
    """Bounding box as ``(x1, y1, x2, y2)`` in pixel coordinates."""

    keypoints: Optional[List[Tuple[float, float, float]]] = field(default=None)
    """Pose keypoints as a list of ``(x, y, conf)`` tuples.  ``None`` for
    non-pose detections."""


# ---------------------------------------------------------------------------
# YOLOEngine
# ---------------------------------------------------------------------------

class YOLOEngine:
    """
    Wraps ``ultralytics.YOLO`` to provide a clean, typed inference interface.

    Parameters
    ----------
    model_path:
        Path to a ``.pt`` or ``.onnx`` YOLOv8 model file.
    device:
        Inference device string accepted by PyTorch / ultralytics, e.g.
        ``'cpu'``, ``'cuda'``, ``'cuda:0'``.
    conf_threshold:
        Minimum confidence for a detection to be returned.
    class_filter:
        Optional list of class *names* to keep; all other classes are
        discarded.  ``None`` means return every detected class.
    """

    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        conf_threshold: float = 0.5,
        class_filter: Optional[List[str]] = None,
    ) -> None:
        self._model_path = model_path
        self._device = device
        self._conf_threshold = conf_threshold
        self._class_filter: Optional[List[str]] = (
            [c.lower() for c in class_filter] if class_filter else None
        )
        self._model: Any = None
        self._class_names: Dict[int, str] = {}
        self._loaded: bool = False

        self._load_model()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Attempt to load the YOLO model; log a warning on failure."""
        if not os.path.isfile(self._model_path):
            logger.warning(
                "YOLOEngine: model file not found at '%s'. "
                "Inference calls will return empty lists.",
                self._model_path,
            )
            return

        try:
            from ultralytics import YOLO  # type: ignore[import]

            self._model = YOLO(self._model_path)
            # Warm-up move to device so the first real call is not delayed.
            self._model.to(self._device)
            # Cache class name mapping.
            if hasattr(self._model, "names"):
                self._class_names = dict(self._model.names)
            self._loaded = True
            logger.info(
                "YOLOEngine: loaded model '%s' on device '%s'.",
                self._model_path,
                self._device,
            )
        except ImportError:
            logger.error(
                "YOLOEngine: 'ultralytics' package is not installed. "
                "Install it with: pip install ultralytics"
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "YOLOEngine: failed to load model '%s': %s",
                self._model_path,
                exc,
            )

    def _class_name_for(self, class_id: int) -> str:
        return self._class_names.get(class_id, str(class_id))

    def _passes_filter(self, class_name: str) -> bool:
        if self._class_filter is None:
            return True
        return class_name.lower() in self._class_filter

    # ------------------------------------------------------------------
    # Inference helpers – shared between detect() and detect_pose()
    # ------------------------------------------------------------------

    def _run_tracked(self, frame: np.ndarray) -> Any:
        """Run model with ByteTrack and return raw ultralytics Results."""
        return self._model.track(
            source=frame,
            device=self._device,
            conf=self._conf_threshold,
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
        )

    def _run_untracked(self, frame: np.ndarray) -> Any:
        """Run model without tracking (fallback) and return Results."""
        return self._model.predict(
            source=frame,
            device=self._device,
            conf=self._conf_threshold,
            verbose=False,
        )

    @staticmethod
    def _safe_int_bbox(box_xyxy: Any) -> Tuple[int, int, int, int]:
        arr = box_xyxy.cpu().numpy().astype(int).tolist()
        return (int(arr[0]), int(arr[1]), int(arr[2]), int(arr[3]))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run YOLOv8 object detection with ByteTrack tracking on *frame*.

        Parameters
        ----------
        frame:
            BGR ``numpy.ndarray`` as produced by ``cv2.VideoCapture``.

        Returns
        -------
        List of :class:`Detection` objects, possibly empty.
        """
        if not self._loaded or frame is None or frame.size == 0:
            return []

        try:
            results = self._run_tracked(frame)
        except Exception as exc:  # noqa: BLE001
            logger.warning("YOLOEngine.detect: tracking failed (%s); falling back to predict.", exc)
            try:
                results = self._run_untracked(frame)
            except Exception as exc2:  # noqa: BLE001
                logger.error("YOLOEngine.detect: predict also failed: %s", exc2)
                return []

        detections: List[Detection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            for i, box in enumerate(boxes):
                class_id = int(box.cls[0].item())
                class_name = self._class_name_for(class_id)
                if not self._passes_filter(class_name):
                    continue
                confidence = float(box.conf[0].item())
                bbox = self._safe_int_bbox(box.xyxy[0])
                track_id: int = -1
                if box.id is not None:
                    track_id = int(box.id[0].item())
                detections.append(
                    Detection(
                        track_id=track_id,
                        class_id=class_id,
                        class_name=class_name,
                        confidence=confidence,
                        bbox=bbox,
                        keypoints=None,
                    )
                )
        return detections

    def detect_pose(self, frame: np.ndarray) -> List[Detection]:
        """
        Run YOLOv8-pose inference on *frame* and return detections that
        include keypoints as ``List[Tuple[x, y, conf]]``.

        The model referenced by ``model_path`` must be a pose-estimation
        variant (e.g. ``yolov8n-pose.pt``).

        Parameters
        ----------
        frame:
            BGR ``numpy.ndarray``.

        Returns
        -------
        List of :class:`Detection` with the ``keypoints`` field populated.
        """
        if not self._loaded or frame is None or frame.size == 0:
            return []

        try:
            results = self._run_tracked(frame)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "YOLOEngine.detect_pose: tracking failed (%s); falling back to predict.", exc
            )
            try:
                results = self._run_untracked(frame)
            except Exception as exc2:  # noqa: BLE001
                logger.error("YOLOEngine.detect_pose: predict also failed: %s", exc2)
                return []

        detections: List[Detection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue

            kpts_result = result.keypoints  # may be None for non-pose models

            for i, box in enumerate(boxes):
                class_id = int(box.cls[0].item())
                class_name = self._class_name_for(class_id)
                if not self._passes_filter(class_name):
                    continue
                confidence = float(box.conf[0].item())
                bbox = self._safe_int_bbox(box.xyxy[0])
                track_id: int = -1
                if box.id is not None:
                    track_id = int(box.id[0].item())

                # Extract keypoints for this detection instance.
                keypoints: Optional[List[Tuple[float, float, float]]] = None
                if kpts_result is not None and i < len(kpts_result.data):
                    raw_kpts = kpts_result.data[i].cpu().numpy()  # shape (K, 3)
                    keypoints = [
                        (float(kp[0]), float(kp[1]), float(kp[2]))
                        for kp in raw_kpts
                    ]

                detections.append(
                    Detection(
                        track_id=track_id,
                        class_id=class_id,
                        class_name=class_name,
                        confidence=confidence,
                        bbox=bbox,
                        keypoints=keypoints,
                    )
                )
        return detections
