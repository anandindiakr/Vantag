"""
jewelry_tray.py
===============
Jewellery tray change detector for the Vantag platform.

A close-up camera on a display tray lets us detect the *act* that matters in
jewellery retail: the tray contents change (an item is removed or shifted)
while a person is at the counter.  This is the jewellery analogue of the
empty-shelf detector, adapted to a small high-value tray rather than a shelf.

Detection logic per tray ROI:

1. A rolling foreground model (MOG2 background subtraction) produces a fill
   ratio for the tray region each ``check_interval_seconds``.
2. When the fill ratio drops by at least ``drop_ratio_threshold`` from the
   previously observed level, and (when ``person_required``) a person is
   near the counter, a :class:`TrayEvent` is emitted with a
   ``change_type`` of ``removed`` / ``appeared`` / ``changed``.

This is deliberately framed as a *change* detector, not an "item stolen"
proof: tiny reflective items are hard to count reliably, so the event is
gated by person presence and intended for operator review alongside the
handover and grab-and-run signals.
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
    centroid,
    parse_polygon,
    point_in_polygon,
)

try:
    import cv2  # type: ignore[import]
    _CV2_OK = True
except Exception:  # noqa: BLE001
    cv2 = None  # type: ignore[assignment]
    _CV2_OK = False


_DEFAULTS: Dict = {
    "trays": [],                   # [{"label": str, "polygon": [[x, y], ...]}]
    "counter_polygon": [],         # used for the person-present check
    "drop_ratio_threshold": 0.25,  # absolute fill-ratio delta to flag
    "check_interval_seconds": 3.0,
    "cooldown_seconds": 30.0,
    "person_required": True,
    "confidence_threshold": 0.45,
}


@dataclass
class TrayEvent:
    """Emitted when a tray's contents change significantly."""

    camera_id: str
    tray_label: str
    previous_fill: float
    current_fill: float
    change_type: str  # 'removed' | 'appeared' | 'changed'
    person_present: bool
    timestamp: datetime
    severity: str  # 'medium' | 'high' (uppercased by the pipeline)


class _TrayState:
    def __init__(self, label: str, polygon, bbox_rect: Tuple[int, int, int, int]) -> None:
        self.label = label
        self.polygon = polygon
        self.bbox_rect = bbox_rect  # (x, y, w, h)
        self.subtractor = None
        if _CV2_OK:
            try:
                self.subtractor = cv2.createBackgroundSubtractorMOG2(
                    history=200, varThreshold=50, detectShadows=False
                )
            except Exception:  # noqa: BLE001
                self.subtractor = None
        self.last_fill: Optional[float] = None
        self.last_check: float = 0.0
        self.last_event: float = 0.0


class JewelryTrayDetector:
    """Stateful tray change detector bound to a single camera."""

    def __init__(self, camera_id: str, config: Dict) -> None:
        self._camera_id = camera_id
        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._scene = JewelryScene.from_config(cfg)
        self._drop_threshold: float = float(cfg["drop_ratio_threshold"])
        self._check_interval: float = float(cfg["check_interval_seconds"])
        self._cooldown: float = float(cfg["cooldown_seconds"])
        self._person_required: bool = bool(cfg["person_required"])
        self._conf_thresh: float = float(cfg["confidence_threshold"])

        self._trays: List[_TrayState] = []
        for tray in cfg.get("trays", []) or []:
            if not isinstance(tray, dict):
                continue
            poly = parse_polygon(tray.get("polygon", []))
            if poly is None:
                continue
            rect = self._polygon_bbox(poly)
            self._trays.append(
                _TrayState(str(tray.get("label", "tray")), poly, rect)
            )

    @property
    def scene(self) -> JewelryScene:
        return self._scene

    @staticmethod
    def _polygon_bbox(poly) -> Tuple[int, int, int, int]:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        x, y = int(min(xs)), int(min(ys))
        w = int(max(xs)) - x
        h = int(max(ys)) - y
        return (x, y, w, h)

    def _extract_roi(self, frame, state: _TrayState):
        """Crop the tray bounding rectangle; returns None on any failure."""
        try:
            fh, fw = frame.shape[:2]
        except Exception:  # noqa: BLE001
            return None
        x, y, w, h = state.bbox_rect
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(fw, x + w), min(fh, y + h)
        if x2 <= x1 or y2 <= y1:
            return None
        try:
            return frame[y1:y2, x1:x2]
        except Exception:  # noqa: BLE001
            return None

    def _fill_ratio(self, state: _TrayState, roi) -> Optional[float]:
        """Return the foreground fill ratio (0..1) for a tray ROI.

        Returns ``None`` when OpenCV is unavailable or the ROI is empty.
        Kept as an instance method so tests can inject deterministic values.
        """
        if state.subtractor is None or roi is None:
            return None
        try:
            mask = state.subtractor.apply(roi)
            total = int(mask.size)
            if total == 0:
                return None
            try:
                import numpy as np
                fg = int(np.count_nonzero(mask))
            except Exception:  # noqa: BLE001
                fg = sum(1 for px in mask.flatten() if px)
            return fg / total
        except Exception:  # noqa: BLE001
            return None

    def _person_near_counter(self, detections: List[Detection]) -> bool:
        counter = self._scene.counter_polygon
        for det in detections:
            if det.class_name != "person" or det.confidence < self._conf_thresh:
                continue
            if counter is None:
                return True
            cx, cy = centroid(det.bbox)
            if point_in_polygon(cx, cy, counter):
                return True
        return False

    def analyze(
        self,
        frame,
        detections: List[Detection],
        timestamp: float,
    ) -> List[TrayEvent]:
        """Process one frame and return tray change events, if any."""
        if frame is None or not self._trays:
            return []

        events: List[TrayEvent] = []
        now = time.monotonic()
        person_present = self._person_near_counter(detections)

        if self._person_required and not person_present:
            # No one at the counter — skip checks entirely (avoid restock
            # and lighting-change false positives).
            return []

        for state in self._trays:
            if (now - state.last_check) < self._check_interval:
                continue
            state.last_check = now

            roi = self._extract_roi(frame, state)
            fill = self._fill_ratio(state, roi)
            if fill is None:
                continue

            if state.last_fill is None:
                # First observation — establish baseline, no event.
                state.last_fill = fill
                continue

            prev = state.last_fill
            state.last_fill = fill
            delta = prev - fill

            change_type: Optional[str] = None
            severity = "medium"
            if delta >= self._drop_threshold:
                change_type = "removed"
                severity = "high"
            elif -delta >= self._drop_threshold:
                change_type = "appeared"
            # Only flag "changed" on a meaningful (but below removal) delta to
            # avoid noise from lighting flicker.
            elif abs(delta) >= self._drop_threshold * 0.5:
                change_type = "changed"

            if change_type is None:
                continue
            if (now - state.last_event) < self._cooldown:
                continue

            state.last_event = now
            logger.warning(
                "TrayEvent | camera=%s tray='%s' change=%s fill=%.2f→%.2f person=%s",
                self._camera_id, state.label, change_type, prev, fill, person_present,
            )
            events.append(
                TrayEvent(
                    camera_id=self._camera_id,
                    tray_label=state.label,
                    previous_fill=round(prev, 4),
                    current_fill=round(fill, 4),
                    change_type=change_type,
                    person_present=person_present,
                    timestamp=datetime.now(tz=timezone.utc),
                    severity=severity,
                )
            )

        return events
