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
import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np

from .config import CameraConfig
from .api_client import VantagApiClient
from .inference import YoloInference, RETAIL_CLASSES

log = logging.getLogger("vantag.camera")

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
# Detection Analyzer (orchestrates all sub-detectors)
# ---------------------------------------------------------------------------

class DetectionAnalyzer:
    """
    Orchestrates per-frame detection results and decides when to emit events.

    Events emitted (canonical backend types):
      shoplifting        – person near high-value item for >2s
      restricted_zone    – person stationary in sensitive zone for >30s
      inventory_movement – no shelf item for >60s
      fall_detected      – aspect-ratio transition standing→fallen
      loitering          – person in zone >90s while still moving
    """

    _SEVERITY_MAP = {
        "shoplifting":        "high",
        "restricted_zone":    "medium",
        "inventory_movement": "medium",
        "fall_detected":      "high",
        "loitering":          "low",
    }

    def __init__(self, camera_id: str, cooldown_sec: int = 30, fps: float = 5.0):
        self.camera_id = camera_id
        self.cooldown_sec = cooldown_sec
        self.fps = fps
        self._last_event: dict[str, float] = {}
        self._person_with_items: dict[str, float] = {}
        self._person_frame_counts: dict[str, int] = {}
        self._shelf_empty_since: Optional[float] = None

        self._fall_detector = FallDetector(camera_id, cooldown_sec)
        self._loiter_detector = LoiteringDetector(camera_id, cooldown_sec)

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

    def analyse(self, boxes: list, frame: np.ndarray) -> list[dict]:
        """Given a list of BoundingBox, return list of events to emit."""
        events = []
        now = time.time()

        persons     = [b for b in boxes if b.label == "person"]
        items       = [b for b in boxes if RETAIL_CLASSES.get(b.label) == "high_value_item"]
        shelf_items = [b for b in boxes if RETAIL_CLASSES.get(b.label) == "shelf_item"]

        # 1. Shoplifting: person near high-value item for >2s
        # Key uses coarse spatial coords so it stays stable across frames
        # (id(p) changes every frame since YOLO creates new objects each inference)
        if persons and items:
            for p in persons:
                for item in items:
                    if self._boxes_overlap(p, item, threshold=0.3):
                        key = f"sweep_{int(p.x*10)}_{int(p.y*10)}"
                        self._person_with_items.setdefault(key, now)
                        if now - self._person_with_items[key] >= 2.0:
                            evt = self._emit("shoplifting", max(p.confidence, item.confidence), [p, item], frame)
                            if evt:
                                events.append(evt)
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

        # 3. Inventory Movement: no shelf items for >60s
        if not shelf_items:
            if self._shelf_empty_since is None:
                self._shelf_empty_since = now
            elif now - self._shelf_empty_since >= 60.0:
                evt = self._emit("inventory_movement", 0.85, [], frame)
                if evt:
                    events.append(evt)
        else:
            self._shelf_empty_since = None

        # 4. Fall Detection
        fall_evt = self._fall_detector.analyse(persons, frame)
        if fall_evt:
            events.append(fall_evt)

        # 5. Loitering
        loiter_evt = self._loiter_detector.analyse(persons, frame)
        if loiter_evt:
            events.append(loiter_evt)

        return events

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
    def __init__(
        self,
        config: CameraConfig,
        inference: YoloInference,
        api_client: VantagApiClient,
        conf_threshold: float = 0.6,
        target_fps: int = 5,
        event_cooldown_sec: int = 30,
        on_event: Optional[Callable[[dict], None]] = None,
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
        )

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.current_fps: float = 0.0
        self.is_connected: bool = False
        self.error_msg: str = ""
        self.consecutive_failures: int = 0

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
        log.info(f"[{self.config.name}] Worker stopped")

    def _run(self):
        frame_interval = 1.0 / self._target_fps
        inference_every = 2   # run AI every 2nd captured frame

        while not self._stop_event.is_set():
            cap = None
            try:
                cap = cv2.VideoCapture(self.config.rtsp_url, cv2.CAP_FFMPEG)
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

                while not self._stop_event.is_set():
                    t_start = time.time()
                    ret, frame = cap.read()
                    if not ret:
                        raise ConnectionError("Frame read failed — stream ended")

                    frame_count += 1
                    fps_frames += 1

                    elapsed = time.time() - fps_t0
                    if elapsed >= 2.0:
                        self.current_fps = fps_frames / elapsed
                        fps_frames = 0
                        fps_t0 = time.time()

                    if frame_count % inference_every == 0:
                        boxes = self._inference.detect(frame, conf_threshold=self._conf)
                        events = self._analyzer.analyse(boxes, frame)
                        for event in events:
                            log.info(
                                f"[{self.config.name}] Event: {event['event_type']} "
                                f"conf={event['confidence']} sev={event['severity']}"
                            )
                            if self._on_event:
                                self._on_event(event)
                            self._api.post_event(event)

                    sleep_time = frame_interval - (time.time() - t_start)
                    if sleep_time > 0:
                        time.sleep(sleep_time)

            except Exception as e:
                self.is_connected = False
                self.consecutive_failures += 1
                self.error_msg = str(e)
                log.warning(f"[{self.config.name}] Error: {e} (failures={self.consecutive_failures})")
                backoff = min(2 ** self.consecutive_failures, 60)
                log.info(f"[{self.config.name}] Reconnecting in {backoff}s...")
                self._stop_event.wait(timeout=backoff)
            finally:
                if cap:
                    cap.release()
