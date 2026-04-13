"""
Per-camera RTSP worker thread.
Connects to an RTSP stream, runs YOLOv8 inference, and posts events to backend.
"""
import base64
import logging
import queue
import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np

from .config import CameraConfig
from .api_client import VantagApiClient
from .inference import YoloInference, RETAIL_CLASSES

log = logging.getLogger("vantag.camera")


class DetectionAnalyzer:
    """
    Analyses per-frame detection results and decides when to emit events.
    Implements:
      - Product Sweep: person detected near high_value_items for >2s
      - Anomalous Dwell: person stationary for >30s in sensitive zone
      - Empty Shelf: no shelf_item detected for >60s
    """

    def __init__(self, camera_id: str, cooldown_sec: int = 30, fps: float = 5.0):
        self.camera_id = camera_id
        self.cooldown_sec = cooldown_sec
        self.fps = fps
        self._last_event: dict[str, float] = {}
        self._person_dwell: dict[str, float] = {}   # track_id → first_seen
        self._person_with_items: dict[str, float] = {}
        self._shelf_empty_since: Optional[float] = None
        self._person_frame_counts: dict[str, int] = {}

    def _can_emit(self, event_type: str) -> bool:
        last = self._last_event.get(event_type, 0)
        return (time.time() - last) >= self.cooldown_sec

    def _emit(self, event_type: str, confidence: float, boxes: list, frame: np.ndarray) -> Optional[dict]:
        if not self._can_emit(event_type):
            return None
        self._last_event[event_type] = time.time()
        thumbnail_b64 = self._encode_thumbnail(frame)
        return {
            "camera_id": self.camera_id,
            "event_type": event_type,
            "confidence": round(confidence, 3),
            "timestamp": int(time.time() * 1000),
            "thumbnail_b64": thumbnail_b64,
            "bounding_boxes": [b.to_dict() for b in boxes],
        }

    def _encode_thumbnail(self, frame: np.ndarray) -> str:
        small = cv2.resize(frame, (320, 180))
        _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        return base64.b64encode(buf.tobytes()).decode("utf-8")

    def analyse(self, boxes: list, frame: np.ndarray) -> list[dict]:
        """Given a list of BoundingBox, return list of events to emit."""
        events = []
        now = time.time()

        persons = [b for b in boxes if b.label == "person"]
        items = [b for b in boxes if RETAIL_CLASSES.get(b.label) == "high_value_item"]
        shelf_items = [b for b in boxes if RETAIL_CLASSES.get(b.label) == "shelf_item"]

        # 1. Product Sweep: person near high-value item
        if persons and items:
            # Check spatial overlap (simplified: any person + item in same frame)
            for p in persons:
                for item in items:
                    if self._boxes_overlap(p, item, threshold=0.3):
                        key = f"sweep_{id(p)}"
                        self._person_with_items.setdefault(key, now)
                        if now - self._person_with_items[key] >= 2.0:
                            evt = self._emit("sweep", max(p.confidence, item.confidence), [p, item], frame)
                            if evt:
                                events.append(evt)
        else:
            self._person_with_items.clear()

        # 2. Anomalous Dwell: person present for >30s
        for p in persons:
            key = f"dwell_{int(p.x * 100)}_{int(p.y * 100)}"
            self._person_frame_counts[key] = self._person_frame_counts.get(key, 0) + 1
            frames_needed = int(30 * self.fps)
            if self._person_frame_counts[key] >= frames_needed:
                evt = self._emit("dwell", p.confidence, [p], frame)
                if evt:
                    events.append(evt)
                self._person_frame_counts[key] = 0  # reset after alert

        # Clean up stale dwell counters
        if len(self._person_frame_counts) > 20:
            oldest = sorted(self._person_frame_counts, key=lambda k: self._person_frame_counts[k])[:10]
            for k in oldest:
                del self._person_frame_counts[k]

        # 3. Empty Shelf: no shelf items detected for >60s
        if not shelf_items:
            if self._shelf_empty_since is None:
                self._shelf_empty_since = now
            elif now - self._shelf_empty_since >= 60.0:
                evt = self._emit("empty_shelf", 0.85, [], frame)
                if evt:
                    events.append(evt)
        else:
            self._shelf_empty_since = None

        return events

    @staticmethod
    def _boxes_overlap(a, b, threshold: float = 0.3) -> bool:
        """Check if two bounding boxes overlap by at least threshold fraction."""
        x_overlap = max(0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
        y_overlap = max(0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
        overlap_area = x_overlap * y_overlap
        min_area = min(a.w * a.h, b.w * b.h)
        return overlap_area >= threshold * min_area if min_area > 0 else False


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

                    # Update FPS every 2 seconds
                    elapsed = time.time() - fps_t0
                    if elapsed >= 2.0:
                        self.current_fps = fps_frames / elapsed
                        fps_frames = 0
                        fps_t0 = time.time()

                    # Run inference on every Nth frame
                    if frame_count % inference_every == 0:
                        boxes = self._inference.detect(frame, conf_threshold=self._conf)
                        events = self._analyzer.analyse(boxes, frame)
                        for event in events:
                            log.info(f"[{self.config.name}] Event: {event['event_type']} conf={event['confidence']}")
                            if self._on_event:
                                self._on_event(event)
                            self._api.post_event(event)

                    # Throttle to target FPS
                    sleep_time = frame_interval - (time.time() - t_start)
                    if sleep_time > 0:
                        time.sleep(sleep_time)

            except Exception as e:
                self.is_connected = False
                self.consecutive_failures += 1
                self.error_msg = str(e)
                log.warning(f"[{self.config.name}] Error: {e} (failures={self.consecutive_failures})")
                # Exponential backoff: 2s, 4s, 8s, … up to 60s
                backoff = min(2 ** self.consecutive_failures, 60)
                log.info(f"[{self.config.name}] Reconnecting in {backoff}s...")
                self._stop_event.wait(timeout=backoff)
            finally:
                if cap:
                    cap.release()
