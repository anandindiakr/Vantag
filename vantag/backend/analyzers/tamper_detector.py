"""
tamper_detector.py
==================
Real-time camera tamper detection for the Vantag platform.

Detects three classes of tampering:
  * BLOCKED      – lens physically covered; mean brightness collapses.
  * STATIC       – spray-painted or scene frozen; per-pixel variance is
                   abnormally low across the rolling frame buffer.
  * TILTED       – camera knocked/rotated; dominant Hough-line orientation
                   shifts by more than a configured angular threshold.

All detection is performed in-process using NumPy and OpenCV only.
No network calls are made; events are returned as dataclass objects for the
upstream MQTT / scoring layers to consume.
"""

from __future__ import annotations

import base64
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tamper type constants
# ---------------------------------------------------------------------------

class TamperType:
    BLOCKED = "BLOCKED"
    STATIC = "STATIC"
    TILTED = "TILTED"


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------

@dataclass
class TamperEvent:
    """Emitted whenever a tamper condition is confirmed."""
    camera_id: str
    timestamp: datetime
    tamper_type: str                  # TamperType constant
    confidence: float                 # 0.0 – 1.0
    frame_snapshot_b64: str           # base-64 encoded JPEG of the offending frame


# ---------------------------------------------------------------------------
# Default thresholds (all overridable via config dict)
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, float | int] = {
    # BLOCKED
    "blocked_brightness_threshold": 10.0,   # mean pixel value (0-255)
    "blocked_duration_seconds": 2.0,        # must persist this long

    # STATIC
    "static_variance_threshold": 8.0,       # tightened — only flag near-zero variance (lens covered)
    "static_duration_seconds": 5.0,         # must persist this long

    # TILTED
    "tilted_angle_delta_degrees": 30.0,     # raised — require a larger angular shift
    "tilted_confirmation_frames": 8,        # more frames needed to confirm

    # Rolling buffer
    "frame_buffer_size": 30,               # max frames kept for variance calc

    # Cooldown — minimum seconds between events of the same type on the same camera
    "cooldown_seconds": 300,               # 5 minutes between repeated tamper alerts
}


# ---------------------------------------------------------------------------
# TamperDetector
# ---------------------------------------------------------------------------

class TamperDetector:
    """
    Stateful, single-camera tamper detector.

    Parameters
    ----------
    camera_id:
        Identifier of the camera this detector is bound to.
    config:
        Optional dict of threshold overrides.  Unknown keys are ignored.
    """

    def __init__(
        self,
        camera_id: str,
        config: Optional[Dict] = None,
    ) -> None:
        self._camera_id = camera_id
        cfg = dict(_DEFAULTS)
        if config:
            cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        # ---- thresholds ----
        self._brightness_thresh: float = float(cfg["blocked_brightness_threshold"])
        self._blocked_duration: float = float(cfg["blocked_duration_seconds"])

        self._variance_thresh: float = float(cfg["static_variance_threshold"])
        self._static_duration: float = float(cfg["static_duration_seconds"])

        self._tilt_delta: float = float(cfg["tilted_angle_delta_degrees"])
        self._tilt_confirm: int = int(cfg["tilted_confirmation_frames"])

        buf: int = int(cfg["frame_buffer_size"])
        self._cooldown: float = float(cfg["cooldown_seconds"])

        # ---- rolling frame buffer (grayscale uint8) ----
        self._frame_buf: Deque[np.ndarray] = deque(maxlen=buf)

        # ---- BLOCKED state ----
        self._blocked_since: Optional[float] = None       # monotonic time
        self._blocked_event_emitted: bool = False

        # ---- STATIC state ----
        self._static_since: Optional[float] = None
        self._static_event_emitted: bool = False

        # ---- TILTED state ----
        self._last_dominant_angle: Optional[float] = None
        self._tilt_confirm_count: int = 0
        self._tilt_event_emitted: bool = False

        # ---- Per-type cooldown tracker ----
        # Stores monotonic time of last emission for each tamper type
        self._last_emitted: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, frame: np.ndarray) -> Optional[TamperEvent]:
        """
        Analyse a single BGR frame and return a ``TamperEvent`` if a new
        tamper condition is confirmed, otherwise ``None``.

        Only the *first* event for each continuous tamper episode is
        returned; subsequent calls within the same episode return ``None``
        to avoid flooding downstream consumers.  The state resets once the
        condition clears.
        """
        if frame is None or frame.size == 0:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self._frame_buf.append(gray)
        now = time.monotonic()  # noqa: F821  – imported below

        # Priority: BLOCKED > STATIC > TILTED (most severe first)
        event = (
            self._check_blocked(gray, frame, now)
            or self._check_static(frame, now)
            or self._check_tilted(gray, frame, now)
        )

        # ── Cooldown gate ────────────────────────────────────────────────────
        # Suppress repeated events of the same type within the cooldown window.
        # This prevents a single continuous tamper condition from flooding the
        # incident log with hundreds of identical alerts.
        if event is not None:
            last = self._last_emitted.get(event.tamper_type, 0.0)
            if now - last < self._cooldown:
                return None            # silently suppress — still within cooldown
            self._last_emitted[event.tamper_type] = now

        return event

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    def _check_blocked(
        self,
        gray: np.ndarray,
        bgr: np.ndarray,
        now: float,
    ) -> Optional[TamperEvent]:
        mean_brightness: float = float(np.mean(gray))

        if mean_brightness < self._brightness_thresh:
            if self._blocked_since is None:
                self._blocked_since = now
                self._blocked_event_emitted = False
            elif (
                not self._blocked_event_emitted
                and (now - self._blocked_since) >= self._blocked_duration
            ):
                self._blocked_event_emitted = True
                confidence = min(1.0, 1.0 - mean_brightness / self._brightness_thresh)
                logger.warning(
                    "TAMPER BLOCKED detected | camera_id=%s brightness=%.2f",
                    self._camera_id,
                    mean_brightness,
                )
                return self._make_event(TamperType.BLOCKED, confidence, bgr)
        else:
            # Condition cleared – reset state.
            self._blocked_since = None
            self._blocked_event_emitted = False

        return None

    def _check_static(
        self,
        bgr: np.ndarray,
        now: float,
    ) -> Optional[TamperEvent]:
        if len(self._frame_buf) < 2:
            return None

        # Stack the last N grayscale frames and compute per-pixel variance.
        stack = np.stack(list(self._frame_buf), axis=0).astype(np.float32)
        variance: float = float(np.mean(np.var(stack, axis=0)))

        if variance < self._variance_thresh:
            if self._static_since is None:
                self._static_since = now
                self._static_event_emitted = False
            elif (
                not self._static_event_emitted
                and (now - self._static_since) >= self._static_duration
            ):
                self._static_event_emitted = True
                # Confidence scales inversely with variance.
                confidence = min(
                    1.0,
                    max(0.0, 1.0 - variance / self._variance_thresh),
                )
                logger.warning(
                    "TAMPER STATIC detected | camera_id=%s variance=%.4f",
                    self._camera_id,
                    variance,
                )
                return self._make_event(TamperType.STATIC, confidence, bgr)
        else:
            self._static_since = None
            self._static_event_emitted = False

        return None

    def _check_tilted(
        self,
        gray: np.ndarray,
        bgr: np.ndarray,
        now: float,
    ) -> Optional[TamperEvent]:
        dominant = self._dominant_edge_angle(gray)
        if dominant is None:
            return None

        if self._last_dominant_angle is None:
            self._last_dominant_angle = dominant
            return None

        delta = abs(dominant - self._last_dominant_angle)
        # Wrap around 180° periodically.
        delta = min(delta, 180.0 - delta) if delta > 90.0 else delta

        if delta >= self._tilt_delta:
            self._tilt_confirm_count += 1
            if (
                self._tilt_confirm_count >= self._tilt_confirm
                and not self._tilt_event_emitted
            ):
                self._tilt_event_emitted = True
                confidence = min(1.0, delta / 90.0)
                logger.warning(
                    "TAMPER TILTED detected | camera_id=%s angle_delta=%.1f°",
                    self._camera_id,
                    delta,
                )
                return self._make_event(TamperType.TILTED, confidence, bgr)
        else:
            # Condition resolved – update reference angle.
            # Only reset the emitted flag if the cooldown has also passed,
            # so a brief normalisation does NOT immediately re-arm the detector.
            self._last_dominant_angle = dominant
            self._tilt_confirm_count = 0
            last = self._last_emitted.get("TILTED", 0.0)
            import time as _time
            if _time.monotonic() - last >= self._cooldown:
                self._tilt_event_emitted = False

        return None

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dominant_edge_angle(gray: np.ndarray) -> Optional[float]:
        """
        Compute the dominant line angle (0–180°) using Canny edge detection
        and a probabilistic Hough transform.  Returns ``None`` when no
        lines are found (e.g. very dark or completely uniform frame).
        """
        edges = cv2.Canny(gray, threshold1=50, threshold2=150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=80,
            minLineLength=60,
            maxLineGap=10,
        )
        if lines is None or len(lines) == 0:
            return None

        angles: list[float] = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0 and dy == 0:
                continue
            angle = float(np.degrees(np.arctan2(dy, dx))) % 180.0
            angles.append(angle)

        if not angles:
            return None

        return float(np.median(angles))

    def _make_event(
        self,
        tamper_type: str,
        confidence: float,
        bgr: np.ndarray,
    ) -> TamperEvent:
        """Encode the frame as a JPEG and build a ``TamperEvent``."""
        _, jpeg_buf = cv2.imencode(
            ".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 70]
        )
        snapshot_b64 = base64.b64encode(jpeg_buf.tobytes()).decode("ascii")

        return TamperEvent(
            camera_id=self._camera_id,
            timestamp=datetime.now(tz=timezone.utc),
            tamper_type=tamper_type,
            confidence=round(confidence, 4),
            frame_snapshot_b64=snapshot_b64,
        )


# ---------------------------------------------------------------------------
# Deferred import – avoids circular-import issues and keeps class body clean.
# ---------------------------------------------------------------------------
import time  # noqa: E402  (intentional placement after class definition)
