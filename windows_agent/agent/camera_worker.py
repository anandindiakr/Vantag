"""
Per-camera RTSP worker thread.
Connects to an RTSP stream, runs YOLOv8 inference, and posts events to backend.

Analyzers implemented
---------------------
  shoplifting        – person near high-value item for >2s
  restricted_zone    – person stationary at same spot for >30s
  inventory_movement – no shelf item detected for >60s
  fall_detected      – person bounding-box aspect ratio transitions from tall→wide (h/w ≤ 0.75)
  loitering          – person in a coarse grid cell for >loiter_threshold_sec and still moving
"""
import base64
import collections
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional
from urllib.parse import quote, unquote

# Must be set BEFORE cv2 opens any capture: force TCP (no packet loss
# artifacts) and disable FFMPEG-side buffering so live view stays realtime.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;500000",
)

import cv2
import numpy as np

from .config import CameraConfig
from .api_client import VantagApiClient
from .inference import (
    YoloInference, RETAIL_CLASSES,
    YoloPoseInference, PersonPose,
    KP_L_SHOULDER, KP_R_SHOULDER, KP_L_WRIST, KP_R_WRIST, KP_L_HIP, KP_R_HIP,
    ProductCountDetector,
)
from .tracker import ByteTracker

log = logging.getLogger("vantag.camera")

# Matches rtsp://user:pass@host... and captures the userinfo portion so it
# can be safely percent-encoded before handing the URL to FFmpeg.
_RTSP_CREDS_RE = re.compile(r"^(rtsp://)([^:@/]+):([^@]*)@(.+)$")


def sanitize_rtsp_url(url: str) -> str:
    """
    Many NVR/IP-camera passwords contain characters (most commonly '#')
    that are reserved in URIs. FFmpeg/OpenCV parse the RTSP URL as a
    standard URI, so an un-encoded '#' is treated as a fragment delimiter
    and silently truncates everything after it (e.g. the port/path),
    producing "Port missing in uri" even though the credentials are
    otherwise correct.

    This normalizes the username/password by unquoting first (a no-op if
    they were already raw) and then re-quoting with safe='' , so both
    already-encoded and raw values converge on the same, correctly
    escaped URL. Idempotent — safe to call every time a stream is opened.
    """
    if not url:
        return url
    m = _RTSP_CREDS_RE.match(url.strip())
    if not m:
        return url
    scheme, user, pwd, rest = m.groups()
    safe_user = quote(unquote(user), safe="")
    safe_pwd = quote(unquote(pwd), safe="")
    return f"{scheme}{safe_user}:{safe_pwd}@{rest}"

# Shared executor for fire-and-forget live-frame pushes to the backend relay.
# Bounded worker count so a slow/unreachable backend can't spawn unbounded
# threads across many cameras; a full queue simply drops the newest push
# (handled per-camera via the in-flight flag below), never blocking capture.
_FRAME_PUSH_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="frame-push")

# Person-centric event types eligible for staff face suppression on the
# backend. Crowding is excluded (multi-person, no single identity).
STAFF_FACE_EVENTS = {
    "shoplifting",
    "restricted_zone",
    "loitering",
    "suspicious_behavior",
    "fall_detected",
}

# ---------------------------------------------------------------------------
# Fall Detector
# ---------------------------------------------------------------------------

class FallDetector:
    """
    Detects falls by tracking bounding-box aspect ratio transitions.

    A standing person has h/w >= STAND_RATIO.
    A fallen person has h/w <= FALL_RATIO.

    We track a rolling window of aspect ratios per coarse grid cell and emit
    'fall_detected' when the ratio transitions from standing to fallen.
    """

    STAND_RATIO = 1.10   # h/w threshold for "upright"
    FALL_RATIO  = 0.75   # h/w threshold for "fallen"
    HISTORY_LEN = 24     # frames (~9.6 s at 2.5 AI fps)

    def __init__(self, camera_id: str, cooldown_sec: int = 60):
        self.camera_id = camera_id
        self._cooldown = max(cooldown_sec, 60)
        # cell → deque of aspect ratios
        self._history: dict[str, collections.deque] = {}
        self._last_event: dict[str, float] = {}

    def _cell(self, p) -> str:
        """Coarse 4×4 grid cell key for a bounding box."""
        cx = int(min(p.x + p.w / 2, 0.999) * 4)
        cy = int(min(p.y + p.h / 2, 0.999) * 4)
        return f"{cx}_{cy}"

    def analyse(self, persons: list, frame: np.ndarray) -> Optional[dict]:
        now = time.time()
        for p in persons:
            ratio = p.h / p.w if p.w > 0 else 1.5
            cell = self._cell(p)
            dq = self._history.setdefault(cell, collections.deque(maxlen=self.HISTORY_LEN))
            dq.append(ratio)

            # Need at least half the window filled before judging
            if len(dq) < self.HISTORY_LEN // 2:
                continue

            prev_ratios = list(dq)[:-3]   # older portion
            recent_ratios = list(dq)[-3:]  # last 3 readings

            was_standing = any(r >= self.STAND_RATIO for r in prev_ratios)
            is_fallen    = all(r <= self.FALL_RATIO for r in recent_ratios)

            if was_standing and is_fallen:
                last = self._last_event.get(cell, 0)
                if now - last >= self._cooldown:
                    self._last_event[cell] = now
                    small = cv2.resize(frame, (320, 180))
                    _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
                    snap = base64.b64encode(buf.tobytes()).decode()
                    return {
                        "camera_id": self.camera_id,
                        "event_type": "fall_detected",
                        "severity": "high",
                        "confidence": round(p.confidence, 3),
                        "snapshot_b64": snap,
                        "metadata": {
                            "timestamp": int(now * 1000),
                            "aspect_ratio": round(ratio, 3),
                            "bounding_boxes": [p.to_dict()],
                        },
                    }
        return None


# ---------------------------------------------------------------------------
# Loitering Detector
# ---------------------------------------------------------------------------

class LoiteringDetector:
    """
    Detects loitering: a person present in the same coarse grid zone for an
    extended period AND still moving (not simply standing still like dwell).

    Uses a 3×3 grid. Tracks per-cell presence start time and position variance.
    """

    MIN_PRESENCE_SEC = 90    # seconds in zone before alert
    MIN_MOVEMENT     = 0.06  # normalised position variance threshold

    def __init__(self, camera_id: str, cooldown_sec: int = 90):
        self.camera_id = camera_id
        self._cooldown = max(cooldown_sec, 90)
        # cell → {"first_seen": float, "positions": deque[(cx, cy)], "last_event": float}
        self._zones: dict[str, dict] = {}

    def _cell(self, p) -> str:
        cx = int(min(p.x + p.w / 2, 0.999) * 3)
        cy = int(min(p.y + p.h / 2, 0.999) * 3)
        return f"{cx}_{cy}"

    def analyse(self, persons: list, frame: np.ndarray) -> Optional[dict]:
        now = time.time()
        seen_cells: set[str] = set()

        for p in persons:
            cell = self._cell(p)
            seen_cells.add(cell)
            cx = p.x + p.w / 2
            cy = p.y + p.h / 2

            if cell not in self._zones:
                self._zones[cell] = {
                    "first_seen": now,
                    "positions": collections.deque(maxlen=50),
                    "last_event": 0.0,
                }
            zone = self._zones[cell]
            zone["positions"].append((cx, cy))

            dwell = now - zone["first_seen"]
            if dwell < self.MIN_PRESENCE_SEC:
                continue

            # Check movement variance
            positions = list(zone["positions"])
            if len(positions) < 5:
                continue
            xs = [pos[0] for pos in positions]
            ys = [pos[1] for pos in positions]
            variance = (max(xs) - min(xs)) + (max(ys) - min(ys))
            if variance <= self.MIN_MOVEMENT:
                continue  # standing still — handled by restricted_zone

            last = zone["last_event"]
            if now - last >= self._cooldown:
                zone["last_event"] = now
                small = cv2.resize(frame, (320, 180))
                _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
                snap = base64.b64encode(buf.tobytes()).decode()
                return {
                    "camera_id": self.camera_id,
                    "event_type": "loitering",
                    "severity": "low",
                    "confidence": round(min(dwell / (self.MIN_PRESENCE_SEC * 2), 0.95), 3),
                    "snapshot_b64": snap,
                    "metadata": {
                        "timestamp": int(now * 1000),
                        "dwell_seconds": round(dwell, 1),
                        "movement_variance": round(variance, 4),
                        "bounding_boxes": [p.to_dict()],
                    },
                }

        # Expire zones where no person was seen this frame
        for cell in list(self._zones.keys()):
            if cell not in seen_cells:
                del self._zones[cell]

        return None


# ---------------------------------------------------------------------------
# Crowd Detector
# ---------------------------------------------------------------------------

class CrowdDetector:
    """
    Detects crowding: person count stays at/above a threshold for a sustained
    window. Uses a rolling count history so a single noisy frame doesn't fire.

    Emits 'crowding' (canonical backend type).
    """

    MIN_PERSONS   = 5     # >= this many people = potential crowd
    SUSTAIN_SEC   = 5.0   # must hold for this long before firing

    def __init__(self, camera_id: str, cooldown_sec: int = 60, min_persons: int = MIN_PERSONS):
        self.camera_id = camera_id
        self._cooldown = max(cooldown_sec, 60)
        self._min_persons = min_persons
        self._crowd_since: Optional[float] = None
        self._last_event: float = 0.0

    def analyse(self, persons: list, frame: np.ndarray) -> Optional[dict]:
        now = time.time()
        count = len(persons)

        if count >= self._min_persons:
            if self._crowd_since is None:
                self._crowd_since = now
            elif now - self._crowd_since >= self.SUSTAIN_SEC:
                if now - self._last_event >= self._cooldown:
                    self._last_event = now
                    small = cv2.resize(frame, (320, 180))
                    _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
                    snap = base64.b64encode(buf.tobytes()).decode()
                    # Confidence scales with how far over the threshold we are
                    conf = min(0.5 + 0.1 * (count - self._min_persons), 0.95)
                    return {
                        "camera_id": self.camera_id,
                        "event_type": "crowding",
                        "severity": "high" if count >= self._min_persons * 2 else "medium",
                        "confidence": round(conf, 3),
                        "snapshot_b64": snap,
                        "metadata": {
                            "timestamp": int(now * 1000),
                            "person_count": count,
                            "threshold": self._min_persons,
                            "bounding_boxes": [p.to_dict() for p in persons],
                        },
                    }
        else:
            self._crowd_since = None

        return None


# ---------------------------------------------------------------------------
# Suspicious Behavior Detector
# ---------------------------------------------------------------------------

class SuspiciousBehaviorDetector:
    """
    Detects suspicious behavior via erratic movement: a person who repeatedly
    reverses horizontal direction (pacing / casing an area) within a coarse
    grid cell. Distinct from loitering (slow drift) and dwell (stationary).

    Emits 'suspicious_behavior' (canonical backend type).
    """

    HISTORY_LEN      = 20    # rolling window of centre-x positions per cell
    MIN_REVERSALS    = 4     # direction changes within the window to flag
    MIN_AMPLITUDE    = 0.04  # each swing must span at least this (normalised)

    def __init__(self, camera_id: str, cooldown_sec: int = 60):
        self.camera_id = camera_id
        self._cooldown = max(cooldown_sec, 60)
        self._tracks: dict[str, collections.deque] = {}
        self._last_event: dict[str, float] = {}

    def _cell(self, p) -> str:
        cx = int(min(p.x + p.w / 2, 0.999) * 4)
        cy = int(min(p.y + p.h / 2, 0.999) * 4)
        return f"{cx}_{cy}"

    def analyse(self, persons: list, frame: np.ndarray) -> Optional[dict]:
        now = time.time()
        seen: set[str] = set()

        for p in persons:
            cell = self._cell(p)
            seen.add(cell)
            cx = p.x + p.w / 2
            dq = self._tracks.setdefault(cell, collections.deque(maxlen=self.HISTORY_LEN))
            dq.append(cx)

            if len(dq) < self.HISTORY_LEN:
                continue

            reversals = self._count_reversals(list(dq))
            if reversals >= self.MIN_REVERSALS:
                last = self._last_event.get(cell, 0)
                if now - last >= self._cooldown:
                    self._last_event[cell] = now
                    small = cv2.resize(frame, (320, 180))
                    _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
                    snap = base64.b64encode(buf.tobytes()).decode()
                    return {
                        "camera_id": self.camera_id,
                        "event_type": "suspicious_behavior",
                        "severity": "medium",
                        "confidence": round(min(0.5 + 0.1 * reversals, 0.95), 3),
                        "snapshot_b64": snap,
                        "metadata": {
                            "timestamp": int(now * 1000),
                            "direction_reversals": reversals,
                            "bounding_boxes": [p.to_dict()],
                        },
                    }

        # Drop tracks for cells with no person this frame
        for cell in list(self._tracks.keys()):
            if cell not in seen:
                del self._tracks[cell]
                self._last_event.pop(cell, None)

        return None

    def _count_reversals(self, xs: list) -> int:
        """Count significant horizontal direction changes in a position series."""
        reversals = 0
        direction = 0          # -1 left, +1 right, 0 unknown
        anchor = xs[0]
        for x in xs[1:]:
            delta = x - anchor
            if abs(delta) < self.MIN_AMPLITUDE:
                continue
            new_dir = 1 if delta > 0 else -1
            if direction != 0 and new_dir != direction:
                reversals += 1
            direction = new_dir
            anchor = x
        return reversals


# ---------------------------------------------------------------------------
# Pose-based Concealment Shoplifting Detector
# ---------------------------------------------------------------------------

class PoseShopliftingDetector:
    """
    Concealment-gesture shoplifting detection using body pose keypoints
    (YOLOv8n-pose). Complements the proximity-based heuristic: it looks at
    WHAT the person is doing with their hands, not just where they stand.

    Heuristic: a wrist that dips below the hip line AND stays close to the
    body's vertical centerline (hand tucked at waist/pocket/bag rather than
    swinging naturally at the side) for several consecutive pose frames is a
    concealment gesture — slipping an item into a waistband, pocket or bag.

    Pose inference runs at most once per POSE_INTERVAL seconds to keep CPU
    usage bounded regardless of the main inference fps.
    """

    POSE_INTERVAL    = 1.0    # seconds between pose runs (CPU budget)
    CONCEAL_FRAMES   = 3      # consecutive pose frames showing the gesture
    CENTER_TOLERANCE = 0.25   # wrist within this fraction of box width from centerline

    def __init__(self, camera_id: str, pose_inference: "YoloPoseInference", cooldown_sec: int = 60):
        self.camera_id = camera_id
        self._pose = pose_inference
        self._cooldown = max(cooldown_sec, 60)
        self._last_run: float = 0.0
        self._last_event: dict[str, float] = {}
        # cell → consecutive gesture-frame count
        self._streaks: dict[str, int] = {}

    def _cell(self, box) -> str:
        cx = int(min(box.x + box.w / 2, 0.999) * 4)
        cy = int(min(box.y + box.h / 2, 0.999) * 4)
        return f"{cx}_{cy}"

    @staticmethod
    def _gesture(person: "PersonPose") -> Optional[str]:
        """Return 'left'/'right' if that wrist shows a concealment gesture."""
        l_hip = person.kp(KP_L_HIP)
        r_hip = person.kp(KP_R_HIP)
        hips = [h for h in (l_hip, r_hip) if h is not None]
        if not hips:
            return None
        hip_y = sum(h[1] for h in hips) / len(hips)

        l_sh = person.kp(KP_L_SHOULDER)
        r_sh = person.kp(KP_R_SHOULDER)
        shoulders = [s for s in (l_sh, r_sh) if s is not None]
        if shoulders:
            center_x = sum(s[0] for s in shoulders) / len(shoulders)
        else:
            center_x = person.box.x + person.box.w / 2

        tol = PoseShopliftingDetector.CENTER_TOLERANCE * max(person.box.w, 1e-4)

        for side, kp_idx in (("left", KP_L_WRIST), ("right", KP_R_WRIST)):
            wrist = person.kp(kp_idx)
            if wrist is None:
                continue
            wx, wy = wrist
            # Below the hip line AND tucked toward the body centerline
            if wy > hip_y and abs(wx - center_x) < tol:
                return side
        return None

    def analyse(self, frame: np.ndarray) -> Optional[dict]:
        if self._pose is None or self._pose._session is None:
            return None
        now = time.time()
        if now - self._last_run < self.POSE_INTERVAL:
            return None
        self._last_run = now

        poses = self._pose.detect_poses(frame, conf_threshold=0.4)
        seen: set[str] = set()
        result: Optional[dict] = None

        for person in poses:
            cell = self._cell(person.box)
            seen.add(cell)
            side = self._gesture(person)
            if side is None:
                self._streaks[cell] = 0
                continue

            self._streaks[cell] = self._streaks.get(cell, 0) + 1
            if self._streaks[cell] < self.CONCEAL_FRAMES:
                continue

            last = self._last_event.get(cell, 0)
            if now - last < self._cooldown:
                continue
            self._last_event[cell] = now
            self._streaks[cell] = 0

            small = cv2.resize(frame, (320, 180))
            _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
            snap = base64.b64encode(buf.tobytes()).decode()
            result = {
                "camera_id": self.camera_id,
                "event_type": "shoplifting",
                "severity": "high",
                "confidence": round(person.box.confidence, 3),
                "snapshot_b64": snap,
                "metadata": {
                    "timestamp": int(now * 1000),
                    "detection_method": "pose_concealment",
                    "wrist_side": side,
                    "bounding_boxes": [person.box.to_dict()],
                    "pose": person.to_dict(),
                },
            }

        # Reset streaks for cells with no person this pose frame
        for cell in list(self._streaks.keys()):
            if cell not in seen:
                del self._streaks[cell]

        return result


# ---------------------------------------------------------------------------
# Detection Analyzer (orchestrates all sub-detectors)
# ---------------------------------------------------------------------------

class DetectionAnalyzer:
    """
    Orchestrates per-frame detection results and decides when to emit events.

    Events emitted (canonical backend types):
      shoplifting         – person near high-value item for >2s
      restricted_zone     – person stationary in sensitive zone for >30s
      inventory_movement  – no shelf item for >60s
      fall_detected       – aspect-ratio transition standing→fallen
      loitering           – person in zone >90s while still moving
      crowding            – person count >= threshold sustained for >5s
      suspicious_behavior – person pacing / reversing direction in a zone
    """

    _SEVERITY_MAP = {
        "shoplifting":         "high",
        "restricted_zone":     "medium",
        "inventory_movement":  "medium",
        "fall_detected":       "high",
        "loitering":           "low",
        "crowding":            "medium",
        "suspicious_behavior": "medium",
    }

    # Inventory-zone occupancy-change tuning (Tier 1 fix). ``CHANGE_THRESHOLD``
    # is a 0-1 dissimilarity score (1 - grayscale histogram correlation)
    # between a zone's baseline crop and its current crop; empirically,
    # ordinary lighting flicker/shadow movement stays well under 0.35 while a
    # product genuinely removed/added produces a much larger jump.
    # ``DEBOUNCE_SEC`` requires the change to persist (not just one noisy
    # frame) before a candidate event is raised, mirroring the dwell-counter
    # pattern used by restricted_zone/loitering above.
    _INVENTORY_CHANGE_THRESHOLD = 0.35
    _INVENTORY_DEBOUNCE_SEC = 5.0
    # Shelf zones drawn in the UI are usually much wider than a single
    # product slot. Comparing one histogram over the WHOLE zone dilutes a
    # single item's removal into noise. Subdividing into a grid of cells and
    # tracking a baseline PER CELL makes a single-slot removal a much larger
    # (reliably detectable) fraction of that cell's own histogram.
    _INVENTORY_GRID_ROWS = 2
    _INVENTORY_GRID_COLS = 3
    # Max age (seconds) of a "last person seen at this cell" photo that's
    # still considered plausibly relevant evidence for a later-confirmed
    # change. Longer than this and the photo is dropped rather than shown,
    # since it could no longer represent who actually made the change.
    _INVENTORY_PERSON_EVIDENCE_MAX_AGE_SEC = 120.0

    def __init__(
        self,
        camera_id: str,
        cooldown_sec: int = 30,
        fps: float = 5.0,
        pose_inference: Optional["YoloPoseInference"] = None,
        people_count_zones: Optional[list[dict]] = None,
        exclusion_zones: Optional[list[dict]] = None,
        inventory_zones: Optional[list[dict]] = None,
        detections: Optional[dict] = None,
        product_count_detector: Optional["ProductCountDetector"] = None,
    ):
        self.camera_id = camera_id
        self.cooldown_sec = cooldown_sec
        self.fps = fps
        # Per-camera opt-in analytic toggles from the backend config.
        # These heuristics (pose shoplifting, loitering, crowding,
        # suspicious behaviour, fall) are OFF unless explicitly enabled for
        # this camera in the dashboard — exactly matching the backend's
        # OPT_IN_EVENT_TYPES gate on ingest. Running them regardless (the
        # previous behaviour) meant every camera paid for pose inference and
        # then had its events silently discarded server-side, which made a
        # test in front of a camera with the analytic switched OFF look
        # identical to a broken detector.
        self._detections: dict = dict(detections or {})
        self._last_event: dict[str, float] = {}
        # {key: [first_seen, last_seen]} — last_seen enables the continuous-
        # presence (temporal smoothing) check in analyse() below (v1.5.1):
        # without it, a single stray overlap frame months apart could
        # accumulate toward the 2s dwell threshold across unrelated visits.
        self._person_with_items: dict[str, list] = {}
        self._person_frame_counts: dict[str, int] = {}
        self._person_dwell_last_seen: dict[str, float] = {}
        self._shelf_empty_since: Optional[float] = None
        # Max gap (seconds) tolerated between consecutive detections of the
        # same dwell/proximity key before it's treated as a NEW encounter
        # rather than a continuation. ~7-8 missed frames at 5fps — enough to
        # survive brief occlusion/motion-blur misses without letting
        # disjoint, unrelated visits accumulate toward an alert threshold.
        self._continuity_grace_sec = 1.5

        # Live person count from the most recent analysed frame (footfall)
        self.last_person_count: int = 0
        # Rolling (timestamp, count) window so the 30s heartbeat reports the
        # PEAK count seen in the interval instead of whatever single frame
        # happened to be analysed last (people are often mid-stride/occluded
        # in one frame — a single-frame sample constantly flickers to 0).
        self._count_window: collections.deque = collections.deque(maxlen=600)
        # Zone-filtered count of the most recent frame. When a people-count
        # zone is drawn (e.g. across the doorway) this counts only persons
        # inside it — used for ENTRIES (footfall), NOT for the live count.
        self.last_zone_count: int = 0
        self._entry_window: collections.deque = collections.deque(maxlen=600)
        # Cumulative "visitors today" — increments every time the debounced
        # zone occupancy RISES (someone entered the view/zone). Resets at
        # local midnight. Unlike the live count this never drops back to 0
        # when people leave, which is what a footfall dashboard actually needs.
        self.entries_today: int = 0
        self._entries_day: str = time.strftime("%Y-%m-%d")
        # Persistent-ID tracker (v1.5.0) — replaces the old occupancy-rise
        # heuristic. Each confirmed track is counted as a visitor exactly
        # ONCE, the first time it appears inside the count zone, instead of
        # inferring entries from the occupancy number going up or down
        # (which could not tell "2 people walked in" from "1 person walked
        # in then out" — both look like a rise then a fall).
        self._tracker = ByteTracker()
        self._counted_track_ids: set[int] = set()

        self._fall_detector = FallDetector(camera_id, cooldown_sec)
        self._loiter_detector = LoiteringDetector(camera_id, cooldown_sec)
        self._crowd_detector = CrowdDetector(camera_id, cooldown_sec)
        self._suspicious_detector = SuspiciousBehaviorDetector(camera_id, cooldown_sec)
        self._pose_detector: Optional[PoseShopliftingDetector] = (
            PoseShopliftingDetector(camera_id, pose_inference, cooldown_sec)
            if pose_inference is not None else None
        )
        self._people_count_zones = people_count_zones or []
        # ROI masking (Tier 3 add-on): zones EXCLUDED from all detection —
        # e.g. a public sidewalk visible through a storefront window, a
        # mirror/TV reflecting people, or an out-of-scope neighboring aisle.
        # Any box whose center falls inside one of these is dropped before
        # any alert/count logic runs (see _filter_exclusions below).
        self._exclusion_zones = exclusion_zones or []

        # Shelf/inventory-movement zones (Zone Editor "Shelf" type), fed to
        # the agent by main.py's _map_remote_camera/_build_worker. Each zone
        # gets its own rolling baseline crop + debounce state so an edit to
        # one shelf zone doesn't disturb another.
        self._inventory_zones = inventory_zones or []
        self._inventory_baseline_hist: dict[str, "np.ndarray"] = {}
        self._inventory_baseline_crop: dict[str, np.ndarray] = {}
        self._inventory_change_since: dict[str, float] = {}
        self._inventory_change_last_seen: dict[str, float] = {}
        # Last moment a person was seen overlapping each cell + a JPEG of
        # the full frame at that moment, so an inventory_movement event
        # (which by design only fires once the zone is person-free) can
        # still attach a photo of whoever was last there, instead of
        # showing no one at all in the evidence.
        self._inventory_last_person_seen: dict[str, float] = {}
        self._inventory_last_person_jpeg: dict[str, bytes] = {}
        # Frame-level (not per-cell) fallback evidence: the last time ANY
        # person was visible anywhere in this camera's frame, plus that
        # frame's JPEG. A person reaching into a shelf is often detected
        # with a bbox that does not overlap the specific small grid cell
        # they disturbed (arm reaches in, body stands to the side), which
        # left confirmed changes with no person photo at all. This gives
        # every inventory event a person image to show whenever a person
        # was recently visible on that camera.
        self._inventory_frame_person_seen: float = 0.0
        self._inventory_frame_person_jpeg: Optional[bytes] = None
        # Tier 2: open-vocabulary product counter (YOLO-World), shared
        # singleton passed in from main.py. Only invoked at the exact
        # moment Tier 1's CV signal proposes a candidate change (see
        # _analyze_inventory_zones below) — never per-frame. May be None
        # (model unavailable) — Tier 1 must keep working unaffected.
        self._product_count_detector = product_count_detector

    def _can_emit(self, event_type: str) -> bool:
        last = self._last_event.get(event_type, 0)
        return (time.time() - last) >= self.cooldown_sec

    def _emit(
        self,
        event_type: str,
        confidence: float,
        boxes: list,
        frame: np.ndarray,
        extra_metadata: Optional[dict] = None,
        cooldown_key: Optional[str] = None,
    ) -> Optional[dict]:
        # By default the cooldown gate is keyed by event_type alone (one
        # slot per camera). Callers that manage several independent
        # sub-regions for the SAME event_type (e.g. one inventory zone per
        # shelf grid cell) can pass a more specific ``cooldown_key`` so an
        # unrelated cell's noise can't block/delay a genuine change in a
        # different cell — this is what caused Tier-1 shelf events to
        # appear at the wrong grid cell and/or minutes late.
        gate_key = cooldown_key or event_type
        if not self._can_emit(gate_key):
            return None
        self._last_event[gate_key] = time.time()
        small = cv2.resize(frame, (320, 180))
        _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        snap = base64.b64encode(buf.tobytes()).decode()
        severity = self._SEVERITY_MAP.get(event_type, "medium")
        if confidence >= 0.85 and severity == "medium":
            severity = "high"
        metadata = {
            "timestamp": int(time.time() * 1000),
            "bounding_boxes": [b.to_dict() for b in boxes],
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        return {
            "camera_id": self.camera_id,
            "event_type": event_type,
            "severity": severity,
            "confidence": round(confidence, 3),
            "snapshot_b64": snap,
            "metadata": metadata,
        }

    def _in_exclusion_zone(self, box, frame_w: int, frame_h: int) -> bool:
        """True if ``box``'s center falls inside any configured exclusion
        (ROI mask) zone. Mirrors the normalized-vs-pixel bbox handling used
        by ``_count_people`` for people-count zones."""
        if not self._exclusion_zones:
            return False
        center_x = (box.x + box.w / 2) * frame_w
        center_y = (box.y + box.h / 2) * frame_h
        for zone in self._exclusion_zones:
            bbox = zone.get("bbox", [])
            if len(bbox) != 4:
                continue
            x1, y1, x2, y2 = (float(v) for v in bbox)
            if zone.get("normalized") or max(x1, y1, x2, y2) <= 1.0:
                x1, x2 = x1 * frame_w, x2 * frame_w
                y1, y2 = y1 * frame_h, y2 * frame_h
            if x1 <= center_x <= x2 and y1 <= center_y <= y2:
                return True
        return False

    def _filter_exclusions(self, boxes: list, frame_w: int, frame_h: int) -> list:
        if not self._exclusion_zones or not boxes:
            return boxes
        return [b for b in boxes if not self._in_exclusion_zone(b, frame_w, frame_h)]

    @staticmethod
    def _zone_pixel_bbox(zone: dict, frame_w: int, frame_h: int) -> Optional[tuple]:
        """Convert a stored zone bbox (normalized 0-1 or raw pixels) to pixel
        coordinates in the CURRENT frame's resolution. Mirrors the
        normalized-vs-pixel handling used by ``_in_exclusion_zone``."""
        bbox = zone.get("bbox", [])
        if len(bbox) != 4:
            return None
        x1, y1, x2, y2 = (float(v) for v in bbox)
        if zone.get("normalized") or max(x1, y1, x2, y2) <= 1.0:
            x1, x2 = x1 * frame_w, x2 * frame_w
            y1, y2 = y1 * frame_h, y2 * frame_h
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(frame_w, int(x2)), min(frame_h, int(y2))
        if x2 - x1 < 20 or y2 - y1 < 20:
            return None
        return x1, y1, x2, y2

    @staticmethod
    def _zone_has_person(bbox_px: tuple, persons: list, frame_w: int, frame_h: int) -> bool:
        """True if any person box overlaps this shelf zone right now. A
        shopper merely standing in front of a shelf (browsing) produces the
        exact same "occlusion" as someone removing an item in a single
        frame — the only reliable way to tell them apart without a
        multi-second track is to skip evaluation entirely while a person is
        present and only judge the change once they've stepped away."""
        zx1, zy1, zx2, zy2 = bbox_px
        for p in persons:
            px1, py1 = p.x * frame_w, p.y * frame_h
            px2, py2 = (p.x + p.w) * frame_w, (p.y + p.h) * frame_h
            ox1, oy1 = max(zx1, px1), max(zy1, py1)
            ox2, oy2 = min(zx2, px2), min(zy2, py2)
            if ox2 > ox1 and oy2 > oy1:
                return True
        return False

    def _is_enabled(self, key: str) -> bool:
        """Is this opt-in behaviour analytic switched on for this camera?

        Mirrors the backend's OPT_IN_EVENT_TYPES gate. Absent key => OFF,
        which is deliberate: these heuristics are opt-in, and defaulting
        them on is what previously flooded the incident feed.

        If the backend sent no ``detections`` block at all (older backend,
        or the camera has never been configured) we fall back to running
        everything, exactly as before, and let the backend be the single
        authority — a config-delivery gap must never silently disable
        detection that the dashboard shows as enabled.
        """
        if not self._detections:
            return True
        return bool(self._detections.get(key))

    def _analyze_inventory_zones(self, persons: list, frame: np.ndarray, now: float) -> list[dict]:
        """Real Tier-1 shelf/inventory-movement detection.

        For each configured shelf zone, subdivides it into a grid of cells
        (``_INVENTORY_GRID_ROWS`` x ``_INVENTORY_GRID_COLS``) and tracks a
        rolling baseline histogram PER CELL, not per whole zone. A shelf
        zone is usually much wider than a single product slot, so comparing
        the whole zone's histogram diluted a single item's removal into
        noise — the grid keeps each comparison scoped to roughly one
        product-slot's worth of pixels, making a single-item removal a much
        bigger (and reliably detectable) fraction of that cell's histogram.

        Each cell keeps a rolling baseline crop (captured whenever no person
        overlaps that cell) and compares each new person-free frame's crop
        against it using a cheap grayscale histogram correlation. A
        sustained dissimilarity (not a single noisy frame) raises a
        candidate ``inventory_movement`` event carrying BOTH the baseline
        and current crops, so the backend's VLM verification step can
        confirm a genuine change vs. normal restocking before any alert is
        dispatched.
        """
        if not self._inventory_zones:
            return []
        events: list[dict] = []
        fh, fw = frame.shape[:2]
        seen_keys: set[str] = set()

        # Frame-level person evidence (fallback for the per-cell capture).
        # Throttled to ~2s so we don't re-encode a JPEG every frame.
        if persons and now - self._inventory_frame_person_seen >= 2.0:
            try:
                _, _fbuf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                self._inventory_frame_person_jpeg = _fbuf.tobytes()
                self._inventory_frame_person_seen = now
            except Exception:  # noqa: BLE001
                pass
        elif persons:
            self._inventory_frame_person_seen = now

        for idx, zone in enumerate(self._inventory_zones):
            zone_key = str(zone.get("id") or idx)
            seen_keys.add(zone_key)
            bbox_px = self._zone_pixel_bbox(zone, fw, fh)
            if bbox_px is None:
                continue

            zx1, zy1, zx2, zy2 = bbox_px
            zone_w, zone_h = zx2 - zx1, zy2 - zy1
            rows, cols = self._INVENTORY_GRID_ROWS, self._INVENTORY_GRID_COLS
            if zone_w < 60 or zone_h < 60:
                # Too small to subdivide meaningfully — treat as one cell.
                rows, cols = 1, 1

            # Collect this pass's confirmed candidates for the whole zone
            # FIRST, then decide. Emitting inside the cell loop meant a
            # single global scene change (someone walking past, camera
            # auto-exposure, lights switching) tripped every cell at once
            # and produced one incident per cell — reporting several
            # different "locations" for one real event, which is worse
            # than useless to the operator.
            candidates: list[dict] = []
            evaluated_cells = 0

            for r in range(rows):
                for c in range(cols):
                    cx1 = zx1 + int(zone_w * c / cols)
                    cx2 = zx1 + int(zone_w * (c + 1) / cols)
                    cy1 = zy1 + int(zone_h * r / rows)
                    cy2 = zy1 + int(zone_h * (r + 1) / rows)
                    if cx2 - cx1 < 10 or cy2 - cy1 < 10:
                        continue
                    key = f"{zone_key}:{r}_{c}"

                    if self._zone_has_person((cx1, cy1, cx2, cy2), persons, fw, fh):
                        # Remember who was last standing here (full frame,
                        # not just the tight crop) so a later confirmed
                        # change can still show a person, even though this
                        # detector only judges the shelf once they've left.
                        # Throttled to once every ~2s to avoid re-encoding a
                        # full JPEG on every frame while someone browses.
                        last_capture = self._inventory_last_person_seen.get(key, 0)
                        if now - last_capture >= 2.0:
                            _, person_buf = cv2.imencode(
                                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
                            )
                            self._inventory_last_person_jpeg[key] = person_buf.tobytes()
                        self._inventory_last_person_seen[key] = now
                        continue

                    evaluated_cells += 1
                    crop = frame[cy1:cy2, cx1:cx2]
                    gray = cv2.cvtColor(cv2.resize(crop, (64, 64)), cv2.COLOR_BGR2GRAY)
                    hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
                    cv2.normalize(hist, hist)

                    baseline_hist = self._inventory_baseline_hist.get(key)
                    if baseline_hist is None:
                        # First person-free look at this cell — establish
                        # baseline, nothing to compare against yet.
                        self._inventory_baseline_hist[key] = hist
                        self._inventory_baseline_crop[key] = crop.copy()
                        continue

                    similarity = cv2.compareHist(baseline_hist, hist, cv2.HISTCMP_CORREL)
                    change_score = 1.0 - max(-1.0, min(1.0, similarity))

                    if change_score < self._INVENTORY_CHANGE_THRESHOLD:
                        # Back to looking like baseline — any in-progress
                        # streak was noise (lighting flicker etc.), not a
                        # real change.
                        self._inventory_change_since.pop(key, None)
                        self._inventory_change_last_seen.pop(key, None)
                        continue

                    first_seen = self._inventory_change_since.get(key)
                    if first_seen is None:
                        first_seen = now
                        self._inventory_change_since[key] = first_seen
                    self._inventory_change_last_seen[key] = now

                    if now - first_seen >= self._INVENTORY_DEBOUNCE_SEC:
                        candidates.append({
                            "key": key,
                            "row": r,
                            "col": c,
                            "bbox": (cx1, cy1, cx2, cy2),
                            "crop": crop,
                            "hist": hist,
                            "change_score": change_score,
                        })

            if not candidates:
                continue

            # A real item removal affects ONE product slot. If most of the
            # zone's cells changed at the same time it is a whole-scene
            # change (lighting, auto-exposure, camera moved, large occlusion)
            # — not inventory movement. Re-baseline everything and stay
            # silent rather than emitting a burst of misleading incidents.
            if evaluated_cells >= 3 and len(candidates) >= max(2, int(evaluated_cells * 0.6)):
                log.info(
                    "Inventory: suppressed whole-scene change on zone '%s' "
                    "(%d/%d cells changed together — lighting/exposure, not an item)",
                    zone.get("label") or zone_key, len(candidates), evaluated_cells,
                )
                for cand in candidates:
                    k = cand["key"]
                    self._inventory_baseline_hist[k] = cand["hist"]
                    self._inventory_baseline_crop[k] = cand["crop"].copy()
                    self._inventory_change_since.pop(k, None)
                    self._inventory_change_last_seen.pop(k, None)
                continue

            # Otherwise report the single most-changed cell — the one that
            # actually looks like the product slot that changed.
            best = max(candidates, key=lambda x: x["change_score"])
            key = best["key"]
            r, c = best["row"], best["col"]
            cx1, cy1, cx2, cy2 = best["bbox"]
            crop = best["crop"]
            hist = best["hist"]
            change_score = best["change_score"]

            ref_crop = self._inventory_baseline_crop.get(key, crop)
            _, ref_buf = cv2.imencode(".jpg", ref_crop, [cv2.IMWRITE_JPEG_QUALITY, 75])
            _, cur_buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 75])

            # Tier 2: enrich the candidate change with a real
            # open-vocabulary product count on both crops. This
            # NEVER blocks or suppresses the Tier 1 event — if
            # the detector is unavailable or errors, product
            # counts stay empty and the event still fires using
            # only the Tier 1 CV signal.
            extra_metadata = {
                "zone_id": zone_key,
                "zone_label": zone.get("label") or "Shelf zone",
                "cell": [r, c],
                "cell_bbox_px": [cx1, cy1, cx2, cy2],
                "cells_changed": len(candidates),
                "cells_evaluated": evaluated_cells,
                "reference_snapshot_b64": base64.b64encode(ref_buf.tobytes()).decode(),
                "current_crop_b64": base64.b64encode(cur_buf.tobytes()).decode(),
            }
            # Attach a photo of whoever was last seen (preferring someone
            # seen at this exact cell, falling back to the last person seen
            # anywhere on this camera) so the incident isn't evidence-less
            # just because the detector only judges the shelf once the zone
            # is person-free.
            person_seen_at = self._inventory_last_person_seen.get(key)
            person_jpeg = self._inventory_last_person_jpeg.get(key)
            person_source = "cell"
            if (
                person_jpeg is None
                or person_seen_at is None
                or (
                    self._inventory_frame_person_jpeg is not None
                    and self._inventory_frame_person_seen > (person_seen_at or 0)
                )
            ):
                # Nobody was matched to this specific cell (common — an arm
                # reaching in rarely puts the person's bbox inside the cell),
                # or somebody was seen more recently elsewhere in frame.
                if self._inventory_frame_person_jpeg is not None:
                    person_jpeg = self._inventory_frame_person_jpeg
                    person_seen_at = self._inventory_frame_person_seen
                    person_source = "frame"
            if person_seen_at and person_jpeg is not None:
                age_sec = now - person_seen_at
                if age_sec <= self._INVENTORY_PERSON_EVIDENCE_MAX_AGE_SEC:
                    extra_metadata["person_snapshot_b64"] = base64.b64encode(
                        person_jpeg
                    ).decode()
                    extra_metadata["person_seen_seconds_ago"] = round(age_sec, 1)
                    extra_metadata["person_evidence_source"] = person_source
            if self._product_count_detector is not None:
                try:
                    baseline_pc = self._product_count_detector.count_products(ref_crop)
                    current_pc = self._product_count_detector.count_products(crop)
                    if baseline_pc is not None and current_pc is not None:
                        extra_metadata["baseline_product_count"] = baseline_pc["count"]
                        extra_metadata["current_product_count"] = current_pc["count"]
                        extra_metadata["product_count_delta"] = (
                            current_pc["count"] - baseline_pc["count"]
                        )
                except Exception as e:  # noqa: BLE001
                    log.warning(f"Tier 2 product count enrichment failed (non-fatal): {e}")

            # Draw the changed cell (yellow box + zone label) on
            # the alert snapshot so the Incident evidence image
            # actually shows the zone that triggered the alert —
            # mirrors the annotated-snapshot pattern already used
            # for people-count evidence.
            annotated = frame.copy()
            cv2.rectangle(annotated, (cx1, cy1), (cx2, cy2), (0, 200, 255), 3)
            cv2.putText(
                annotated, zone.get("label") or "Shelf zone",
                (cx1 + 4, max(14, cy1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2, cv2.LINE_AA,
            )

            evt = self._emit(
                "inventory_movement",
                min(0.95, 0.5 + change_score / 2),
                [],
                annotated,
                extra_metadata=extra_metadata,
                cooldown_key=f"inventory_movement:{zone_key}",
            )
            if evt:
                events.append(evt)
                # Re-baseline every cell that was a candidate this pass so
                # the same change doesn't keep re-firing (and so the cells
                # we deliberately did NOT report don't fire on the next
                # pass as if they were separate events).
                for cand in candidates:
                    k = cand["key"]
                    self._inventory_baseline_hist[k] = cand["hist"]
                    self._inventory_baseline_crop[k] = cand["crop"].copy()
                    self._inventory_change_since.pop(k, None)
                    self._inventory_change_last_seen.pop(k, None)
            # If evt is None (this zone's cooldown hasn't elapsed yet),
            # deliberately do NOT re-baseline or clear the streak —
            # otherwise a confirmed change would be silently discarded and
            # never emitted at all instead of firing as soon as cooldown
            # clears.

        # Drop state for cells whose parent zone was removed/edited out of
        # existence in the UI. Keys are "{zone_key}:{r}_{c}".
        all_keys = (
            set(self._inventory_baseline_hist)
            | set(self._inventory_last_person_seen)
            | set(self._inventory_last_person_jpeg)
        )
        stale = [k for k in all_keys if k.split(":", 1)[0] not in seen_keys]
        for k in stale:
            self._inventory_baseline_hist.pop(k, None)
            self._inventory_baseline_crop.pop(k, None)
            self._inventory_change_since.pop(k, None)
            self._inventory_change_last_seen.pop(k, None)
            self._inventory_last_person_seen.pop(k, None)
            self._inventory_last_person_jpeg.pop(k, None)

        return events

    def analyse(
        self,
        boxes: list,
        frame: np.ndarray,
        count_persons: Optional[list] = None,
    ) -> list[dict]:
        """Given a list of BoundingBox, return list of events to emit.

        ``boxes`` are the high-confidence detections used for alerting.
        ``count_persons`` (optional) are person boxes detected at a LOWER
        confidence threshold, used only for people counting — ceiling-mounted
        cameras at steep angles produce small/foreshortened person boxes that
        YOLO scores 0.3–0.55, well below the 0.6 alert threshold.
        """
        events = []
        now = time.time()

        # ROI masking: drop anything inside an excluded area BEFORE it can
        # trigger an alert or be counted — e.g. a public sidewalk visible
        # through a storefront window, or a TV/mirror reflecting people.
        if self._exclusion_zones:
            fh, fw = frame.shape[:2]
            boxes = self._filter_exclusions(boxes, fw, fh)
            if count_persons is not None:
                count_persons = self._filter_exclusions(count_persons, fw, fh)

        persons     = [b for b in boxes if b.label == "person"]
        items       = [b for b in boxes if RETAIL_CLASSES.get(b.label) == "high_value_item"]
        shelf_items = [b for b in boxes if RETAIL_CLASSES.get(b.label) == "shelf_item"]

        # LIVE count = every person visible in the frame (what the user sees
        # in the snapshot). The people-count zone must NOT filter this — a
        # doorway zone would otherwise report 0 whenever nobody is standing
        # exactly in the doorway, which reads as "broken" on the dashboard.
        count_boxes = count_persons if count_persons is not None else persons
        # Assign persistent track IDs (v1.5.0 ByteTrack-inspired tracker) —
        # used for accurate, never-double-counted footfall below. Does not
        # change the live count itself.
        tracked = self._tracker.update(count_boxes)
        self.last_person_count = len(tracked)
        self._count_window.append((now, self.last_person_count))
        # ZONE count = persons inside the drawn zone (falls back to the full
        # frame when no zone is configured). This drives "visitors today".
        self.last_zone_count = self._count_people(tracked, frame)
        self._entry_window.append((now, self.last_zone_count))
        self._update_entries_via_tracks(tracked, frame)

        # 1. Shoplifting: person near high-value item for >2s
        # Key on the ITEM's position (items are stationary — backpack/bag on shelf).
        # Keying on the person would reset the timer whenever they walk a grid cell
        # width (~64px at 640p) before the 2s window closes.
        if persons and items and self._is_enabled("shoplifting"):
            overlapping_keys: set[str] = set()
            for p in persons:
                for item in items:
                    if self._boxes_overlap(p, item, threshold=0.3):
                        key = f"sweep_{int(item.x*10)}_{int(item.y*10)}"
                        overlapping_keys.add(key)
                        entry = self._person_with_items.get(key)
                        if entry is None:
                            entry = [now, now]  # [first_seen, last_seen]
                            self._person_with_items[key] = entry
                        else:
                            entry[1] = now  # last_seen
                        if now - entry[0] >= 2.0:
                            evt = self._emit("shoplifting", max(p.confidence, item.confidence), [p, item], frame)
                            if evt:
                                events.append(evt)
            # Temporal smoothing (v1.5.1): a key that loses overlap for
            # longer than the continuity grace window is a NEW encounter,
            # not a continuation — reset it instead of letting disjoint,
            # unrelated brief overlaps accumulate toward the 2s threshold.
            stale = [
                k for k, (_, last_seen) in self._person_with_items.items()
                if k not in overlapping_keys and now - last_seen > self._continuity_grace_sec
            ]
            for k in stale:
                del self._person_with_items[k]
        else:
            self._person_with_items.clear()

        # 2. Restricted Zone: person stationary for >30s
        dwell_seen_keys: set[str] = set()
        for p in persons:
            key = f"dwell_{int(p.x * 100)}_{int(p.y * 100)}"
            dwell_seen_keys.add(key)
            # Temporal smoothing (v1.5.1): if this exact spot wasn't matched
            # recently, this is a NEW visit — start the dwell count over
            # instead of adding to a count left over from a past, unrelated
            # visit to the same coordinates.
            last_seen = self._person_dwell_last_seen.get(key)
            if last_seen is not None and now - last_seen > self._continuity_grace_sec:
                self._person_frame_counts[key] = 0
            self._person_dwell_last_seen[key] = now
            self._person_frame_counts[key] = self._person_frame_counts.get(key, 0) + 1
            frames_needed = int(30 * self.fps)
            if self._person_frame_counts[key] >= frames_needed:
                evt = self._emit("restricted_zone", p.confidence, [p], frame)
                if evt:
                    events.append(evt)
                self._person_frame_counts[key] = 0

        # Expire dwell counters for spots not matched this frame once the
        # continuity grace window has elapsed (bounds memory AND prevents a
        # stale count from being resumed by an unrelated later visit).
        expired = [
            k for k, last_seen in self._person_dwell_last_seen.items()
            if k not in dwell_seen_keys and now - last_seen > self._continuity_grace_sec
        ]
        for k in expired:
            self._person_dwell_last_seen.pop(k, None)
            self._person_frame_counts.pop(k, None)
        # Backstop cap in case pruning above ever lags (e.g. many distinct
        # spots seen briefly) — keep memory bounded regardless.
        if len(self._person_frame_counts) > 50:
            oldest = sorted(
                self._person_frame_counts, key=lambda k: self._person_dwell_last_seen.get(k, 0)
            )[:20]
            for k in oldest:
                self._person_frame_counts.pop(k, None)
                self._person_dwell_last_seen.pop(k, None)

        # 3. Inventory movement: per-zone occupancy-change detection (Tier 1
        # fix — previously this was a no-op that relied on a dead backend
        # detector which never received real per-tenant camera frames).
        events.extend(self._analyze_inventory_zones(persons, frame, now))

        # 4. Fall Detection
        if self._is_enabled("fall_detected"):
            fall_evt = self._fall_detector.analyse(persons, frame)
            if fall_evt:
                events.append(fall_evt)

        # 5. Loitering
        if self._is_enabled("loitering"):
            loiter_evt = self._loiter_detector.analyse(persons, frame)
            if loiter_evt:
                events.append(loiter_evt)

        # 6. Crowding
        if self._is_enabled("crowding"):
            crowd_evt = self._crowd_detector.analyse(persons, frame)
            if crowd_evt:
                events.append(crowd_evt)

        # 7. Suspicious behavior (pacing / direction reversals)
        if self._is_enabled("suspicious_behavior"):
            suspicious_evt = self._suspicious_detector.analyse(persons, frame)
            if suspicious_evt:
                events.append(suspicious_evt)

        # 8. Pose-based concealment shoplifting (rate-limited internally).
        # Pose inference is the single most expensive pass in the pipeline —
        # skipping it entirely on cameras where shoplifting is switched off
        # is also the biggest available latency win on multi-camera sites.
        if self._pose_detector is not None and self._is_enabled("shoplifting"):
            pose_evt = self._pose_detector.analyse(frame)
            if pose_evt:
                events.append(pose_evt)

        # Attach a full-resolution person crop so the backend can run staff
        # face matching (Staff Faces enrolment) and suppress alerts for
        # recognised staff. The 320x180 snapshot is too small for faces.
        if events and persons:
            crop_b64 = self._person_crop_b64(persons, frame)
            if crop_b64:
                for evt in events:
                    if evt.get("event_type") in STAFF_FACE_EVENTS:
                        evt["person_crop_b64"] = crop_b64

        return events

    @staticmethod
    def _person_crop_b64(persons: list, frame: np.ndarray) -> Optional[str]:
        """JPEG-encode a native-resolution crop of the largest person box."""
        try:
            fh, fw = frame.shape[:2]
            p = max(persons, key=lambda b: b.w * b.h)
            x1 = max(0, int(p.x * fw) - 10)
            y1 = max(0, int(p.y * fh) - 10)
            x2 = min(fw, int((p.x + p.w) * fw) + 10)
            y2 = min(fh, int((p.y + p.h) * fh) + 10)
            if x2 - x1 < 40 or y2 - y1 < 40:
                return None
            _, buf = cv2.imencode(
                ".jpg", frame[y1:y2, x1:x2], [cv2.IMWRITE_JPEG_QUALITY, 80]
            )
            return base64.b64encode(buf.tobytes()).decode()
        except Exception:
            return None

    def _count_people(self, persons: list, frame: np.ndarray) -> int:
        """Zone-filtered person count (footfall). Falls back to everyone in
        frame when no people-count zone is configured. NOT used for the live
        occupancy figure — that is always the total in-frame count."""
        if not self._people_count_zones:
            return len(persons)

        frame_height, frame_width = frame.shape[:2]
        count = 0
        for person in persons:
            center_x = (person.x + person.w / 2) * frame_width
            center_y = (person.y + person.h / 2) * frame_height
            for zone in self._people_count_zones:
                bbox = zone.get("bbox", [])
                if len(bbox) != 4:
                    continue
                x1, y1, x2, y2 = (float(v) for v in bbox)
                # Backend sends zones normalized to 0-1 ("normalized": True).
                # Scale to this frame's actual pixel size. Legacy pixel-based
                # zones (all values > 1) are used as-is.
                if zone.get("normalized") or max(x1, y1, x2, y2) <= 1.0:
                    x1, x2 = x1 * frame_width, x2 * frame_width
                    y1, y2 = y1 * frame_height, y2 * frame_height
                if x1 <= center_x <= x2 and y1 <= center_y <= y2:
                    count += 1
                    break
        return count

    def recent_person_count(self, window_sec: float = 35.0) -> int:
        """Peak person count over the last ``window_sec`` seconds.

        The heartbeat samples every 30s; the instantaneous last-frame count
        flickers to 0 whenever someone is mid-stride or briefly occluded, so
        the dashboard looked "stuck at zero". The window max reports the true
        occupancy seen during the interval.
        """
        cutoff = time.time() - window_sec
        counts = [c for (ts, c) in self._count_window if ts >= cutoff]
        if not counts:
            return self.last_person_count
        return max(counts)

    def _update_entries_via_tracks(self, tracked_persons: list, frame: np.ndarray) -> None:
        """Accumulate cumulative footfall (entries) using persistent track
        IDs (v1.5.0 — replaces the old occupancy-rise heuristic).

        Each CONFIRMED track (matched by the tracker at least twice, so a
        single-frame false detection can never count) is added to
        ``entries_today`` exactly ONCE, the first time it is seen inside
        the count zone (or anywhere in frame, when no zone is configured).
        Because counting is keyed on the track's own identity rather than
        an aggregate occupancy number, this correctly tells "2 people
        walked in" apart from "1 person walked in then back out" — both of
        which look identical to a level-based heuristic. A track that
        flickers in and out of the zone boundary is also never re-counted,
        since its ID (not its zone membership) is what's remembered.

        Resets ``entries_today`` and the counted-ID set at local midnight.
        """
        day = time.strftime("%Y-%m-%d")
        if day != self._entries_day:
            self._entries_day = day
            self.entries_today = 0
            self._counted_track_ids.clear()

        frame_height, frame_width = frame.shape[:2]
        for p in tracked_persons:
            tid = getattr(p, "track_id", None)
            if tid is None or not getattr(p, "track_confirmed", False):
                continue
            if tid in self._counted_track_ids:
                continue
            if self._people_count_zones:
                center_x = (p.x + p.w / 2) * frame_width
                center_y = (p.y + p.h / 2) * frame_height
                in_zone = False
                for zone in self._people_count_zones:
                    bbox = zone.get("bbox", [])
                    if len(bbox) != 4:
                        continue
                    x1, y1, x2, y2 = (float(v) for v in bbox)
                    if zone.get("normalized") or max(x1, y1, x2, y2) <= 1.0:
                        x1, x2 = x1 * frame_width, x2 * frame_width
                        y1, y2 = y1 * frame_height, y2 * frame_height
                    if x1 <= center_x <= x2 and y1 <= center_y <= y2:
                        in_zone = True
                        break
                if not in_zone:
                    continue
            # No zone configured → the whole frame is the zone (matches the
            # previous fallback behaviour of `_count_people`).
            self._counted_track_ids.add(tid)
            self.entries_today += 1

        # Bound memory on very long-running/very busy days; the tracker
        # itself already caps active tracks, this just prevents the
        # counted-ID set from growing without limit.
        if len(self._counted_track_ids) > 5000:
            self._counted_track_ids = set(list(self._counted_track_ids)[-2000:])

    @staticmethod
    def _boxes_overlap(a, b, threshold: float = 0.3) -> bool:
        x_overlap = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
        y_overlap = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
        overlap_area = x_overlap * y_overlap
        min_area = min(a.w * a.h, b.w * b.h)
        return overlap_area >= threshold * min_area if min_area > 0 else False


# ---------------------------------------------------------------------------
# Camera Worker
# ---------------------------------------------------------------------------

class CameraWorker:
    # Give up after this many consecutive connection failures so cameras with
    # no real RTSP stream (e.g. demo placeholders) don't flood the log forever.
    MAX_FAILURES = 3

    def __init__(
        self,
        config: CameraConfig,
        inference: YoloInference,
        api_client: VantagApiClient,
        conf_threshold: float = 0.6,
        target_fps: int = 5,
        event_cooldown_sec: int = 30,
        on_event: Optional[Callable[[dict], None]] = None,
        pose_inference: Optional[YoloPoseInference] = None,
        people_count_zones: Optional[list[dict]] = None,
        exclusion_zones: Optional[list[dict]] = None,
        inventory_zones: Optional[list[dict]] = None,
        detections: Optional[dict] = None,
        product_count_detector: Optional["ProductCountDetector"] = None,
    ):
        self.config = config
        self._inference = inference
        self._api = api_client
        self._conf = conf_threshold
        self._target_fps = target_fps
        self._on_event = on_event
        self._analyzer = DetectionAnalyzer(
            camera_id=config.id,
            cooldown_sec=event_cooldown_sec,
            fps=float(target_fps),
            pose_inference=pose_inference,
            exclusion_zones=exclusion_zones,
            people_count_zones=people_count_zones,
            inventory_zones=inventory_zones,
            detections=detections,
            product_count_detector=product_count_detector,
        )

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.current_fps: float = 0.0
        self.is_connected: bool = False
        self.error_msg: str = ""
        self.consecutive_failures: int = 0

        # Live-frame relay: push a downsized JPEG to the backend so the cloud
        # dashboard can display live view even when the camera is on a private
        # LAN unreachable from the backend directly.
        #
        # Interval is 0.5s (~2 fps). The previous 0.2s (5 fps) at 640x360 q70
        # meant 6 cameras pushed ~12 Mbps of continuous upload, which saturated
        # typical store uplinks — pushes timed out, frames aged past the
        # backend's staleness window, and live tiles went blank one by one.
        # 2 fps at 480x270 q65 is ~1.5 Mbps total for 6 cameras and still
        # looks live on the dashboard.
        self._last_frame_push: float = 0.0
        self._frame_push_interval: float = 0.5
        self._frame_push_inflight = threading.Event()

        # AI inference runs in its own single thread so a slow YOLO/pose pass
        # (1-3s on CPU) can NEVER stall the capture loop. Previously inference
        # was inline: while it blocked, no frames were pushed to the backend,
        # the relay's staleness window expired, and the live tile went black
        # ("camera blip") exactly when a detection was about to fire.
        self._infer_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"infer-{config.id}"
        )
        self._infer_inflight = threading.Event()
        # Annotated people-count snapshot push (rate-limited)
        self._last_count_snapshot = 0.0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"cam-{self.config.id}",
            daemon=True,
        )
        self._thread.start()
        log.info(f"[{self.config.name}] Worker started → {self.config.rtsp_url}")
        # Make the per-camera analytic configuration VISIBLE in the console.
        # Without this, testing an analytic in front of a camera where it is
        # switched off produced total silence — indistinguishable from a
        # broken detector, and the only record was a server-side log line.
        det = self._analyzer._detections
        if det:
            on = sorted(k for k, v in det.items() if v)
            off = sorted(k for k, v in det.items() if not v)
            log.info(
                f"[{self.config.name}] Analytics ENABLED: "
                f"{', '.join(on) if on else '(none)'}"
            )
            if off:
                log.info(f"[{self.config.name}] Analytics off: {', '.join(off)}")
        else:
            log.warning(
                f"[{self.config.name}] No per-camera analytic config received "
                f"— running all detectors; backend will filter."
            )
        zone_bits = []
        if getattr(self._analyzer, "_inventory_zones", None):
            zone_bits.append(f"shelf/inventory zones={len(self._analyzer._inventory_zones)}")
        if getattr(self._analyzer, "_people_count_zones", None):
            zone_bits.append(f"people-count zones={len(self._analyzer._people_count_zones)}")
        if zone_bits:
            log.info(f"[{self.config.name}] Zones: {'; '.join(zone_bits)}")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._infer_executor.shutdown(wait=False)
        log.info(f"[{self.config.name}] Worker stopped")

    # People counting uses a LOWER confidence than alerting: overhead/angled
    # CCTV shots of stationary or partially-occluded people typically score
    # 0.35-0.55 — below the 0.6 alert threshold, so they were invisible to the
    # counter. Alerts keep the strict threshold to avoid false positives.
    COUNT_CONF = 0.35
    # Minimum seconds between annotated people-count snapshot uploads.
    COUNT_SNAPSHOT_INTERVAL = 20.0

    def _run_inference(self, frame: np.ndarray) -> None:
        """Runs YOLO detection + event analysis off the capture thread.

        Only one inference is in flight per camera (single-worker executor +
        in-flight flag), so a slow pass simply lowers the effective detection
        fps instead of freezing the live view.
        """
        try:
            # Single YOLO pass at the LOW threshold, then split by confidence:
            # low-conf persons feed the people counter, high-conf boxes feed
            # the alert analyser. (One pass ~ same cost as before.)
            low_conf = min(self.COUNT_CONF, self._conf)
            all_boxes = self._inference.detect(frame, conf_threshold=low_conf)
            count_persons = [b for b in all_boxes if b.label == "person"]
            alert_boxes = [b for b in all_boxes if b.confidence >= self._conf]
            events = self._analyzer.analyse(
                alert_boxes, frame, count_persons=count_persons
            )
            self._maybe_push_count_snapshot(frame, count_persons)
            for event in events:
                log.info(
                    f"[{self.config.name}] Event: {event['event_type']} "
                    f"conf={event['confidence']} sev={event['severity']}"
                )
                if self._on_event:
                    self._on_event(event)
                self._api.post_event(event)
        except Exception as e:  # noqa: BLE001 — inference must never kill the worker
            log.warning(f"[{self.config.name}] Inference error: {e}")
        finally:
            self._infer_inflight.clear()

    def _maybe_push_count_snapshot(self, frame: np.ndarray, persons: list) -> None:
        """Upload an annotated snapshot (person boxes drawn) so the People
        Count page can show visual proof of WHO is being counted.

        Rate-limited; only sent when at least one person is detected.
        """
        now = time.time()
        if not persons or (now - self._last_count_snapshot) < self.COUNT_SNAPSHOT_INTERVAL:
            return
        self._last_count_snapshot = now
        try:
            fh, fw = frame.shape[:2]
            annotated = frame.copy()
            # Draw the people-count zone (yellow) so the snapshot explains
            # itself: green boxes inside the zone count towards footfall.
            for zone in getattr(self._analyzer, "_people_count_zones", []) or []:
                bbox = zone.get("bbox", [])
                if len(bbox) != 4:
                    continue
                zx1, zy1, zx2, zy2 = (float(v) for v in bbox)
                if zone.get("normalized") or max(zx1, zy1, zx2, zy2) <= 1.0:
                    zx1, zx2 = zx1 * fw, zx2 * fw
                    zy1, zy2 = zy1 * fh, zy2 * fh
                cv2.rectangle(
                    annotated, (int(zx1), int(zy1)), (int(zx2), int(zy2)),
                    (0, 200, 255), 2,
                )
                cv2.putText(
                    annotated, "count zone", (int(zx1) + 4, max(14, int(zy1) - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1, cv2.LINE_AA,
                )
            for p in persons:
                x1, y1 = int(p.x * fw), int(p.y * fh)
                x2, y2 = int((p.x + p.w) * fw), int((p.y + p.h) * fh)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 200, 60), 2)
                cv2.putText(
                    annotated, f"person {p.confidence:.2f}",
                    (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (0, 200, 60), 1, cv2.LINE_AA,
                )
            # Live count = everyone in frame (matches the boxes drawn above).
            count = self._analyzer.last_person_count
            cv2.putText(
                annotated, f"Count: {count}", (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 60), 2, cv2.LINE_AA,
            )
            # Keep upload small: 640-wide JPEG q70
            if fw > 640:
                scale = 640 / fw
                annotated = cv2.resize(annotated, (640, int(fh * scale)))
            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
            snap_b64 = base64.b64encode(buf.tobytes()).decode()
            self._api.post_count_snapshot(self.config.id, count, snap_b64)
        except Exception as e:  # noqa: BLE001 — snapshot is best-effort
            log.debug(f"[{self.config.name}] Count snapshot push failed: {e}")

    def _run(self):
        frame_interval = 1.0 / self._target_fps

        while not self._stop_event.is_set():
            cap = None
            try:
                stream_url = sanitize_rtsp_url(self.config.rtsp_url)
                cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not cap.isOpened():
                    raise ConnectionError(f"Cannot open RTSP stream: {self.config.rtsp_url}")

                self.is_connected = True
                self.consecutive_failures = 0
                self.error_msg = ""
                log.info(f"[{self.config.name}] RTSP connected")

                frame_count = 0
                fps_t0 = time.time()
                fps_frames = 0
                last_infer = 0.0

                # LOW-LATENCY LOOP with GRAB-DRAIN: cap.read() decodes frames
                # one-by-one, so whenever AI inference blocks longer than one
                # frame period, FFMPEG's buffer accumulates stale frames and
                # the live view drifts seconds behind realtime. Fix: grab()
                # (cheap, no decode) repeatedly to drain any buffered frames,
                # then retrieve() (decode) only the NEWEST one. A grab that
                # returns in <5ms was a stale buffered frame; a grab that
                # blocks longer waited for a fresh frame — stop draining.
                while not self._stop_event.is_set():
                    if not cap.grab():
                        raise ConnectionError("Frame grab failed — stream ended")
                    for _ in range(10):  # drain at most 10 stale frames
                        t_g = time.monotonic()
                        if not cap.grab():
                            break
                        if time.monotonic() - t_g > 0.005:
                            break  # blocked → this grab is a fresh frame
                    ret, frame = cap.retrieve()
                    if not ret:
                        raise ConnectionError("Frame read failed — stream ended")

                    frame_count += 1
                    fps_frames += 1

                    elapsed = time.time() - fps_t0
                    if elapsed >= 2.0:
                        self.current_fps = fps_frames / elapsed
                        fps_frames = 0
                        fps_t0 = time.time()

                    now = time.time()
                    if now - last_infer >= frame_interval and not self._infer_inflight.is_set():
                        last_infer = now
                        self._infer_inflight.set()
                        self._infer_executor.submit(self._run_inference, frame.copy())

                    self._maybe_push_frame(frame)

            except Exception as e:
                self.is_connected = False
                self.consecutive_failures += 1
                self.error_msg = str(e)
                log.warning(f"[{self.config.name}] Error: {e} (failures={self.consecutive_failures})")
                # NEVER permanently give up: NVRs limit concurrent RTSP sessions,
                # so 6 cameras hitting the same NVR at startup often fail a few
                # times before slots free up. A permanent stop after 3 failures
                # left cameras offline forever until an agent restart. Instead,
                # keep retrying with capped exponential backoff (max 60s).
                if self.consecutive_failures == self.MAX_FAILURES:
                    log.error(
                        f"[{self.config.name}] {self.MAX_FAILURES} consecutive failures — "
                        f"will keep retrying every ≤60s (check RTSP URL/NVR session limits)."
                    )
                backoff = min(2 ** self.consecutive_failures, 60)
                log.info(f"[{self.config.name}] Reconnecting in {backoff}s...")
                self._stop_event.wait(timeout=backoff)
            finally:
                if cap:
                    cap.release()

    def _maybe_push_frame(self, frame: np.ndarray) -> None:
        """Throttled, non-blocking push of the current frame to the backend
        live-relay endpoint (``POST /api/edge/frame``).

        Runs at most every ``self._frame_push_interval`` seconds and skips
        entirely if a previous push is still in flight, so a slow/unreachable
        backend never stalls the capture loop.
        """
        now = time.time()
        if now - self._last_frame_push < self._frame_push_interval:
            return
        if self._frame_push_inflight.is_set():
            return  # previous push hasn't completed yet — drop this frame

        self._last_frame_push = now
        small = cv2.resize(frame, (640, 360))
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return
        frame_b64 = base64.b64encode(buf.tobytes()).decode()

        self._frame_push_inflight.set()

        def _do_push():
            try:
                self._api.push_frame(self.config.id, frame_b64)
            finally:
                self._frame_push_inflight.clear()

        _FRAME_PUSH_EXECUTOR.submit(_do_push)
