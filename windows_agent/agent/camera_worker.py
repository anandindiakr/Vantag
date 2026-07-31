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

    def __init__(
        self,
        camera_id: str,
        cooldown_sec: int = 30,
        fps: float = 5.0,
        pose_inference: Optional["YoloPoseInference"] = None,
        people_count_zones: Optional[list[dict]] = None,
    ):
        self.camera_id = camera_id
        self.cooldown_sec = cooldown_sec
        self.fps = fps
        self._last_event: dict[str, float] = {}
        self._person_with_items: dict[str, float] = {}
        self._person_frame_counts: dict[str, int] = {}
        self._shelf_empty_since: Optional[float] = None

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

    def _can_emit(self, event_type: str) -> bool:
        last = self._last_event.get(event_type, 0)
        return (time.time() - last) >= self.cooldown_sec

    def _emit(self, event_type: str, confidence: float, boxes: list, frame: np.ndarray) -> Optional[dict]:
        if not self._can_emit(event_type):
            return None
        self._last_event[event_type] = time.time()
        small = cv2.resize(frame, (320, 180))
        _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        snap = base64.b64encode(buf.tobytes()).decode()
        severity = self._SEVERITY_MAP.get(event_type, "medium")
        if confidence >= 0.85 and severity == "medium":
            severity = "high"
        return {
            "camera_id": self.camera_id,
            "event_type": event_type,
            "severity": severity,
            "confidence": round(confidence, 3),
            "snapshot_b64": snap,
            "metadata": {
                "timestamp": int(time.time() * 1000),
                "bounding_boxes": [b.to_dict() for b in boxes],
            },
        }

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
        if persons and items:
            for p in persons:
                for item in items:
                    if self._boxes_overlap(p, item, threshold=0.3):
                        key = f"sweep_{int(item.x*10)}_{int(item.y*10)}"
                        self._person_with_items.setdefault(key, now)
                        if now - self._person_with_items[key] >= 2.0:
                            evt = self._emit("shoplifting", max(p.confidence, item.confidence), [p, item], frame)
                            if evt:
                                events.append(evt)
            # Prune item slots where no person has been nearby for >30s
            stale = [k for k, t in self._person_with_items.items() if now - t > 30]
            for k in stale:
                del self._person_with_items[k]
        else:
            self._person_with_items.clear()

        # 2. Restricted Zone: person stationary for >30s
        for p in persons:
            key = f"dwell_{int(p.x * 100)}_{int(p.y * 100)}"
            self._person_frame_counts[key] = self._person_frame_counts.get(key, 0) + 1
            frames_needed = int(30 * self.fps)
            if self._person_frame_counts[key] >= frames_needed:
                evt = self._emit("restricted_zone", p.confidence, [p], frame)
                if evt:
                    events.append(evt)
                self._person_frame_counts[key] = 0

        # Clean up stale dwell counters
        if len(self._person_frame_counts) > 20:
            oldest = sorted(self._person_frame_counts, key=lambda k: self._person_frame_counts[k])[:10]
            for k in oldest:
                del self._person_frame_counts[k]

        # Inventory movement is configured and evaluated by the dedicated
        # detector on the backend. Do not create a generic incident merely
        # because this frame contains no shelf-item detections.

        # 4. Fall Detection
        fall_evt = self._fall_detector.analyse(persons, frame)
        if fall_evt:
            events.append(fall_evt)

        # 5. Loitering
        loiter_evt = self._loiter_detector.analyse(persons, frame)
        if loiter_evt:
            events.append(loiter_evt)

        # 6. Crowding
        crowd_evt = self._crowd_detector.analyse(persons, frame)
        if crowd_evt:
            events.append(crowd_evt)

        # 7. Suspicious behavior (pacing / direction reversals)
        suspicious_evt = self._suspicious_detector.analyse(persons, frame)
        if suspicious_evt:
            events.append(suspicious_evt)

        # 8. Pose-based concealment shoplifting (rate-limited internally)
        if self._pose_detector is not None:
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
            people_count_zones=people_count_zones,
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
