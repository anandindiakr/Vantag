"""
stream_manager.py
=================
Manages concurrent RTSP camera streams for the Vantag ingestion layer.

Each camera runs in a dedicated daemon thread that continuously reads frames
from OpenCV VideoCapture (or a GStreamer pipeline on Jetson/aarch64).
Frames are pushed to a bounded per-camera queue; the oldest frame is dropped
automatically when the queue is full.  Disconnected cameras are retried with
exponential back-off up to ``reconnect_backoff_max`` seconds.
"""

from __future__ import annotations

import logging
import platform
import queue
import threading
import time
from typing import Dict, Optional

import cv2
import numpy as np

from .camera_registry import CameraConfig, CameraRegistry

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)
_LOG_FORMAT = (
    "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s"
)
logging.basicConfig(format=_LOG_FORMAT, level=logging.INFO)


# ---------------------------------------------------------------------------
# Internal per-camera worker
# ---------------------------------------------------------------------------

class _CameraWorker:
    """
    Owns a single RTSP stream and runs a read loop in a background thread.
    """

    def __init__(
        self,
        config: CameraConfig,
        buffer_size: int,
        reconnect_backoff_max: int,
    ) -> None:
        self._config = config
        self._buffer_size = buffer_size
        self._backoff_max = reconnect_backoff_max

        self._frame_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=buffer_size)
        self._healthy: bool = False
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API (called from StreamManager)
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"cam-worker-{self._config.id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("Camera worker started | camera_id=%s", self._config.id)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._healthy = False
        logger.info("Camera worker stopped | camera_id=%s", self._config.id)

    def get_frame(self) -> Optional[np.ndarray]:
        """Return the latest queued frame, or None if unavailable."""
        try:
            return self._frame_queue.get_nowait()
        except queue.Empty:
            return None

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_capture(self) -> cv2.VideoCapture:
        """
        Build a cv2.VideoCapture.  On Jetson (aarch64) use a GStreamer
        pipeline that leverages hardware decode; everywhere else use the
        raw RTSP URL.
        """
        url = self._config.rtsp_url

        if platform.machine() == "aarch64":
            pipeline = (
                f"rtspsrc location={url} latency=100 ! "
                "rtph264depay ! h264parse ! nvv4l2decoder ! "
                "nvvidconv ! video/x-raw,format=BGRx ! "
                "videoconvert ! video/x-raw,format=BGR ! "
                "appsink drop=1"
            )
            logger.info(
                "Using GStreamer pipeline for Jetson | camera_id=%s",
                self._config.id,
            )
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            # Force TCP transport to avoid UDP packet loss on LANs.
            # Use rtsp_transport=tcp option in URL to set short open timeout.
            rtsp_url = url
            if "?" not in url and "rtsp://" in url:
                rtsp_url = url  # keep as-is; timeout set via CAP_PROP_OPEN_TIMEOUT
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Limit connection attempt to 8 seconds (avoids 30-s hangs on offline cameras)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8_000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8_000)

        cap.set(cv2.CAP_PROP_FPS, self._config.fps_target)
        return cap

    def _push_frame(self, frame: np.ndarray) -> None:
        """
        Push frame to the bounded queue.  If the queue is full, evict the
        oldest frame before inserting the new one so the consumer always
        receives recent data.
        """
        if self._frame_queue.full():
            try:
                self._frame_queue.get_nowait()  # discard oldest
            except queue.Empty:
                pass
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            pass  # extremely unlikely after eviction – safe to skip

    def _run(self) -> None:
        """Main capture loop with exponential back-off reconnect logic."""
        backoff: float = 1.0

        while not self._stop_event.is_set():
            cap = self._build_capture()

            if not cap.isOpened():
                self._healthy = False
                logger.warning(
                    "Failed to open stream | camera_id=%s url=%s | retrying in %.1fs",
                    self._config.id,
                    self._config.rtsp_url,
                    backoff,
                )
                self._wait(backoff)
                backoff = min(backoff * 2, self._backoff_max)
                continue

            # Successful connection – reset backoff.
            backoff = 1.0
            self._healthy = True
            logger.info(
                "Stream connected | camera_id=%s url=%s",
                self._config.id,
                self._config.rtsp_url,
            )

            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    self._healthy = False
                    logger.warning(
                        "Frame read failed | camera_id=%s | attempting reconnect in %.1fs",
                        self._config.id,
                        backoff,
                    )
                    break  # inner loop – reconnect outer loop takes over

                self._push_frame(frame)

            cap.release()

            if not self._stop_event.is_set():
                self._wait(backoff)
                backoff = min(backoff * 2, self._backoff_max)

    def _wait(self, seconds: float) -> None:
        """Interruptible sleep that respects the stop event."""
        self._stop_event.wait(timeout=seconds)


# ---------------------------------------------------------------------------
# StreamManager
# ---------------------------------------------------------------------------

class StreamManager:
    """
    Manages all camera workers.  Start once, then poll frames via
    ``get_frame`` or ``get_all_frames`` from any thread.

    Parameters
    ----------
    registry:
        A loaded ``CameraRegistry`` instance.
    """

    def __init__(self, registry: CameraRegistry) -> None:
        self._registry = registry
        self._workers: Dict[str, _CameraWorker] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Initialise and start a worker thread for every enabled camera."""
        global_cfg = self._registry.get_global()
        buffer_size: int = int(global_cfg.get("frame_buffer_size", 30))
        backoff_max: int = int(global_cfg.get("reconnect_backoff_max", 64))

        for cam in self._registry.all_cameras():
            if not cam.enabled:
                logger.info(
                    "Skipping disabled camera | camera_id=%s", cam.id
                )
                continue

            worker = _CameraWorker(
                config=cam,
                buffer_size=buffer_size,
                reconnect_backoff_max=backoff_max,
            )
            self._workers[cam.id] = worker
            worker.start()

        logger.info(
            "StreamManager started | active_cameras=%d", len(self._workers)
        )

    def stop(self) -> None:
        """Gracefully stop all camera workers."""
        for camera_id, worker in self._workers.items():
            worker.stop()
        self._workers.clear()
        logger.info("StreamManager stopped.")

    # ------------------------------------------------------------------
    # Frame access
    # ------------------------------------------------------------------

    def get_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """
        Retrieve the next available frame for a camera.

        Returns ``None`` if the camera is unknown or the queue is empty.
        """
        worker = self._workers.get(camera_id)
        if worker is None:
            logger.debug("get_frame: unknown camera_id=%s", camera_id)
            return None
        return worker.get_frame()

    def get_all_frames(self) -> Dict[str, np.ndarray]:
        """
        Retrieve one frame from every camera that has data available.

        Cameras with empty queues are omitted from the result dict.
        """
        frames: Dict[str, np.ndarray] = {}
        for camera_id, worker in self._workers.items():
            frame = worker.get_frame()
            if frame is not None:
                frames[camera_id] = frame
        return frames

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def is_healthy(self, camera_id: str) -> bool:
        """Return True if the camera is connected and producing frames."""
        worker = self._workers.get(camera_id)
        return worker.is_healthy if worker is not None else False

    def worker_ids(self) -> list[str]:
        """Return the list of active (enabled) camera IDs."""
        return list(self._workers.keys())
