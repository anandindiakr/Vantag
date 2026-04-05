"""
empty_shelf.py
==============
Empty-shelf detector for the Vantag platform.

For each named shelf zone the detector:
1. Uses MOG2 background subtraction to compute the foreground (product)
   fill ratio within the zone bounding rectangle.
2. Optionally recognises explicit ``'empty shelf'`` detections from the
   YOLO model when the model vocabulary supports that class.
3. Emits a :class:`ShelfEvent` whenever the fill ratio drops below
   ``fill_ratio_threshold`` **and** ``check_interval_seconds`` has elapsed
   since the last check for that zone.

Severity levels:
    * ``'LOW'``      – fill_ratio in [threshold × 0.5, threshold)
    * ``'MEDIUM'``   – fill_ratio in [threshold × 0.2, threshold × 0.5)
    * ``'HIGH'``     – fill_ratio < threshold × 0.2
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shapely for zone polygon containment.
# ---------------------------------------------------------------------------

try:
    from shapely.geometry import box as shapely_box, Polygon  # type: ignore[import]
    _SHAPELY_OK = True
except ImportError:
    _SHAPELY_OK = False
    logger.warning(
        "empty_shelf: 'shapely' not installed — polygon zones unavailable. "
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
    "shelf_zones": [],               # [{"label": str, "polygon": [[x,y]…]}]
    "fill_ratio_threshold": 0.30,
    "check_interval_seconds": 10.0,
}


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class ShelfEvent:
    """Emitted when a shelf zone appears substantially empty."""

    camera_id: str
    shelf_zone: str
    fill_ratio: float
    timestamp: datetime
    severity: str  # 'LOW' | 'MEDIUM' | 'HIGH'


# ---------------------------------------------------------------------------
# _ZoneState – internal per-zone tracker
# ---------------------------------------------------------------------------

class _ZoneState:
    """Holds the MOG2 subtractor and timing state for one shelf zone."""

    def __init__(
        self,
        label: str,
        polygon: Optional[object],
        bbox_rect: Tuple[int, int, int, int],  # (x, y, w, h) bounding box of zone
    ) -> None:
        self.label = label
        self.polygon = polygon
        self.bbox_rect = bbox_rect
        self.subtractor: Any = cv2.createBackgroundSubtractorMOG2(
            history=200,
            varThreshold=50,
            detectShadows=False,
        )
        self.last_check_time: float = 0.0


# ---------------------------------------------------------------------------
# EmptyShelfDetector
# ---------------------------------------------------------------------------

class EmptyShelfDetector:
    """
    Stateful empty-shelf detector bound to a single camera.

    Parameters
    ----------
    camera_id:
        Identifier of the camera this detector is bound to.
    config:
        Dict of configuration overrides (see ``_DEFAULTS``).
    """

    def __init__(self, camera_id: str, config: Dict) -> None:
        self._camera_id = camera_id

        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._fill_threshold: float = float(cfg["fill_ratio_threshold"])
        self._check_interval: float = float(cfg["check_interval_seconds"])

        self._zones: List[_ZoneState] = []
        for zone_def in cfg.get("shelf_zones", []):
            label: str = zone_def.get("label", "shelf")
            pts: List[List[int]] = zone_def.get("polygon", [])
            poly = None
            bbox_rect = (0, 0, 0, 0)

            if len(pts) >= 3:
                arr = np.array(pts, dtype=np.int32)
                x, y, w, h = cv2.boundingRect(arr)
                bbox_rect = (x, y, w, h)
                if _SHAPELY_OK:
                    poly = Polygon(pts)

            self._zones.append(_ZoneState(label, poly, bbox_rect))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_fill_ratio(
        zone: _ZoneState,
        roi: np.ndarray,
    ) -> float:
        """
        Apply MOG2 to the zone ROI and return the foreground fill ratio.

        ``roi`` is the cropped BGR frame for the zone bounding rectangle.
        """
        if roi is None or roi.size == 0:
            return 0.0
        fg_mask = zone.subtractor.apply(roi)
        fg_pixels = int(np.count_nonzero(fg_mask))
        total_pixels = fg_mask.size
        if total_pixels == 0:
            return 0.0
        return fg_pixels / total_pixels

    def _severity(self, fill_ratio: float) -> str:
        t = self._fill_threshold
        if fill_ratio < t * 0.2:
            return "HIGH"
        if fill_ratio < t * 0.5:
            return "MEDIUM"
        return "LOW"

    def _extract_roi(
        self,
        frame: np.ndarray,
        zone: _ZoneState,
    ) -> Optional[np.ndarray]:
        """Crop the bounding rectangle of the zone from *frame*."""
        x, y, w, h = zone.bbox_rect
        fh, fw = frame.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(fw, x + w)
        y2 = min(fh, y + h)
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        timestamp: float,
    ) -> List[ShelfEvent]:
        """
        Analyse a single frame and return shelf events if any zones appear
        empty.

        Parameters
        ----------
        frame:
            BGR numpy array for the current frame.
        detections:
            YOLO detections; used to check for ``'empty shelf'`` class if
            present in the model's vocabulary.
        timestamp:
            Monotonic timestamp of the frame (``time.monotonic()``).

        Returns
        -------
        Possibly empty list of :class:`ShelfEvent`.
        """
        if frame is None or frame.size == 0:
            return []

        events: List[ShelfEvent] = []

        # Collect bounding boxes of explicit 'empty shelf' detections.
        empty_shelf_bboxes: List[Tuple[int, int, int, int]] = [
            det.bbox
            for det in detections
            if det.class_name.lower() in ("empty shelf", "empty_shelf")
        ]

        for zone in self._zones:
            if (timestamp - zone.last_check_time) < self._check_interval:
                continue  # Not time to check yet.

            zone.last_check_time = timestamp
            roi = self._extract_roi(frame, zone)
            if roi is None:
                continue

            fill_ratio = self._compute_fill_ratio(zone, roi)

            # Override with YOLO 'empty shelf' detection if available.
            if empty_shelf_bboxes and zone.bbox_rect != (0, 0, 0, 0):
                x, y, w, h = zone.bbox_rect
                zone_area = w * h
                if zone_area > 0:
                    for det_bbox in empty_shelf_bboxes:
                        # Check overlap with zone bounding rect.
                        dx1 = max(x, det_bbox[0])
                        dy1 = max(y, det_bbox[1])
                        dx2 = min(x + w, det_bbox[2])
                        dy2 = min(y + h, det_bbox[3])
                        if dx2 > dx1 and dy2 > dy1:
                            # A YOLO detection says this zone is empty —
                            # override to a low fill ratio.
                            fill_ratio = min(fill_ratio, 0.05)
                            break

            if fill_ratio < self._fill_threshold:
                severity = self._severity(fill_ratio)
                logger.warning(
                    "ShelfEvent | camera=%s zone='%s' fill=%.3f severity=%s",
                    self._camera_id,
                    zone.label,
                    fill_ratio,
                    severity,
                )
                events.append(
                    ShelfEvent(
                        camera_id=self._camera_id,
                        shelf_zone=zone.label,
                        fill_ratio=round(fill_ratio, 4),
                        timestamp=datetime.now(tz=timezone.utc),
                        severity=severity,
                    )
                )

        return events
