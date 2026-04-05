"""
staff_monitor.py
================
Staff activity monitor for the Vantag platform.

Classifies each detected person as *staff* or *customer* by comparing the
dominant colour of their bounding-box region against the configured staff
uniform colour palette.  Comparison is performed in CIE LAB colour space
using Euclidean distance.

An alert is emitted when a named zone has had no staff present for longer
than ``unattended_threshold_seconds`` during configured peak hours.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shapely for zone containment.
# ---------------------------------------------------------------------------

try:
    from shapely.geometry import Point, Polygon  # type: ignore[import]
    _SHAPELY_OK = True
except ImportError:
    _SHAPELY_OK = False
    logger.warning(
        "staff_monitor: 'shapely' not installed — zone containment disabled."
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
    # List of hex colour strings, e.g. ['#0055A4', '#FFFFFF']
    "staff_zone_colors": [],
    "unattended_threshold_seconds": 120.0,
    # List of [start_hour, end_hour] ranges (24-hour), e.g. [[9, 12], [14, 18]]
    "peak_hours": [],
    "color_tolerance": 30.0,  # Max LAB Euclidean distance to be considered a match.
    # Zones: [{"label": str, "polygon": [[x,y]…]}]
    "zones": [],
}


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class StaffAlertEvent:
    """Emitted when a zone is unattended by staff during peak hours."""

    camera_id: str
    zone: str
    unattended_duration: float
    timestamp: datetime
    alert_type: str  # 'UNATTENDED_ZONE'


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _hex_to_bgr(hex_color: str) -> Tuple[int, int, int]:
    """Convert a CSS hex string (``'#RRGGBB'``) to a BGR tuple."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


def _bgr_to_lab(bgr: Tuple[int, int, int]) -> np.ndarray:
    """Convert a single BGR pixel to CIE LAB."""
    pixel = np.array([[list(bgr)]], dtype=np.uint8)
    lab = cv2.cvtColor(pixel, cv2.COLOR_BGR2LAB)
    return lab[0, 0].astype(np.float32)


def _dominant_bgr(roi: np.ndarray, n_colors: int = 1) -> Tuple[int, int, int]:
    """
    Return the dominant BGR colour of *roi* using k-means clustering.

    Falls back to the mean colour when k-means fails or ROI is too small.
    """
    if roi is None or roi.size == 0:
        return (0, 0, 0)

    pixels = roi.reshape(-1, 3).astype(np.float32)
    if len(pixels) < n_colors:
        mean = tuple(int(v) for v in np.mean(pixels, axis=0))
        return (mean[0], mean[1], mean[2])

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    try:
        _, labels, centers = cv2.kmeans(
            pixels,
            n_colors,
            None,
            criteria,
            attempts=3,
            flags=cv2.KMEANS_RANDOM_CENTERS,
        )
        # Pick the cluster with the most pixels.
        counts = np.bincount(labels.flatten())
        dominant_center = centers[np.argmax(counts)].astype(int)
        return (int(dominant_center[0]), int(dominant_center[1]), int(dominant_center[2]))
    except cv2.error:
        mean = tuple(int(v) for v in np.mean(pixels, axis=0))
        return (mean[0], mean[1], mean[2])


# ---------------------------------------------------------------------------
# _ZoneState – per-zone internal state
# ---------------------------------------------------------------------------

class _ZoneState:
    def __init__(self, label: str, polygon: Optional[object]) -> None:
        self.label = label
        self.polygon = polygon
        # Monotonic timestamp of the last frame where staff was observed.
        self.last_staff_seen: float = time.monotonic()
        self.alert_emitted: bool = False


# ---------------------------------------------------------------------------
# StaffMonitor
# ---------------------------------------------------------------------------

class StaffMonitor:
    """
    Stateful staff activity monitor bound to a single camera.

    Parameters
    ----------
    camera_id:
        Identifier of the camera.
    config:
        Configuration dict (see ``_DEFAULTS``).
    """

    def __init__(self, camera_id: str, config: Dict) -> None:
        self._camera_id = camera_id

        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._unattended_threshold: float = float(cfg["unattended_threshold_seconds"])
        self._color_tolerance: float = float(cfg["color_tolerance"])
        self._peak_hours: List[List[int]] = cfg.get("peak_hours", [])

        # Pre-convert staff colours to LAB.
        raw_colors: List[str] = cfg.get("staff_zone_colors", [])
        self._staff_lab_colors: List[np.ndarray] = []
        for hex_c in raw_colors:
            try:
                bgr = _hex_to_bgr(hex_c)
                self._staff_lab_colors.append(_bgr_to_lab(bgr))
            except Exception as exc:  # noqa: BLE001
                logger.warning("staff_monitor: invalid colour '%s': %s", hex_c, exc)

        # Build zone list.
        self._zones: List[_ZoneState] = []
        for zone_def in cfg.get("zones", []):
            label: str = zone_def.get("label", "zone")
            pts: List[List[int]] = zone_def.get("polygon", [])
            poly = None
            if _SHAPELY_OK and len(pts) >= 3:
                poly = Polygon(pts)
            self._zones.append(_ZoneState(label, poly))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_peak_hour(self, timestamp: float) -> bool:
        if not self._peak_hours:
            return True  # No restriction → always active.
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        hour = dt.hour
        for start, end in self._peak_hours:
            if start <= hour < end:
                return True
        return False

    def _is_staff(self, roi: np.ndarray) -> bool:
        if not self._staff_lab_colors or roi is None or roi.size == 0:
            return False
        dom_bgr = _dominant_bgr(roi)
        dom_lab = _bgr_to_lab(dom_bgr)
        for ref_lab in self._staff_lab_colors:
            dist = float(np.linalg.norm(dom_lab - ref_lab))
            if dist <= self._color_tolerance:
                return True
        return False

    @staticmethod
    def _centroid(bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _in_zone(
        self,
        bbox: Tuple[int, int, int, int],
        poly: Optional[object],
    ) -> bool:
        if poly is None:
            return True
        cx, cy = self._centroid(bbox)
        return poly.contains(Point(cx, cy))  # type: ignore[union-attr]

    def _extract_roi(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
    ) -> Optional[np.ndarray]:
        fh, fw = frame.shape[:2]
        x1, y1, x2, y2 = (
            max(0, bbox[0]),
            max(0, bbox[1]),
            min(fw, bbox[2]),
            min(fh, bbox[3]),
        )
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        detections: List[Detection],
        frame: np.ndarray,
        timestamp: float,
    ) -> List[StaffAlertEvent]:
        """
        Process one frame's detections and return staff alert events.

        Parameters
        ----------
        detections:
            All detections for the current frame.
        frame:
            BGR numpy frame used for colour sampling.
        timestamp:
            Wall-clock Unix timestamp (``time.time()``) for peak-hour checks.

        Returns
        -------
        List of :class:`StaffAlertEvent`, possibly empty.
        """
        events: List[StaffAlertEvent] = []
        now_mono = time.monotonic()

        # For each zone, determine if staff is present.
        zones_with_staff: set = set()

        for det in detections:
            if det.class_name.lower() != "person":
                continue
            roi = self._extract_roi(frame, det.bbox)
            if roi is None:
                continue
            if not self._is_staff(roi):
                continue
            # This person is classified as staff.
            for zone in self._zones:
                if self._in_zone(det.bbox, zone.polygon):
                    zones_with_staff.add(zone.label)

        # Update last-seen timestamps and check for alerts.
        for zone in self._zones:
            if zone.label in zones_with_staff:
                zone.last_staff_seen = now_mono
                zone.alert_emitted = False  # Staff returned — reset episode.
                continue

            unattended_duration = now_mono - zone.last_staff_seen

            if (
                unattended_duration >= self._unattended_threshold
                and not zone.alert_emitted
                and self._is_peak_hour(timestamp)
            ):
                zone.alert_emitted = True
                logger.warning(
                    "StaffAlertEvent | camera=%s zone='%s' unattended=%.1fs",
                    self._camera_id,
                    zone.label,
                    unattended_duration,
                )
                events.append(
                    StaffAlertEvent(
                        camera_id=self._camera_id,
                        zone=zone.label,
                        unattended_duration=round(unattended_duration, 2),
                        timestamp=datetime.now(tz=timezone.utc),
                        alert_type="UNATTENDED_ZONE",
                    )
                )

        return events
