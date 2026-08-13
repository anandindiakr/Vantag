"""
High-Value Counter detectors for the Vantag Edge Agent.

Ported from the backend's ``backend/analyzers/`` jewellery modules
(``jewelry_scene.py`` / ``jewelry_handover.py`` / ``jewelry_tray.py`` /
``grab_and_run.py``) so the three vision-only jewellery signals run ON-BOX
(no shelves, no POS):

  jewelry_handover – a hand reaches into the display tray and withdraws
  jewelry_tray     – tray contents change while a person is at the counter
  grab_and_run     – fast case→exit traversal (grab-and-run snatch)

Polygon coordinates arrive from the backend's ``/api/edge/config`` response
normalized to 0-1 fractions of the camera's reference resolution and are
scaled to the current frame's pixel size at analyse time, so the detectors
work regardless of the RTSP stream's decoded resolution.

Hand positions use the bbox-proportional approximation (bottom corners /
centre and mid-height sides) — the same fallback the backend uses when a
detection carries no pose keypoints. The agent's ``BoundingBox`` objects do
not carry pose keypoints, so this conservative geometric proxy is used here.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger("vantag.jewelry")

Point2D = Tuple[float, float]
Polygon = List[Tuple[float, float]]


# ---------------------------------------------------------------------------
# Geometry helpers (pure Python, dependency-free — mirrors jewelry_scene.py)
# ---------------------------------------------------------------------------

def point_in_polygon(x: float, y: float, poly: Optional[Polygon]) -> bool:
    """Ray-casting point-in-polygon. ``None``/degenerate = not inside."""
    if not poly or len(poly) < 3:
        return False
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            intersect_x = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < intersect_x:
                inside = not inside
        j = i
    return inside


def centroid(bbox: Tuple[float, float, float, float]) -> Point2D:
    """Centre of a pixel-space bbox ``(x1, y1, x2, y2)``."""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def distance(a: Point2D, b: Point2D) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def parse_polygon(points) -> Optional[Polygon]:
    """Normalise a ``[[x, y], ...]`` list into ``[(x, y), ...]`` (≥3 points)."""
    if not isinstance(points, list) or len(points) < 3:
        return None
    parsed: List[Tuple[float, float]] = []
    for pt in points:
        try:
            parsed.append((float(pt[0]), float(pt[1])))
        except (TypeError, IndexError, ValueError):
            continue
    return parsed if len(parsed) >= 3 else None


def _pixel_poly(poly: Optional[Polygon], fw: int, fh: int) -> Optional[Polygon]:
    """Scale a normalized polygon to the current frame's pixel size."""
    if poly is None:
        return None
    return [(x * fw, y * fh) for x, y in poly]


def _pixel_bbox(p, fw: int, fh: int) -> Tuple[float, float, float, float]:
    """Convert an agent BoundingBox (normalized 0-1) to pixel ``(x1,y1,x2,y2)``."""
    return (p.x * fw, p.y * fh, (p.x + p.w) * fw, (p.y + p.h) * fh)


def _hand_points(bbox: Tuple[float, float, float, float]) -> List[Point2D]:
    """Bbox-proportional hand-candidate points (see jewelry_scene.hand_points)."""
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    return [
        (x1, y2),   # bottom-left
        (x2, y2),   # bottom-right
        (cx, y2),   # bottom-centre
        (x1, cy),   # mid-left
        (x2, cy),   # mid-right
    ]


def _snapshot(frame: np.ndarray) -> str:
    """Downsized JPEG evidence snapshot, matching the other edge detectors."""
    small = cv2.resize(frame, (320, 180))
    _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return base64.b64encode(buf.tobytes()).decode()


def _track_id(p) -> Optional[int]:
    tid = getattr(p, "track_id", None)
    return int(tid) if tid is not None else None


# ---------------------------------------------------------------------------
# Handover (reach-in → withdraw)
# ---------------------------------------------------------------------------

class JewelryHandoverDetector:
    """Flags a hand reaching into the tray and withdrawing.

    Emits ``jewelry_handover`` (severity high). Gated on ``tray_polygon``
    being configured; ``counter_polygon`` is the optional person gate.
    """

    def __init__(self, camera_id: str, config: Optional[dict], cooldown_sec: int = 30):
        cfg = config or {}
        self.camera_id = camera_id
        self._counter = parse_polygon(cfg.get("counter_polygon"))
        self._tray = parse_polygon(cfg.get("tray_polygon"))
        self._min_inside = int(cfg.get("min_hand_inside_frames", 2))
        self._cooldown = float(cfg.get("cooldown_seconds", cooldown_sec))
        self._conf_thresh = float(cfg.get("confidence_threshold", 0.45))
        self._require_at_counter = bool(cfg.get("require_person_at_counter", True))
        # track_id → {in, was, last_event}
        self._tracks: Dict[int, dict] = {}

    @property
    def configured(self) -> bool:
        return self._tray is not None

    def analyse(self, persons: list, frame: np.ndarray) -> Optional[dict]:
        if self._tray is None:
            return None
        fh, fw = frame.shape[:2]
        tray_px = _pixel_poly(self._tray, fw, fh)
        counter_px = _pixel_poly(self._counter, fw, fh)
        now = time.monotonic()
        result: Optional[dict] = None
        active: set = set()

        for p in persons:
            if p.label != "person" or p.confidence < self._conf_thresh:
                continue
            tid = _track_id(p)
            if tid is None:
                continue
            active.add(tid)
            track = self._tracks.setdefault(tid, {"in": 0, "was": False, "last_event": 0.0})
            bbox = _pixel_bbox(p, fw, fh)

            at_counter = True
            if self._require_at_counter and counter_px is not None:
                cx, cy = centroid(bbox)
                at_counter = point_in_polygon(cx, cy, counter_px)

            hand_inside = any(
                point_in_polygon(hx, hy, tray_px) for hx, hy in _hand_points(bbox)
            )

            if at_counter and hand_inside:
                track["in"] += 1
                track["was"] = True
                continue

            # Hand no longer inside → treat as a withdraw if it had been in long enough.
            if track["was"] and track["in"] >= self._min_inside:
                if (now - track["last_event"]) >= self._cooldown:
                    track["last_event"] = now
                    result = {
                        "camera_id": self.camera_id,
                        "event_type": "jewelry_handover",
                        "severity": "high",
                        "confidence": round(min(0.95, p.confidence + 0.05), 3),
                        "snapshot_b64": _snapshot(frame),
                        "metadata": {
                            "timestamp": int(time.time() * 1000),
                            "person_track_id": tid,
                            "frames_inside": track["in"],
                            "event_subtype": "reach_in_withdraw",
                            "bounding_boxes": [p.to_dict()],
                        },
                    }
            track["in"] = 0
            track["was"] = False

        for stale in set(self._tracks) - active:
            del self._tracks[stale]

        return result


# ---------------------------------------------------------------------------
# Tray change (foreground fill-ratio delta while a person is at the counter)
# ---------------------------------------------------------------------------

class JewelryTrayDetector:
    """Flags a significant change in a display tray's foreground fill ratio.

    Emits ``jewelry_tray`` (severity high for a removal, medium otherwise).
    Gated on at least one configured tray ROI; a per-tray MOG2 background
    subtractor establishes a rolling baseline, so a hand passing through does
    not look like an item leaving (the change must persist across checks).
    """

    def __init__(self, camera_id: str, config: Optional[dict], cooldown_sec: int = 30):
        cfg = config or {}
        self.camera_id = camera_id
        self._counter = parse_polygon(cfg.get("counter_polygon"))
        self._drop_threshold = float(cfg.get("drop_ratio_threshold", 0.25))
        self._check_interval = float(cfg.get("check_interval_seconds", 3.0))
        self._cooldown = float(cfg.get("cooldown_seconds", cooldown_sec))
        self._person_required = bool(cfg.get("person_required", True))
        self._conf_thresh = float(cfg.get("confidence_threshold", 0.45))
        self._trays: List[dict] = []
        for t in cfg.get("trays") or []:
            if not isinstance(t, dict):
                continue
            poly = parse_polygon(t.get("polygon"))
            if poly is None:
                continue
            self._trays.append({
                "label": str(t.get("label", "tray")),
                "polygon": poly,
                "subtractor": cv2.createBackgroundSubtractorMOG2(
                    history=200, varThreshold=50, detectShadows=False
                ),
                "last_fill": None,
                "last_check": 0.0,
                "last_event": 0.0,
            })

    @property
    def configured(self) -> bool:
        return bool(self._trays)

    def _person_near_counter(self, persons: list, fw: int, fh: int) -> bool:
        counter_px = _pixel_poly(self._counter, fw, fh)
        for p in persons:
            if p.label != "person" or p.confidence < self._conf_thresh:
                continue
            if counter_px is None:
                return True
            cx, cy = centroid(_pixel_bbox(p, fw, fh))
            if point_in_polygon(cx, cy, counter_px):
                return True
        return False

    def analyse(self, persons: list, frame: np.ndarray) -> Optional[dict]:
        if not self._trays:
            return None
        now = time.monotonic()
        fh, fw = frame.shape[:2]
        person_present = self._person_near_counter(persons, fw, fh)

        if self._person_required and not person_present:
            # No one at the counter — skip checks entirely (avoids restock /
            # lighting-change false positives), matching the backend.
            return None

        result: Optional[dict] = None
        for st in self._trays:
            if (now - st["last_check"]) < self._check_interval:
                continue
            st["last_check"] = now

            poly_px = _pixel_poly(st["polygon"], fw, fh)
            xs = [pt[0] for pt in poly_px]
            ys = [pt[1] for pt in poly_px]
            x1, y1 = max(0, int(min(xs))), max(0, int(min(ys)))
            x2, y2 = min(fw, int(max(xs))), min(fh, int(max(ys)))
            if x2 - x1 < 8 or y2 - y1 < 8:
                continue

            roi = frame[y1:y2, x1:x2]
            mask = st["subtractor"].apply(roi)
            total = int(mask.size)
            if total == 0:
                continue
            fill = float(np.count_nonzero(mask)) / total

            if st["last_fill"] is None:
                # First observation — establish baseline, no event.
                st["last_fill"] = fill
                continue

            prev = st["last_fill"]
            st["last_fill"] = fill
            delta = prev - fill

            change_type: Optional[str] = None
            severity = "medium"
            if delta >= self._drop_threshold:
                change_type = "removed"
                severity = "high"
            elif -delta >= self._drop_threshold:
                change_type = "appeared"
            elif abs(delta) >= self._drop_threshold * 0.5:
                change_type = "changed"

            if change_type is None:
                continue
            if (now - st["last_event"]) < self._cooldown:
                continue
            st["last_event"] = now

            log.warning(
                "jewelry_tray | cam=%s tray='%s' change=%s fill=%.2f→%.2f person=%s",
                self.camera_id, st["label"], change_type, prev, fill, person_present,
            )
            result = {
                "camera_id": self.camera_id,
                "event_type": "jewelry_tray",
                "severity": severity,
                "confidence": round(min(0.95, 0.5 + abs(delta)), 3),
                "snapshot_b64": _snapshot(frame),
                "metadata": {
                    "timestamp": int(time.time() * 1000),
                    "tray_label": st["label"],
                    "previous_fill": round(prev, 4),
                    "current_fill": round(fill, 4),
                    "change_type": change_type,
                    "person_present": person_present,
                },
            }

        return result


# ---------------------------------------------------------------------------
# Grab-and-run (fast case → exit traversal)
# ---------------------------------------------------------------------------

class GrabAndRunDetector:
    """Flags a fast case→exit traversal (possible grab-and-run).

    Emits ``grab_and_run`` (severity critical). Gated on both ``case_polygon``
    and ``exit_polygon``; ``approach_polygon`` is an optional approach gate.
    """

    def __init__(self, camera_id: str, config: Optional[dict], cooldown_sec: int = 30):
        cfg = config or {}
        self.camera_id = camera_id
        self._case = parse_polygon(cfg.get("case_polygon"))
        self._exit = parse_polygon(cfg.get("exit_polygon"))
        self._approach = parse_polygon(cfg.get("approach_polygon"))
        self._max_window = float(cfg.get("max_window_seconds", 8.0))
        self._min_speed = float(cfg.get("min_exit_speed_px_s", 120.0))
        self._cooldown = float(cfg.get("cooldown_seconds", cooldown_sec))
        self._conf_thresh = float(cfg.get("confidence_threshold", 0.45))
        # track_id → {case_time, case_pos, approach_seen, last_event}
        self._tracks: Dict[int, dict] = {}

    @property
    def configured(self) -> bool:
        return self._case is not None and self._exit is not None

    def analyse(self, persons: list, frame: np.ndarray) -> Optional[dict]:
        if not self.configured:
            return None
        fh, fw = frame.shape[:2]
        case_px = _pixel_poly(self._case, fw, fh)
        exit_px = _pixel_poly(self._exit, fw, fh)
        approach_px = _pixel_poly(self._approach, fw, fh)
        now = time.monotonic()
        result: Optional[dict] = None
        active: set = set()

        for p in persons:
            if p.label != "person" or p.confidence < self._conf_thresh:
                continue
            tid = _track_id(p)
            if tid is None:
                continue
            active.add(tid)
            tr = self._tracks.setdefault(
                tid, {"case_time": None, "case_pos": None, "approach_seen": False, "last_event": 0.0}
            )
            bbox = _pixel_bbox(p, fw, fh)
            center = centroid(bbox)

            in_case = point_in_polygon(*center, case_px)
            in_exit = point_in_polygon(*center, exit_px)

            if approach_px is not None:
                if point_in_polygon(*center, approach_px):
                    tr["approach_seen"] = True
                approach_ok = tr["approach_seen"]
            else:
                approach_ok = True

            if in_case and tr["case_time"] is None:
                tr["case_time"] = now
                tr["case_pos"] = center
                continue

            if tr["case_time"] is not None and in_exit:
                travel = now - tr["case_time"]
                speed = 0.0
                if tr["case_pos"] is not None and travel > 0:
                    speed = distance(center, tr["case_pos"]) / travel

                if (
                    approach_ok
                    and 0 < travel <= self._max_window
                    and speed >= self._min_speed
                    and (now - tr["last_event"]) >= self._cooldown
                ):
                    tr["last_event"] = now
                    result = {
                        "camera_id": self.camera_id,
                        "event_type": "grab_and_run",
                        "severity": "critical",
                        "confidence": round(min(0.95, 0.5 + speed / (self._min_speed * 4)), 3),
                        "snapshot_b64": _snapshot(frame),
                        "metadata": {
                            "timestamp": int(time.time() * 1000),
                            "person_track_id": tid,
                            "travel_seconds": round(travel, 2),
                            "exit_speed_px_s": round(speed, 1),
                            "bounding_boxes": [p.to_dict()],
                        },
                    }
                # Episode over — reset so a new approach can start fresh.
                tr["case_time"] = None
                tr["case_pos"] = None
                tr["approach_seen"] = False
                continue

            if tr["case_time"] is not None and (now - tr["case_time"]) > self._max_window:
                tr["case_time"] = None
                tr["case_pos"] = None
                tr["approach_seen"] = False

        for stale in set(self._tracks) - active:
            del self._tracks[stale]

        return result
