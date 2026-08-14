"""
jewelry_scene.py
================
Jewelry-counter "scene profile" for the Vantag platform.

A jewellery shop has no shelves: the merchandise sits in a display case /
tray on a counter and is handed across to customers by staff.  This module
defines the shared geometry contract — the *scene profile* — that the three
jewellery-specific detectors consume:

  * ``counter_polygon``   – the serving-counter surface (customer side)
  * ``tray_polygon``      – the display case / tray region a hand reaches into
  * ``case_polygon``      – alias for the display case used by grab-and-run
  * ``exit_polygon``      – the door / exit of the room
  * ``approach_polygon``  – optional approach corridor toward the counter
  * ``trays``             – optional list of labelled per-tray ROIs

A :class:`JewelryScene` provides polygon parsing, robust point-in-polygon
(ray-casting, no external geometry dependency), centroid math, and hand-
candidate estimation from a person detection.

Hand estimation: when a detection carries pose keypoints (COCO 17-point
layout) the wrists (indices 9 and 10) are used; otherwise the hands are
approximated from the person bounding box.  The bbox approximation is a
deliberately conservative geometric proxy — loading a pose model greatly
improves accuracy, but the detector must remain usable with the plain
detection model the pipeline already runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

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


Point2D = Tuple[float, float]
Polygon = List[Tuple[float, float]]

# COCO 17-keypoint layout. Arms are (elbow, wrist): left = (7, 9),
# right = (8, 10). The forearm direction (wrist − elbow) lets us project a
# point past the wrist toward the palm/fingertips — which is what actually
# dips into a display tray — instead of stopping at the wrist.
_WRIST_ELBOW_PAIRS = ((9, 7), (10, 8))  # (wrist_index, elbow_index)
_MIN_WRIST_CONF = 0.15
_MIN_ELBOW_CONF = 0.15
_HAND_EXTEND_FACTOR = 0.6  # extend this fraction of the forearm past the wrist

# MediaPipe Hands 21-landmark layout (per-finger precision).
_HAND_TIP_INDICES = (4, 8, 12, 16, 20)  # thumb..pinky fingertips
_HAND_WRIST_INDEX = 0
_MIN_HAND_CONF = 0.1  # MediaPipe visibility threshold for a fingertip


# ---------------------------------------------------------------------------
# Geometry helpers (pure Python, dependency-free)
# ---------------------------------------------------------------------------

def point_in_polygon(x: float, y: float, poly: Optional[Polygon]) -> bool:
    """Return True when (x, y) lies inside *poly* using ray casting.

    ``None`` / degenerate polygons are treated as "not inside" so a missing
    scene zone never silently means "the whole frame".
    """
    if not poly or len(poly) < 3:
        return False

    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            # Point is on the correct vertical span; check ray crossing.
            intersect_x = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < intersect_x:
                inside = not inside
        j = i
    return inside


def centroid(bbox: Tuple[int, int, int, int]) -> Point2D:
    """Return the centre of a bounding box ``(x1, y1, x2, y2)``."""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def distance(a: Point2D, b: Point2D) -> float:
    """Euclidean distance between two pixel points."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def parse_polygon(points: Sequence[Sequence[float]]) -> Optional[Polygon]:
    """Normalise a ``[[x, y], ...]`` list into ``[(x, y), ...]``.

    Returns ``None`` for anything with fewer than three vertices, which is
    the convention used throughout the jewellery detectors for "zone not
    configured".
    """
    if not points:
        return None
    parsed: List[Tuple[float, float]] = []
    for pt in points:
        try:
            parsed.append((float(pt[0]), float(pt[1])))
        except (TypeError, IndexError, ValueError):
            continue
    return parsed if len(parsed) >= 3 else None


# ---------------------------------------------------------------------------
# Hand estimation
# ---------------------------------------------------------------------------

def hand_points(detection: Detection) -> List[Point2D]:
    """Return candidate hand pixel points for a person detection.

    Prefers 21-point MediaPipe hand landmarks when
    ``detection.hand_landmarks`` is populated — the actual fingertip points
    (indices 4/8/12/16/20) give per-finger precision for tray reach detection.
    Falls back to COCO 17-point pose keypoints (wrists plus a point projected
    past the wrist along the forearm), and finally to a small set of
    bbox-proportional points — bottom corners/centre and mid-height sides —
    which is a conservative approximation for a standing person reaching
    toward a counter.
    """
    hands = getattr(detection, "hand_landmarks", None)
    if hands:
        points: List[Point2D] = []
        for hand in hands:
            if not isinstance(hand, (list, tuple)):
                continue
            for idx in _HAND_TIP_INDICES:
                if idx >= len(hand):
                    continue
                kp = hand[idx]
                if (
                    isinstance(kp, (list, tuple))
                    and len(kp) >= 3
                    and float(kp[2]) >= _MIN_HAND_CONF
                ):
                    points.append((float(kp[0]), float(kp[1])))
        if points:
            return points

    kps = getattr(detection, "keypoints", None)
    if kps:
        points: List[Point2D] = []
        for wrist_idx, elbow_idx in _WRIST_ELBOW_PAIRS:
            if wrist_idx >= len(kps):
                continue
            wrist = kps[wrist_idx]
            if not isinstance(wrist, (list, tuple)) or len(wrist) < 3:
                continue
            if float(wrist[2]) < _MIN_WRIST_CONF:
                continue
            wx, wy = float(wrist[0]), float(wrist[1])
            points.append((wx, wy))  # the wrist itself

            # Project past the wrist along the forearm toward the fingertips.
            if elbow_idx < len(kps):
                elbow = kps[elbow_idx]
                if (
                    isinstance(elbow, (list, tuple))
                    and len(elbow) >= 3
                    and float(elbow[2]) >= _MIN_ELBOW_CONF
                ):
                    ex, ey = float(elbow[0]), float(elbow[1])
                    points.append(
                        (
                            wx + _HAND_EXTEND_FACTOR * (wx - ex),
                            wy + _HAND_EXTEND_FACTOR * (wy - ey),
                        )
                    )
        if points:
            return points

    x1, y1, x2, y2 = detection.bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    return [
        (x1, y2),   # bottom-left
        (x2, y2),   # bottom-right
        (cx, y2),   # bottom-centre
        (x1, cy),   # mid-left
        (x2, cy),   # mid-right
    ]


def any_point_in(points: Sequence[Point2D], poly: Optional[Polygon]) -> bool:
    """Return True if any of *points* is inside *poly*."""
    if poly is None:
        return False
    return any(point_in_polygon(x, y, poly) for (x, y) in points)


# ---------------------------------------------------------------------------
# Scene profile
# ---------------------------------------------------------------------------

@dataclass
class JewelryScene:
    """Parsed jewellery-counter scene profile for a single camera."""

    counter_polygon: Optional[Polygon] = None
    tray_polygon: Optional[Polygon] = None
    case_polygon: Optional[Polygon] = None
    exit_polygon: Optional[Polygon] = None
    approach_polygon: Optional[Polygon] = None
    trays: List[Dict] = field(default_factory=list)
    """``[{"label": str, "polygon": [(x, y), ...]}]`` per-tray ROIs."""

    @classmethod
    def from_config(cls, config: Optional[Dict]) -> "JewelryScene":
        """Parse a scene profile from an analyzer-config dict.

        Expected keys (all optional):

        * ``counter_polygon``
        * ``tray_polygon``
        * ``case_polygon``
        * ``exit_polygon``
        * ``approach_polygon``
        * ``trays`` – list of ``{"label": str, "polygon": [[x, y], ...]}``
        """
        cfg = config or {}
        scene = cls(
            counter_polygon=parse_polygon(cfg.get("counter_polygon", [])),
            tray_polygon=parse_polygon(cfg.get("tray_polygon", [])),
            case_polygon=parse_polygon(cfg.get("case_polygon", [])),
            exit_polygon=parse_polygon(cfg.get("exit_polygon", [])),
            approach_polygon=parse_polygon(cfg.get("approach_polygon", [])),
        )
        for tray in cfg.get("trays", []) or []:
            if not isinstance(tray, dict):
                continue
            poly = parse_polygon(tray.get("polygon", []))
            if poly is not None:
                scene.trays.append(
                    {"label": str(tray.get("label", "tray")), "polygon": poly}
                )
        return scene

    def is_configured(self) -> bool:
        """True when at least one meaningful zone is present."""
        return bool(
            self.counter_polygon
            or self.tray_polygon
            or self.case_polygon
            or self.exit_polygon
            or self.approach_polygon
            or self.trays
        )
