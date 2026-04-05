"""
backend/inference/model_scheduler.py
=====================================
GPU model priority scheduler for the Vantag platform.

``ModelScheduler`` manages time-sliced GPU access across three concurrent
inference workloads:

1. **Primary YOLO detector** — runs every frame; always has priority.
2. **Pose estimator** — FPS-limited and skipped when GPU load is high.
3. **Face recogniser** — lowest priority, most aggressively throttled.

The scheduler is *stateful* and *thread-safe*; a single instance should be
shared across all pipeline threads.

Usage
-----
::

    scheduler = ModelScheduler(config={
        "gpu_load_threshold": 0.80,
        "pose_fps_limit": 5,
        "face_fps_limit": 2,
    })

    # In the per-frame pipeline loop:
    scheduler.record_gpu_load()   # samples nvidia-smi once per call

    if scheduler.should_run_pose():
        pose_results = pose_engine.detect_pose(frame)

    if scheduler.should_run_face():
        face_results = face_engine.recognize(frame)
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_GPU_LOAD_THRESHOLD: float = 0.80
_DEFAULT_POSE_FPS_LIMIT: int = 5
_DEFAULT_FACE_FPS_LIMIT: int = 2

# How often (seconds) to re-query nvidia-smi.  Querying every frame is
# expensive; we amortise the cost by caching the last reading.
_GPU_SAMPLE_INTERVAL: float = 1.0


# ---------------------------------------------------------------------------
# _FrameRateLimiter
# ---------------------------------------------------------------------------

class _FrameRateLimiter:
    """
    Thread-safe token-bucket rate limiter expressed as *frames per second*.

    ``allow()`` returns ``True`` at most *fps_limit* times per second and
    ``False`` otherwise.  When *fps_limit* is 0 or negative the limiter
    always returns ``False`` (fully suppressed).
    """

    def __init__(self, fps_limit: int) -> None:
        self._fps_limit = max(0, fps_limit)
        self._lock = threading.Lock()
        self._last_allowed_ts: float = 0.0  # monotonic timestamp

    @property
    def fps_limit(self) -> int:
        return self._fps_limit

    @fps_limit.setter
    def fps_limit(self, value: int) -> None:
        with self._lock:
            self._fps_limit = max(0, value)

    def allow(self) -> bool:
        """Return ``True`` if a frame should be processed at this point in time."""
        if self._fps_limit <= 0:
            return False
        interval = 1.0 / self._fps_limit
        now = time.monotonic()
        with self._lock:
            if now - self._last_allowed_ts >= interval:
                self._last_allowed_ts = now
                return True
        return False


# ---------------------------------------------------------------------------
# ModelScheduler
# ---------------------------------------------------------------------------

class ModelScheduler:
    """
    GPU model priority scheduler.

    Parameters
    ----------
    config:
        Optional configuration dict.  Recognised keys:

        * ``gpu_load_threshold`` (float, 0–1) — GPU utilisation fraction
          above which pose and face inference are skipped.  Default: ``0.80``.
        * ``pose_fps_limit`` (int) — Maximum pose inference calls per second.
          Default: ``5``.
        * ``face_fps_limit`` (int) — Maximum face recognition calls per
          second.  Default: ``2``.
    """

    def __init__(self, config: Optional[Dict] = None) -> None:
        cfg = config or {}

        self._gpu_load_threshold: float = float(
            cfg.get("gpu_load_threshold", _DEFAULT_GPU_LOAD_THRESHOLD)
        )
        pose_fps: int = int(cfg.get("pose_fps_limit", _DEFAULT_POSE_FPS_LIMIT))
        face_fps: int = int(cfg.get("face_fps_limit", _DEFAULT_FACE_FPS_LIMIT))

        self._pose_limiter = _FrameRateLimiter(pose_fps)
        self._face_limiter = _FrameRateLimiter(face_fps)

        # Cached GPU load state.
        self._lock = threading.Lock()
        self._current_gpu_load: float = 0.0   # fraction [0, 1]
        self._last_gpu_sample_ts: float = 0.0  # monotonic
        self._gpu_overloaded: bool = False

        # Per-model run counters (cumulative, for diagnostics).
        self._pose_runs: int = 0
        self._face_runs: int = 0
        self._pose_skips: int = 0
        self._face_skips: int = 0

        logger.info(
            "ModelScheduler initialised — gpu_load_threshold=%.0f%%, "
            "pose_fps=%d, face_fps=%d.",
            self._gpu_load_threshold * 100,
            pose_fps,
            face_fps,
        )

    # ------------------------------------------------------------------
    # GPU load monitoring
    # ------------------------------------------------------------------

    def _query_nvidia_smi(self) -> Optional[float]:
        """
        Query current GPU utilisation via ``nvidia-smi``.

        Returns the utilisation as a fraction [0, 1], or ``None`` if the
        query fails (e.g. on a host without an NVIDIA GPU).
        """
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode != 0:
                logger.debug(
                    "ModelScheduler: nvidia-smi returned code %d: %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return None
            lines = result.stdout.strip().splitlines()
            if not lines:
                return None
            # If multiple GPUs, take the first (Jetson has one GPU).
            util_pct = float(lines[0].strip())
            return util_pct / 100.0
        except FileNotFoundError:
            logger.debug("ModelScheduler: nvidia-smi not found on this host.")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("ModelScheduler: nvidia-smi query timed out.")
            return None
        except (ValueError, IndexError) as exc:
            logger.debug("ModelScheduler: could not parse nvidia-smi output: %s", exc)
            return None

    def record_gpu_load(self) -> float:
        """
        Sample GPU utilisation and update the internal overload flag.

        This method is rate-limited internally (at most once per
        ``_GPU_SAMPLE_INTERVAL`` seconds) so it is safe to call on every
        frame without introducing latency spikes.

        Returns
        -------
        float
            Current GPU utilisation as a fraction [0, 1].  Returns the
            cached value when the sample interval has not yet elapsed.
        """
        now = time.monotonic()
        with self._lock:
            if now - self._last_gpu_sample_ts < _GPU_SAMPLE_INTERVAL:
                return self._current_gpu_load

        # Release the lock while querying to avoid blocking callers.
        util = self._query_nvidia_smi()

        with self._lock:
            self._last_gpu_sample_ts = time.monotonic()
            if util is not None:
                self._current_gpu_load = util
                was_overloaded = self._gpu_overloaded
                self._gpu_overloaded = util >= self._gpu_load_threshold
                if self._gpu_overloaded != was_overloaded:
                    if self._gpu_overloaded:
                        logger.warning(
                            "ModelScheduler: GPU load %.0f%% ≥ threshold %.0f%% "
                            "— pose and face inference SUSPENDED.",
                            util * 100,
                            self._gpu_load_threshold * 100,
                        )
                    else:
                        logger.info(
                            "ModelScheduler: GPU load %.0f%% — "
                            "pose and face inference RESUMED.",
                            util * 100,
                        )
            return self._current_gpu_load

    # ------------------------------------------------------------------
    # Scheduling gates
    # ------------------------------------------------------------------

    def should_run_pose(self) -> bool:
        """
        Return ``True`` if the pose estimator should execute for this frame.

        Blocked when:
        * GPU utilisation ≥ ``gpu_load_threshold``, OR
        * The pose FPS limiter denies the frame.
        """
        with self._lock:
            overloaded = self._gpu_overloaded

        if overloaded:
            with self._lock:
                self._pose_skips += 1
            return False

        allowed = self._pose_limiter.allow()
        with self._lock:
            if allowed:
                self._pose_runs += 1
            else:
                self._pose_skips += 1
        return allowed

    def should_run_face(self) -> bool:
        """
        Return ``True`` if the face recogniser should execute for this frame.

        Blocked when:
        * GPU utilisation ≥ ``gpu_load_threshold``, OR
        * The face FPS limiter denies the frame.
        """
        with self._lock:
            overloaded = self._gpu_overloaded

        if overloaded:
            with self._lock:
                self._face_skips += 1
            return False

        allowed = self._face_limiter.allow()
        with self._lock:
            if allowed:
                self._face_runs += 1
            else:
                self._face_skips += 1
        return allowed

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def stats(self) -> Dict:
        """
        Return a snapshot of scheduler statistics.

        Returns
        -------
        dict with keys:
            ``gpu_load_fraction``, ``gpu_overloaded``,
            ``pose_runs``, ``pose_skips``,
            ``face_runs``, ``face_skips``.
        """
        with self._lock:
            return {
                "gpu_load_fraction": round(self._current_gpu_load, 4),
                "gpu_overloaded": self._gpu_overloaded,
                "pose_fps_limit": self._pose_limiter.fps_limit,
                "face_fps_limit": self._face_limiter.fps_limit,
                "gpu_load_threshold": self._gpu_load_threshold,
                "pose_runs": self._pose_runs,
                "pose_skips": self._pose_skips,
                "face_runs": self._face_runs,
                "face_skips": self._face_skips,
            }

    def update_thresholds(
        self,
        *,
        gpu_load_threshold: Optional[float] = None,
        pose_fps_limit: Optional[int] = None,
        face_fps_limit: Optional[int] = None,
    ) -> None:
        """
        Dynamically update scheduler parameters at runtime.

        Parameters
        ----------
        gpu_load_threshold:
            New GPU utilisation threshold (0–1).
        pose_fps_limit:
            New pose inference FPS cap.
        face_fps_limit:
            New face inference FPS cap.
        """
        with self._lock:
            if gpu_load_threshold is not None:
                self._gpu_load_threshold = max(0.0, min(1.0, gpu_load_threshold))
                logger.info(
                    "ModelScheduler: gpu_load_threshold updated to %.0f%%.",
                    self._gpu_load_threshold * 100,
                )
        if pose_fps_limit is not None:
            self._pose_limiter.fps_limit = pose_fps_limit
            logger.info(
                "ModelScheduler: pose_fps_limit updated to %d.", pose_fps_limit
            )
        if face_fps_limit is not None:
            self._face_limiter.fps_limit = face_fps_limit
            logger.info(
                "ModelScheduler: face_fps_limit updated to %d.", face_fps_limit
            )
