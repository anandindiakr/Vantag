"""
risk_scorer.py
==============
Risk score aggregator for the Vantag platform.

Ingests events from all analyser modules, applies configurable per-event-type
weights, and computes a rolling weighted risk score normalised to 0–100.

Severity thresholds:
    * ``'LOW'``     – score < 30
    * ``'MEDIUM'``  – 30 ≤ score < 70
    * ``'HIGH'``    – score ≥ 70
"""

from __future__ import annotations

import logging
import time
from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default weights per event type
# ---------------------------------------------------------------------------

_DEFAULT_WEIGHTS: Dict[str, float] = {
    "sweeping": 25.0,
    "dwell": 10.0,
    "empty_shelf": 5.0,
    "watchlist_match": 30.0,
    "queue": 8.0,
    "accident": 20.0,
    "staff_alert": 12.0,
    "tamper": 35.0,
    "pos_anomaly": 20.0,
}

# Map event *class names* → canonical event_type keys.
_EVENT_TYPE_MAP: Dict[str, str] = {
    "SweepingEvent": "sweeping",
    "DwellEvent": "dwell",
    "ShelfEvent": "empty_shelf",
    "WatchlistMatchEvent": "watchlist_match",
    "QueueEvent": "queue",
    "AccidentEvent": "accident",
    "StaffAlertEvent": "staff_alert",
    "TamperEvent": "tamper",
    "PosAnomalyEvent": "pos_anomaly",
}

_DEFAULTS: Dict = {
    "window_seconds": 300.0,
    "weights": {},
}


# ---------------------------------------------------------------------------
# RiskScore dataclass
# ---------------------------------------------------------------------------

@dataclass
class RiskScore:
    """Point-in-time risk assessment for a single store."""

    store_id: str
    score: float
    """Weighted risk score normalised to [0, 100]."""
    severity: str
    """``'LOW'``, ``'MEDIUM'``, or ``'HIGH'``."""
    timestamp: datetime
    event_counts: Dict[str, int]
    """Count of each event type within the current rolling window."""


# ---------------------------------------------------------------------------
# _EventRecord – internal timestamped event record
# ---------------------------------------------------------------------------

@dataclass
class _EventRecord:
    event_type: str
    weight: float
    timestamp: float   # monotonic


# ---------------------------------------------------------------------------
# RiskScorer
# ---------------------------------------------------------------------------

class RiskScorer:
    """
    Rolling-window risk score aggregator for a single store.

    Parameters
    ----------
    store_id:
        Identifier of the store / installation.
    config:
        Configuration dict with optional keys:

        * ``window_seconds`` (float) – rolling window width (default 300).
        * ``weights`` (dict) – per-event-type weight overrides.
    """

    # Maximum raw weighted sum used for normalisation (one of every event
    # at full weight within a single window).  In practice scores can
    # briefly exceed 100 during burst incidents; we clamp to 100.
    _NORMALISATION_FACTOR = 200.0

    def __init__(self, store_id: str, config: Dict) -> None:
        self._store_id = store_id

        cfg = dict(_DEFAULTS)
        cfg.update({k: v for k, v in config.items() if k in _DEFAULTS})

        self._window: float = float(cfg["window_seconds"])
        self._weights: Dict[str, float] = dict(_DEFAULT_WEIGHTS)
        self._weights.update(cfg.get("weights", {}))

        # Ring buffer of event records within the rolling window.
        self._events: Deque[_EventRecord] = deque()

        # History ring buffer of computed RiskScore snapshots.
        self._history: Deque[RiskScore] = deque(maxlen=1000)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_event_type(self, event: Any) -> Optional[str]:
        """Map an event object to its canonical event-type key."""
        class_name = type(event).__name__
        return _EVENT_TYPE_MAP.get(class_name)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()

    def _compute_score_and_counts(
        self,
    ) -> Tuple[float, Dict[str, int]]:
        counts: Dict[str, int] = defaultdict(int)
        weighted_sum = 0.0
        for rec in self._events:
            counts[rec.event_type] += 1
            weighted_sum += rec.weight

        raw_score = min(100.0, weighted_sum / self._NORMALISATION_FACTOR * 100.0)
        return round(raw_score, 2), dict(counts)

    @staticmethod
    def _severity(score: float) -> str:
        if score >= 70.0:
            return "HIGH"
        if score >= 30.0:
            return "MEDIUM"
        return "LOW"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_event(self, event: Any) -> None:
        """
        Record an event from any Vantag analyser module.

        The event's class name is used to look up the appropriate weight.
        Unknown event types are logged and ignored.

        Parameters
        ----------
        event:
            Any event dataclass instance, e.g. :class:`SweepingEvent`,
            :class:`DwellEvent`, etc.  May also accept a plain dict with
            an ``'event_type'`` key.
        """
        now = time.monotonic()

        # Support plain dict events as well.
        if isinstance(event, dict):
            event_type = event.get("event_type")
        else:
            event_type = self._resolve_event_type(event)

        if event_type is None:
            logger.debug(
                "RiskScorer.ingest_event: unknown event type '%s' — ignored.",
                type(event).__name__,
            )
            return

        weight = self._weights.get(event_type, 5.0)
        self._events.append(
            _EventRecord(event_type=event_type, weight=weight, timestamp=now)
        )
        self._prune(now)
        logger.debug(
            "RiskScorer: ingested '%s' (weight=%.1f). Window events: %d.",
            event_type,
            weight,
            len(self._events),
        )

    def get_score(self) -> RiskScore:
        """
        Compute and return the current risk score.

        Also appends the snapshot to the internal history buffer.

        Returns
        -------
        :class:`RiskScore`
        """
        now = time.monotonic()
        self._prune(now)
        score, counts = self._compute_score_and_counts()
        severity = self._severity(score)
        rs = RiskScore(
            store_id=self._store_id,
            score=score,
            severity=severity,
            timestamp=datetime.now(tz=timezone.utc),
            event_counts=counts,
        )
        self._history.append(rs)
        return rs

    def get_history(self, n: int = 100) -> List[RiskScore]:
        """
        Return the last *n* computed :class:`RiskScore` snapshots, oldest first.

        Parameters
        ----------
        n:
            Maximum number of snapshots to return.
        """
        history_list = list(self._history)
        return history_list[-n:]
