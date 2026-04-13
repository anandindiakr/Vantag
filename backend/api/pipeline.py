"""
backend/api/pipeline.py
========================
Central inference pipeline orchestrator for the Vantag platform.

``VantagPipeline`` ties together:
  * ``CameraRegistry``  – camera config source
  * ``StreamManager``   – RTSP frame ingestion
  * ``HealthMonitor``   – camera health polling
  * ``TamperDetector``  – one instance per camera
  * ``MQTTClient``      – event publication
  * WebSocket manager   – real-time dashboard push

Architecture
------------
1. On ``start()``, one asyncio task is spawned per enabled camera.
2. Each task calls ``StreamManager.get_frame()`` in a tight loop, runs the
   analyzer stack, updates risk scores, snapshots, heatmaps, and event logs.
3. Results are stored in plain dicts/lists protected by ``asyncio.Lock``
   objects so the API routers (running in the same event loop) can read
   them without blocking.
4. MQTT publishes and WebSocket broadcasts are fire-and-forget coroutines.

Analyzer stub conventions
--------------------------
The pipeline is designed so that additional analyzers can be plugged in by
adding them to ``_build_analyzers()``.  Each analyzer must expose:
    ``analyze(frame: np.ndarray) -> Optional[dict]``
returning an event dict or ``None``.

The ``TamperDetector`` is the only concrete analyzer included in the
existing codebase; all others are no-ops until their modules are implemented.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

import cv2
import numpy as np

from ..analyzers.tamper_detector import TamperDetector, TamperEvent
from ..analyzers.shoplifting import ShopliftingDetector, ShopliftingEvent
from ..analyzers.inventory_movement import InventoryMovementDetector, InventoryEvent
from ..analyzers.restricted_zone import RestrictedZoneDetector, ZoneEntryEvent
from ..analyzers.queue_length import QueueLengthAnalyzer, QueueEvent
from ..analyzers.fall_detection import FallDetector, FallEvent
from ..inference.yolo_engine import YOLOEngine, Detection
from ..ingestion.camera_registry import CameraRegistry
from ..ingestion.health_monitor import HealthMonitor
from ..ingestion.stream_manager import StreamManager
from ..mqtt.client import MQTTClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RECENT_EVENTS = 500        # per store
_SNAPSHOT_JPEG_QUALITY = 80     # 0-100
_HEATMAP_ROWS = 10
_HEATMAP_COLS = 10
_RISK_DECAY_FACTOR = 0.95       # applied per second when no new events arrive
_FRAME_SLEEP_NO_DATA = 0.01     # seconds to yield when no frame is available


# ---------------------------------------------------------------------------
# Severity scoring weights
# ---------------------------------------------------------------------------

_EVENT_WEIGHTS: Dict[str, float] = {
    "tamper": 35.0,
    "loitering": 15.0,
    "queue_breach": 10.0,
    "watchlist_match": 40.0,
    "low_light": 5.0,
    "crowd_surge": 20.0,
    "object_left": 12.0,
    # New AI analyzers
    "shoplifting": 45.0,
    "inventory_movement": 20.0,
    "restricted_zone": 30.0,
    "queue_length": 10.0,
    "fall_detection": 50.0,
    "unknown": 5.0,
}


def _score_to_severity(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Stub analyzer wrapper
# ---------------------------------------------------------------------------


class _LegacyAdapter:
    """
    Adapts a single-arg analyzer (``analyze(frame)``) to the 3-arg interface
    ``analyze(frame, detections, timestamp) -> List`` expected by the pipeline.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def analyze(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        timestamp: float,
    ) -> List[Any]:
        result = self._inner.analyze(frame)
        return [result] if result is not None else []


# ---------------------------------------------------------------------------
# VantagPipeline
# ---------------------------------------------------------------------------


class VantagPipeline:
    """
    Central inference pipeline for the Vantag platform.

    Parameters
    ----------
    config_path:
        Optional override for the cameras.yaml config file path.
    mqtt_client:
        Optional pre-configured ``MQTTClient``.  If ``None``, a new client
        is created using settings from the camera registry.
    ws_broadcast:
        Async callable ``(event_dict) -> Coroutine`` used to broadcast
        events over WebSocket.  Typically ``ConnectionManager.broadcast``.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        mqtt_client: Optional[MQTTClient] = None,
        ws_broadcast: Optional[Callable[[dict], Any]] = None,
    ) -> None:
        # ---- Configuration ----
        self.registry = CameraRegistry(config_path=config_path)
        self.registry.load()

        global_cfg = self.registry.get_global()
        self._window_seconds: int = int(global_cfg.get("risk_score_window_seconds", 60))

        # ---- Ingestion layer ----
        self.stream_manager = StreamManager(self.registry)
        self.health_monitor = HealthMonitor(self.stream_manager, poll_interval=5.0)

        # ---- MQTT ----
        if mqtt_client is not None:
            self._mqtt = mqtt_client
        else:
            self._mqtt = MQTTClient(
                broker=global_cfg.get("mqtt_broker", "localhost"),
                port=int(global_cfg.get("mqtt_port", 1883)),
            )
        self._mqtt_owned = mqtt_client is None  # we own it if we created it

        # ---- WebSocket broadcast callable ----
        self._ws_broadcast: Optional[Callable[[dict], Any]] = ws_broadcast

        # ---- Per-camera analyzers ----
        # Dict[camera_id, list-of-analyzers] – all expose analyze(frame, detections, timestamp) -> List
        self._analyzers: Dict[str, List[Any]] = {}

        # ---- YOLO inference engines ----
        # One shared engine (per global config); per-camera engines can be added later.
        self._yolo_engine: Optional[YOLOEngine] = self._init_yolo(global_cfg)

        self._build_analyzers()

        # ---- Shared state (read by API routers) ----
        self.risk_scores: Dict[str, dict] = {}          # store_id → {score, event_counts, ...}
        self.recent_events: Dict[str, Deque[dict]] = defaultdict(
            lambda: deque(maxlen=_MAX_RECENT_EVENTS)
        )
        self.latest_snapshots: Dict[str, bytes] = {}    # camera_id → JPEG bytes
        self.heatmaps: Dict[str, Dict[str, dict]] = {}  # store_id → {window → grid}
        self.queue_status: Dict[str, dict] = {}         # lane_id → queue data

        # ---- Rolling event timestamps for risk scoring ----
        # store_id → list of (event_type, weight, monotonic_ts)
        self._event_buffer: Dict[str, List[tuple]] = defaultdict(list)
        self._event_buffer_lock = asyncio.Lock()

        # ---- Lifecycle ----
        self._started = False
        self._stop_event = asyncio.Event()
        self._camera_tasks: List[asyncio.Task] = []
        self._risk_task: Optional[asyncio.Task] = None

        self._start_time = time.monotonic()

    # ------------------------------------------------------------------
    # YOLO engine initialisation
    # ------------------------------------------------------------------

    @staticmethod
    def _init_yolo(global_cfg: dict) -> Optional[YOLOEngine]:
        """Initialise the shared YOLO inference engine from global config."""
        model_path = global_cfg.get("yolo_model_path", "")
        device = global_cfg.get("yolo_device", "cpu")
        conf = float(global_cfg.get("yolo_conf_threshold", 0.45))
        try:
            engine = YOLOEngine(model_path=model_path, device=device, conf_threshold=conf)
            logger.info("YOLOEngine initialised | model=%s device=%s", model_path, device)
            return engine
        except Exception as exc:  # noqa: BLE001
            logger.warning("YOLOEngine init failed (%s) – analyzers will run without detections.", exc)
            return None

    # ------------------------------------------------------------------
    # Analyzer construction
    # ------------------------------------------------------------------

    def _build_analyzers(self) -> None:
        """Instantiate the full analyzer stack per enabled camera."""
        for cam in self.registry.all_cameras():
            if not cam.enabled:
                continue

            acfg = cam.analyzer_config  # raw dict from cameras.yaml

            shoplifting_cfg = acfg.get("shoplifting", {})
            inventory_cfg = acfg.get("inventory_movement", {})
            restricted_cfg = acfg.get("restricted_zone", {})
            queue_cfg = acfg.get("queue_length", {})
            fall_cfg = acfg.get("fall_detection", {})

            self._analyzers[cam.id] = [
                # Legacy (1-arg) analyzer wrapped for uniform interface
                _LegacyAdapter(TamperDetector(camera_id=cam.id)),
                # New 3-arg analyzers
                ShopliftingDetector(cam.id, shoplifting_cfg),
                InventoryMovementDetector(cam.id, inventory_cfg),
                RestrictedZoneDetector(cam.id, restricted_cfg),
                QueueLengthAnalyzer(cam.id, queue_cfg),
                FallDetector(cam.id, fall_cfg),
            ]

        logger.info("Analyzers built | cameras=%d", len(self._analyzers))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start all ingestion, health monitoring, and processing tasks."""
        if self._started:
            logger.warning("VantagPipeline.start() called but already running.")
            return

        logger.info("VantagPipeline starting...")
        self._stop_event.clear()

        self.stream_manager.start()
        self.health_monitor.start()

        if self._mqtt_owned:
            self._mqtt.connect()

        # Spawn one processing task per enabled camera.
        for cam_id in self._analyzers:
            task = asyncio.create_task(
                self._camera_loop(cam_id),
                name=f"pipeline-cam-{cam_id}",
            )
            self._camera_tasks.append(task)

        # Spawn the periodic risk-score decay task.
        self._risk_task = asyncio.create_task(
            self._risk_decay_loop(),
            name="pipeline-risk-decay",
        )

        self._started = True
        self._start_time = time.monotonic()
        logger.info("VantagPipeline started | cameras=%d", len(self._camera_tasks))

    async def stop(self) -> None:
        """Gracefully stop all pipeline tasks and release resources."""
        if not self._started:
            return

        logger.info("VantagPipeline stopping...")
        self._stop_event.set()

        # Cancel camera processing tasks.
        for task in self._camera_tasks:
            task.cancel()
        if self._camera_tasks:
            await asyncio.gather(*self._camera_tasks, return_exceptions=True)
        self._camera_tasks.clear()

        # Cancel risk decay task.
        if self._risk_task:
            self._risk_task.cancel()
            try:
                await self._risk_task
            except asyncio.CancelledError:
                pass

        self.health_monitor.stop()
        self.stream_manager.stop()

        if self._mqtt_owned:
            self._mqtt.disconnect()

        self._started = False
        logger.info("VantagPipeline stopped.")

    # ------------------------------------------------------------------
    # Per-camera processing loop
    # ------------------------------------------------------------------

    async def _camera_loop(self, camera_id: str) -> None:
        """Async loop that reads frames and runs the analyzer stack."""
        logger.info("Camera processing loop started | camera=%s", camera_id)
        try:
            cam = self.registry.get_camera(camera_id)
        except KeyError:
            logger.error("Camera not found in registry | camera=%s", camera_id)
            return

        store_id = self._camera_to_store_id(cam)

        while not self._stop_event.is_set():
            frame = self.stream_manager.get_frame(camera_id)
            if frame is None:
                await asyncio.sleep(_FRAME_SLEEP_NO_DATA)
                continue

            await self.process_frame(camera_id, store_id, frame)

            # Yield to the event loop so other tasks can run.
            await asyncio.sleep(0)

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    async def process_frame(
        self,
        camera_id: str,
        store_id: str,
        frame: np.ndarray,
    ) -> None:
        """
        Run the full analyzer stack on a single frame.

        Steps:
        1. (Optional) Low-light enhancement.
        2. Run YOLO inference to get typed Detection objects.
        3. Run each analyzer with (frame, detections, timestamp); collect events.
        4. Update risk score for the store.
        5. Cache annotated JPEG snapshot.
        6. Update heatmap.
        7. Broadcast events via WebSocket and MQTT.
        """
        timestamp = time.time()

        # 1. Low-light enhancement.
        enhanced = self._enhance_low_light(camera_id, frame)

        # 2. YOLO inference (graceful fallback to empty list if engine unavailable).
        detections: List[Detection] = []
        if self._yolo_engine is not None:
            try:
                detections = self._yolo_engine.detect(enhanced)
            except Exception as exc:  # noqa: BLE001
                logger.debug("YOLO inference error | camera=%s error=%s", camera_id, exc)

        # 3. Run analyzers – all expose analyze(frame, detections, timestamp) -> List.
        events: List[dict] = []
        analyzers = self._analyzers.get(camera_id, [])
        for analyzer in analyzers:
            try:
                results = analyzer.analyze(enhanced, detections, timestamp)
                for result in results:
                    ev = self._normalise_event(result, camera_id, store_id)
                    events.append(ev)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Analyzer error | camera=%s analyzer=%s error=%s",
                    camera_id,
                    type(analyzer).__name__,
                    exc,
                )

        # 4. Update risk score.
        if events:
            async with self._event_buffer_lock:
                now_mono = time.monotonic()
                for ev in events:
                    weight = _EVENT_WEIGHTS.get(ev.get("type", "unknown"), 5.0)
                    self._event_buffer[store_id].append(
                        (ev["type"], weight, now_mono)
                    )
                self._recompute_risk(store_id)

        # 4. Cache annotated snapshot.
        annotated = self._annotate_frame(frame, events)
        try:
            _, jpeg_buf = cv2.imencode(
                ".jpg", annotated,
                [cv2.IMWRITE_JPEG_QUALITY, _SNAPSHOT_JPEG_QUALITY],
            )
            self.latest_snapshots[camera_id] = jpeg_buf.tobytes()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Snapshot encoding failed | camera=%s error=%s", camera_id, exc)

        # 5. Update heatmap (simple motion-based approximation).
        self._update_heatmap(store_id, camera_id, frame)

        # 6. Broadcast events.
        for ev in events:
            await self._emit_event(ev, store_id)

    # ------------------------------------------------------------------
    # Risk scoring
    # ------------------------------------------------------------------

    def _recompute_risk(self, store_id: str) -> None:
        """
        Recompute risk score for a store from the rolling event buffer.

        Must be called while holding ``_event_buffer_lock``.
        """
        now_mono = time.monotonic()
        cutoff = now_mono - self._window_seconds

        # Prune events outside the window.
        buf = self._event_buffer[store_id]
        self._event_buffer[store_id] = [
            e for e in buf if e[2] >= cutoff
        ]
        buf = self._event_buffer[store_id]

        # Sum weights of events in window.
        total_weight = sum(e[1] for e in buf)
        score = min(100.0, total_weight)

        event_counts: Dict[str, int] = defaultdict(int)
        for ev_type, _, _ in buf:
            event_counts[ev_type] += 1

        self.risk_scores[store_id] = {
            "score": round(score, 2),
            "severity": _score_to_severity(score),
            "event_counts": dict(event_counts),
            "window_seconds": self._window_seconds,
            "computed_at": datetime.now(tz=timezone.utc),
        }

    async def _risk_decay_loop(self) -> None:
        """Periodically decay risk scores when no new events arrive."""
        while not self._stop_event.is_set():
            await asyncio.sleep(1.0)
            async with self._event_buffer_lock:
                for store_id in list(self._event_buffer):
                    self._recompute_risk(store_id)

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    async def _emit_event(self, ev: dict, store_id: str) -> None:
        """Push an event to the in-memory log, WebSocket, and MQTT."""
        # Append to recent events.
        self.recent_events[store_id].append(ev)

        # WebSocket broadcast.
        if self._ws_broadcast:
            try:
                await self._ws_broadcast(ev)
            except Exception as exc:  # noqa: BLE001
                logger.debug("WS broadcast failed | error=%s", exc)

        # MQTT publish.
        topic = self._mqtt.events_topic(store_id)
        self._mqtt.publish(topic, ev)

    # ------------------------------------------------------------------
    # Heatmap
    # ------------------------------------------------------------------

    def _update_heatmap(
        self,
        store_id: str,
        camera_id: str,
        frame: np.ndarray,
    ) -> None:
        """
        Update the heatmap grid for a store using frame-level motion energy.

        Motion is approximated as mean absolute deviation of down-sampled
        grayscale frame (a lightweight proxy until a proper optical-flow
        analyzer is plugged in).
        """
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Down-sample to grid resolution.
            small = cv2.resize(gray, (_HEATMAP_COLS, _HEATMAP_ROWS))
            activity = small.astype(float) / 255.0

            store_heatmaps = self.heatmaps.setdefault(store_id, {})
            for window in ("hourly", "daily"):
                grid = store_heatmaps.setdefault(
                    window,
                    {
                        "rows": _HEATMAP_ROWS,
                        "cols": _HEATMAP_COLS,
                        "cells": {},
                    },
                )
                alpha = 0.1  # EMA blend factor
                for r in range(_HEATMAP_ROWS):
                    for c in range(_HEATMAP_COLS):
                        key = f"{r},{c}"
                        prev = grid["cells"].get(key, 0.0)
                        grid["cells"][key] = round(
                            (1 - alpha) * prev + alpha * float(activity[r, c]), 4
                        )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Heatmap update failed | store=%s error=%s", store_id, exc)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _camera_to_store_id(cam) -> str:  # noqa: ANN001
        prefix = cam.location.split("–")[0].strip()
        return prefix.lower().replace(" ", "_")

    @staticmethod
    def _normalise_event(raw: Any, camera_id: str, store_id: str) -> dict:
        """
        Convert an analyzer result (dataclass or dict) to a canonical event dict.
        """
        # ── TamperDetector ──────────────────────────────────────────────────
        if isinstance(raw, TamperEvent):
            return {
                "incident_id": str(uuid.uuid4()),
                "type": "tamper",
                "camera_id": camera_id,
                "store_id": store_id,
                "severity": "high",
                "timestamp": raw.timestamp,
                "description": f"Camera tamper detected: {raw.tamper_type}",
                "metadata": {
                    "tamper_type": raw.tamper_type,
                    "confidence": raw.confidence,
                    "snapshot_b64": raw.frame_snapshot_b64[:64] + "...",
                },
                "acknowledged": False,
                "snapshot_url": None,
            }

        # ── ShopliftingDetector ─────────────────────────────────────────────
        if isinstance(raw, ShopliftingEvent):
            return {
                "incident_id": str(uuid.uuid4()),
                "type": "shoplifting",
                "camera_id": camera_id,
                "store_id": store_id,
                "severity": raw.severity.upper(),
                "timestamp": raw.timestamp,
                "description": (
                    f"Shoplifting detected – {raw.event_subtype} "
                    f"(track #{raw.person_track_id}, {raw.items_involved} item(s))"
                ),
                "metadata": {
                    "event_subtype": raw.event_subtype,
                    "person_track_id": raw.person_track_id,
                    "confidence": raw.confidence,
                    "bbox": list(raw.bbox),
                    "items_involved": raw.items_involved,
                },
                "acknowledged": False,
                "snapshot_url": None,
            }

        # ── InventoryMovementDetector ───────────────────────────────────────
        if isinstance(raw, InventoryEvent):
            return {
                "incident_id": str(uuid.uuid4()),
                "type": "inventory_movement",
                "camera_id": camera_id,
                "store_id": store_id,
                "severity": raw.severity.upper(),
                "timestamp": raw.timestamp,
                "description": (
                    f"Inventory drop in '{raw.zone_label}': "
                    f"{raw.previous_count} → {raw.current_count} "
                    f"(−{raw.delta} items"
                    + (", person present" if raw.person_present else "")
                    + ")"
                ),
                "metadata": {
                    "zone_label": raw.zone_label,
                    "previous_count": raw.previous_count,
                    "current_count": raw.current_count,
                    "delta": raw.delta,
                    "person_present": raw.person_present,
                },
                "acknowledged": False,
                "snapshot_url": None,
            }

        # ── RestrictedZoneDetector ──────────────────────────────────────────
        if isinstance(raw, ZoneEntryEvent):
            return {
                "incident_id": str(uuid.uuid4()),
                "type": "restricted_zone",
                "camera_id": camera_id,
                "store_id": store_id,
                "severity": raw.severity.upper(),
                "timestamp": raw.timestamp,
                "description": (
                    f"Person entered restricted zone '{raw.zone_name}' "
                    f"(track #{raw.person_track_id})"
                ),
                "metadata": {
                    "zone_name": raw.zone_name,
                    "person_track_id": raw.person_track_id,
                    "confidence": raw.confidence,
                    "bbox": list(raw.bbox),
                },
                "acknowledged": False,
                "snapshot_url": None,
            }

        # ── QueueLengthAnalyzer ─────────────────────────────────────────────
        if isinstance(raw, QueueEvent):
            return {
                "incident_id": str(uuid.uuid4()),
                "type": "queue_length",
                "camera_id": camera_id,
                "store_id": store_id,
                "severity": raw.severity.upper(),
                "timestamp": raw.timestamp,
                "description": (
                    f"Queue '{raw.zone_label}' exceeded limit: "
                    f"{raw.queue_length}/{raw.max_allowed} people "
                    f"(est. wait {raw.estimated_wait_minutes} min)"
                ),
                "metadata": {
                    "zone_label": raw.zone_label,
                    "queue_length": raw.queue_length,
                    "max_allowed": raw.max_allowed,
                    "estimated_wait_minutes": raw.estimated_wait_minutes,
                },
                "acknowledged": False,
                "snapshot_url": None,
            }

        # ── FallDetector ────────────────────────────────────────────────────
        if isinstance(raw, FallEvent):
            return {
                "incident_id": str(uuid.uuid4()),
                "type": "fall_detection",
                "camera_id": camera_id,
                "store_id": store_id,
                "severity": raw.severity.upper(),
                "timestamp": raw.timestamp,
                "description": (
                    f"Person fall detected (track #{raw.person_track_id}, "
                    f"method={raw.method}, {raw.duration_frames} frames)"
                ),
                "metadata": {
                    "person_track_id": raw.person_track_id,
                    "method": raw.method,
                    "confidence": raw.confidence,
                    "bbox": list(raw.bbox),
                    "duration_frames": raw.duration_frames,
                },
                "acknowledged": False,
                "snapshot_url": None,
            }

        # ── Generic dict pass-through ────────────────────────────────────────
        if isinstance(raw, dict):
            raw.setdefault("incident_id", str(uuid.uuid4()))
            raw.setdefault("camera_id", camera_id)
            raw.setdefault("store_id", store_id)
            raw.setdefault("timestamp", datetime.now(tz=timezone.utc))
            raw.setdefault("severity", "low")
            raw.setdefault("acknowledged", False)
            return raw

        # ── Unknown type ─────────────────────────────────────────────────────
        return {
            "incident_id": str(uuid.uuid4()),
            "type": "unknown",
            "camera_id": camera_id,
            "store_id": store_id,
            "severity": "LOW",
            "timestamp": datetime.now(tz=timezone.utc),
            "description": str(raw),
            "metadata": {},
            "acknowledged": False,
            "snapshot_url": None,
        }

    @staticmethod
    def _enhance_low_light(camera_id: str, frame: np.ndarray) -> np.ndarray:
        """
        Placeholder for LowLightEnhancer.

        Currently applies CLAHE histogram equalisation on the L channel
        of the LAB colour space as a lightweight substitute.
        """
        try:
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l_ch, a_ch, b_ch = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l_eq = clahe.apply(l_ch)
            merged = cv2.merge([l_eq, a_ch, b_ch])
            return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
        except Exception:  # noqa: BLE001
            return frame

    @staticmethod
    def _annotate_frame(frame: np.ndarray, events: List[dict]) -> np.ndarray:
        """
        Draw a minimal overlay on the frame: timestamp and event count.
        """
        annotated = frame.copy()
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        cv2.putText(
            annotated, ts, (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
        )
        if events:
            label = f"Events: {len(events)}"
            cv2.putText(
                annotated, label, (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
            )
        return annotated

    # ------------------------------------------------------------------
    # Public introspection
    # ------------------------------------------------------------------

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def is_running(self) -> bool:
        return self._started
