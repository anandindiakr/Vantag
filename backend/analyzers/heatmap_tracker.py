"""
heatmap_tracker.py
==================
Customer journey heatmap tracker for the Vantag platform.

Maintains a 2-D numpy grid (``grid_resolution × grid_resolution``) where
each cell accumulates the number of person-centroid observations that fall
within the corresponding spatial region of the camera frame.

Aggregation:
    * **Hourly** – the current running grid is snapshotted once per hour and
      stored in a ring buffer of the last 24 hourly grids.
    * **Daily**  – the sum of the last 24 hourly snapshots is stored once
      per UTC day in a ring buffer of the last 7 daily grids.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection import with fallback stub.
# ---------------------------------------------------------------------------

try:
    from backend.inference.yolo_engine import Detection  # type: ignore[import]
except ImportError:
    from dataclasses import dataclass as _dc

    @_dc
    class Detection:  # type: ignore[no-redef]
        track_id: int = -1
        class_id: int = 0
        class_name: str = ""
        confidence: float = 0.0
        bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
        keypoints: Optional[list] = None


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULTS: Dict = {
    "grid_resolution": 64,
    "accumulate_seconds": 3600.0,
}


# ---------------------------------------------------------------------------
# _Snapshot – single snapshotted heatmap
# ---------------------------------------------------------------------------

@dataclass
class _Snapshot:
    grid: np.ndarray          # (R, R) float64 normalised to [0, 1]
    captured_at: datetime
    window: str               # 'hourly' | 'daily'


# ---------------------------------------------------------------------------
# HeatmapTracker
# ---------------------------------------------------------------------------

class HeatmapTracker:
    """
    Stateful customer journey heatmap tracker bound to a single camera.

    Parameters
    ----------
    camera_id:
        Identifier of the camera.
    config:
        Dict of configuration overrides (see ``_DEFAULTS``).
    """

    def __init__(self, camera_id: str, config: Dict) -> None:
        self._camera_id = camera_id

        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._resolution: int = int(cfg["grid_resolution"])
        self._accumulate_seconds: float = float(cfg["accumulate_seconds"])

        # Running accumulation grid (raw counts).
        self._grid: np.ndarray = np.zeros(
            (self._resolution, self._resolution), dtype=np.float64
        )

        # Snapshot ring buffers.
        self._hourly_snapshots: Deque[_Snapshot] = deque(maxlen=24)
        self._daily_snapshots: Deque[_Snapshot] = deque(maxlen=7)

        # Timing for automatic snapshotting.
        self._last_hourly_snap: Optional[datetime] = None
        self._last_daily_snap: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize(self, grid: np.ndarray) -> np.ndarray:
        """Normalise *grid* to [0, 1]."""
        max_val = float(grid.max())
        if max_val == 0.0:
            return grid.copy()
        return (grid / max_val).astype(np.float64)

    def _grid_to_list(self, grid: np.ndarray) -> List[List[float]]:
        return grid.tolist()

    def _take_hourly_snapshot(self, now: datetime) -> None:
        snap = _Snapshot(
            grid=self._normalize(self._grid),
            captured_at=now,
            window="hourly",
        )
        self._hourly_snapshots.append(snap)
        logger.debug(
            "HeatmapTracker: hourly snapshot taken at %s.",
            now.isoformat(),
        )

    def _take_daily_snapshot(self, now: datetime) -> None:
        if self._hourly_snapshots:
            stacked = np.sum(
                [s.grid for s in self._hourly_snapshots], axis=0
            )
        else:
            stacked = self._grid.copy()

        snap = _Snapshot(
            grid=self._normalize(stacked),
            captured_at=now,
            window="daily",
        )
        self._daily_snapshots.append(snap)
        logger.info(
            "HeatmapTracker: daily snapshot taken at %s.",
            now.isoformat(),
        )

    def _maybe_snapshot(self, now: datetime) -> None:
        """Trigger hourly / daily snapshots when their window has elapsed."""
        # Hourly snapshot.
        if self._last_hourly_snap is None:
            self._last_hourly_snap = now
        elif (now - self._last_hourly_snap) >= timedelta(hours=1):
            self._take_hourly_snapshot(now)
            self._last_hourly_snap = now
            self._grid[:] = 0.0  # Reset accumulation after snapshot.

        # Daily snapshot (taken once per UTC day).
        today = now.date()
        if self._last_daily_snap is None:
            self._last_daily_snap = now
        elif now.date() > self._last_daily_snap.date():
            self._take_daily_snapshot(now)
            self._last_daily_snap = now

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        detections: List[Detection],
        frame_shape: Tuple[int, int],
    ) -> None:
        """
        Increment grid cells for each ``'person'`` centroid in *detections*.

        Parameters
        ----------
        detections:
            Frame detections.
        frame_shape:
            ``(height, width)`` of the source frame for coordinate mapping.
        """
        fh, fw = frame_shape[:2]
        if fh == 0 or fw == 0:
            return

        for det in detections:
            if det.class_name.lower() != "person":
                continue
            x1, y1, x2, y2 = det.bbox
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            # Map to grid indices.
            col = int(cx / fw * self._resolution)
            row = int(cy / fh * self._resolution)
            col = min(max(col, 0), self._resolution - 1)
            row = min(max(row, 0), self._resolution - 1)
            self._grid[row, col] += 1.0

    def analyze(
        self,
        detections: List[Detection],
        frame_shape: Tuple[int, int],
        timestamp: float,
    ) -> None:
        """
        Update the heatmap and trigger periodic snapshots.

        Parameters
        ----------
        detections:
            Frame detections.
        frame_shape:
            ``(height, width)`` tuple.
        timestamp:
            Unix wall-clock timestamp (``time.time()``).
        """
        self.update(detections, frame_shape)
        now = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        self._maybe_snapshot(now)

    def get_heatmap(self, window: str = "hourly") -> Dict:
        """
        Return a normalised heatmap for the requested aggregation window.

        Parameters
        ----------
        window:
            ``'current'`` – live accumulation grid (not yet snapshotted).
            ``'hourly'``  – most recent hourly snapshot.
            ``'daily'``   – most recent daily snapshot.

        Returns
        -------
        Dict with keys:
            ``'camera_id'``, ``'window'``, ``'grid'`` (nested list),
            ``'resolution'``, ``'captured_at'`` (ISO string or ``None``).
        """
        if window == "current":
            grid_data = self._normalize(self._grid)
            captured_at = None
        elif window == "hourly":
            if self._hourly_snapshots:
                snap = self._hourly_snapshots[-1]
                grid_data = snap.grid
                captured_at = snap.captured_at.isoformat()
            else:
                grid_data = self._normalize(self._grid)
                captured_at = None
        elif window == "daily":
            if self._daily_snapshots:
                snap = self._daily_snapshots[-1]
                grid_data = snap.grid
                captured_at = snap.captured_at.isoformat()
            else:
                grid_data = self._normalize(self._grid)
                captured_at = None
        else:
            raise ValueError(f"Unknown window '{window}'. Choose 'current', 'hourly', or 'daily'.")

        return {
            "camera_id": self._camera_id,
            "window": window,
            "grid": self._grid_to_list(grid_data),
            "resolution": self._resolution,
            "captured_at": captured_at,
        }

    def reset(self) -> None:
        """Clear the live accumulation grid (snapshots are preserved)."""
        self._grid[:] = 0.0
        logger.info("HeatmapTracker: live grid reset for camera '%s'.", self._camera_id)

    def export_snapshot(self) -> Dict:
        """
        Return a full export dict containing the current live grid plus all
        stored hourly and daily snapshots.

        Returns
        -------
        Dict with keys:
            ``'camera_id'``, ``'resolution'``, ``'live_grid'``,
            ``'hourly_snapshots'`` (list of dicts), ``'daily_snapshots'`` (list of dicts).
        """
        def _snap_to_dict(s: _Snapshot) -> Dict:
            return {
                "grid": self._grid_to_list(s.grid),
                "captured_at": s.captured_at.isoformat(),
                "window": s.window,
            }

        return {
            "camera_id": self._camera_id,
            "resolution": self._resolution,
            "live_grid": self._grid_to_list(self._normalize(self._grid)),
            "hourly_snapshots": [_snap_to_dict(s) for s in self._hourly_snapshots],
            "daily_snapshots": [_snap_to_dict(s) for s in self._daily_snapshots],
        }
