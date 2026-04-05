"""
health_monitor.py
=================
Background daemon that periodically polls ``StreamManager.is_healthy()`` for
every registered camera and exposes a thread-safe health status dictionary
to the rest of the Vantag backend (API layer, alerting, etc.).

Usage
-----
    monitor = HealthMonitor(stream_manager, poll_interval=5.0)
    monitor.start()

    # From any thread:
    status = monitor.get_status()
    # {"cam-01": {"healthy": True, "last_checked": "2026-04-06T10:00:00Z",
    #              "consecutive_failures": 0}, ...}

    monitor.stop()
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict

from .stream_manager import StreamManager

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Daemon thread that polls ``StreamManager`` health and maintains a
    publicly readable status dict.

    Parameters
    ----------
    stream_manager:
        A started ``StreamManager`` instance.
    poll_interval:
        Seconds between consecutive health polls (default 5 s).
    """

    def __init__(
        self,
        stream_manager: StreamManager,
        poll_interval: float = 5.0,
    ) -> None:
        self._sm = stream_manager
        self._poll_interval = poll_interval

        # Shared state – protected by _lock.
        self._status: Dict[str, dict] = {}
        self._lock = threading.Lock()

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background polling thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("HealthMonitor.start() called but thread already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="health-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "HealthMonitor started | poll_interval=%.1fs", self._poll_interval
        )

    def stop(self) -> None:
        """Signal the polling thread to exit and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 2.0)
        self._thread = None
        logger.info("HealthMonitor stopped.")

    # ------------------------------------------------------------------
    # Status access
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, dict]:
        """
        Return a snapshot of camera health status.

        Returns a shallow copy of the internal dict so callers cannot
        inadvertently corrupt shared state.

        Schema per camera
        -----------------
        {
            "healthy": bool,
            "last_checked": str   (ISO-8601 UTC),
            "consecutive_failures": int,
        }
        """
        with self._lock:
            return {
                cam_id: dict(entry)
                for cam_id, entry in self._status.items()
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main polling loop."""
        while not self._stop_event.is_set():
            self._poll()
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll(self) -> None:
        """Check every active camera and update the shared status dict."""
        camera_ids = self._sm.worker_ids()
        ts = datetime.now(tz=timezone.utc).isoformat()

        with self._lock:
            for cam_id in camera_ids:
                healthy = self._sm.is_healthy(cam_id)
                prev = self._status.get(cam_id, {"consecutive_failures": 0})

                if healthy:
                    consecutive_failures = 0
                else:
                    consecutive_failures = prev.get("consecutive_failures", 0) + 1

                self._status[cam_id] = {
                    "healthy": healthy,
                    "last_checked": ts,
                    "consecutive_failures": consecutive_failures,
                }

                if not healthy:
                    logger.warning(
                        "Camera unhealthy | camera_id=%s consecutive_failures=%d",
                        cam_id,
                        consecutive_failures,
                    )
                else:
                    logger.debug("Camera healthy | camera_id=%s", cam_id)

            # Remove stale entries for cameras that are no longer managed.
            active = set(camera_ids)
            stale = [cid for cid in list(self._status) if cid not in active]
            for cid in stale:
                del self._status[cid]
                logger.debug("Removed stale health entry | camera_id=%s", cid)
