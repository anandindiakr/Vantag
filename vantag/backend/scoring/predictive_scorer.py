"""
predictive_scorer.py
====================
Predictive theft-probability scorer for the Vantag platform.

Uses LightGBM as the primary ML backend.  When ``lightgbm`` is not installed
a weighted rule-based heuristic is used instead.

Feature vector (14 features):
    0  – hour_of_day          (0–23)
    1  – day_of_week          (0=Monday … 6=Sunday)
    2  – count_sweeping        events in recent window
    3  – count_dwell
    4  – count_empty_shelf
    5  – count_watchlist_match
    6  – count_queue
    7  – count_accident
    8  – count_staff_alert
    9  – count_tamper
    10 – count_pos_anomaly
    11 – customer_count        (current head-count estimate)
    12 – avg_dwell_time        (seconds)
    13 – zone_count_with_activity

Model persistence: a trained LightGBM booster is saved to / loaded from
``model_path`` as a plain ``.txt`` file (LightGBM native format).
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LightGBM – optional.
# ---------------------------------------------------------------------------

try:
    import lightgbm as lgb  # type: ignore[import]
    _LGB_OK = True
except ImportError:
    lgb = None  # type: ignore[assignment]
    _LGB_OK = False
    logger.warning(
        "predictive_scorer: 'lightgbm' is not installed. "
        "Using heuristic fallback. Install with: pip install lightgbm"
    )

# ---------------------------------------------------------------------------
# Feature indices (symbolic constants for readability)
# ---------------------------------------------------------------------------

_F_HOUR = 0
_F_DOW = 1
_F_SWEEPING = 2
_F_DWELL = 3
_F_EMPTY_SHELF = 4
_F_WATCHLIST = 5
_F_QUEUE = 6
_F_ACCIDENT = 7
_F_STAFF_ALERT = 8
_F_TAMPER = 9
_F_POS_ANOMALY = 10
_F_CUSTOMER_COUNT = 11
_F_AVG_DWELL = 12
_F_ZONE_ACTIVITY = 13

_FEATURE_DIM = 14

# Heuristic weights for each event-count feature (index → weight).
_HEURISTIC_WEIGHTS: Dict[int, float] = {
    _F_SWEEPING: 0.30,
    _F_DWELL: 0.12,
    _F_EMPTY_SHELF: 0.05,
    _F_WATCHLIST: 0.40,
    _F_QUEUE: 0.08,
    _F_ACCIDENT: 0.20,
    _F_STAFF_ALERT: 0.15,
    _F_TAMPER: 0.45,
    _F_POS_ANOMALY: 0.25,
}


# ---------------------------------------------------------------------------
# PredictiveScorer
# ---------------------------------------------------------------------------

class PredictiveScorer:
    """
    Predicts theft probability from a feature vector.

    Parameters
    ----------
    model_path:
        Filesystem path where the LightGBM model is saved / loaded.  Must
        end in ``.txt`` (LightGBM native format).
    """

    def __init__(self, model_path: str) -> None:
        self._model_path = model_path
        self._model: Any = None  # lgb.Booster or None
        self._using_lgb = False

        if _LGB_OK:
            self._try_load_model()

    # ------------------------------------------------------------------
    # Model persistence
    # ------------------------------------------------------------------

    def _try_load_model(self) -> None:
        if not os.path.isfile(self._model_path):
            logger.info(
                "predictive_scorer: no saved model at '%s'. "
                "Using heuristic until trained.",
                self._model_path,
            )
            return
        try:
            self._model = lgb.Booster(model_file=self._model_path)  # type: ignore[union-attr]
            self._using_lgb = True
            logger.info(
                "predictive_scorer: LightGBM model loaded from '%s'.",
                self._model_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "predictive_scorer: failed to load model (%s). Using heuristic.",
                exc,
            )

    def _save_model(self) -> None:
        if self._model is None:
            return
        try:
            os.makedirs(os.path.dirname(self._model_path) or ".", exist_ok=True)
            self._model.save_model(self._model_path)  # type: ignore[union-attr]
            logger.info(
                "predictive_scorer: model saved to '%s'.", self._model_path
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "predictive_scorer: failed to save model: %s", exc
            )

    # ------------------------------------------------------------------
    # Heuristic fallback
    # ------------------------------------------------------------------

    def _heuristic_score(self, features: List[float]) -> float:
        """
        Compute a rule-based probability score in [0, 1].

        The score is a sigmoid-normalised weighted sum of event counts plus
        a small bonus for late-night hours (potential after-hours risk).
        """
        weighted_sum = 0.0
        for idx, weight in _HEURISTIC_WEIGHTS.items():
            if idx < len(features):
                weighted_sum += min(features[idx], 10.0) * weight  # cap counts at 10

        # Late-night bonus (hours 22–5).
        hour = features[_F_HOUR] if len(features) > _F_HOUR else 12
        if hour >= 22 or hour <= 5:
            weighted_sum += 0.3

        # Sigmoid normalisation to [0, 1].
        prob = 1.0 / (1.0 + math.exp(-weighted_sum + 2.0))
        return round(float(prob), 4)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, feature_vector: List[float]) -> float:
        """
        Return the theft probability in [0.0, 1.0] for *feature_vector*.

        Parameters
        ----------
        feature_vector:
            14-element float list as built by :meth:`build_features`.

        Returns
        -------
        Probability float in [0.0, 1.0].
        """
        if len(feature_vector) != _FEATURE_DIM:
            logger.warning(
                "predictive_scorer.predict: expected %d features, got %d. "
                "Padding / truncating.",
                _FEATURE_DIM,
                len(feature_vector),
            )
            fv = list(feature_vector)
            while len(fv) < _FEATURE_DIM:
                fv.append(0.0)
            feature_vector = fv[:_FEATURE_DIM]

        if self._using_lgb and self._model is not None:
            try:
                import numpy as np  # local import to keep top-level optional
                arr = np.array([feature_vector], dtype=np.float32)
                raw = self._model.predict(arr)  # type: ignore[union-attr]
                prob = float(raw[0])
                # LightGBM binary classifier outputs probability directly.
                return round(min(max(prob, 0.0), 1.0), 4)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "predictive_scorer.predict: LightGBM inference failed (%s). "
                    "Falling back to heuristic.",
                    exc,
                )

        return self._heuristic_score(feature_vector)

    def build_features(
        self,
        recent_events: List[Any],
        current_time: datetime,
        customer_count: int = 0,
        avg_dwell_time: float = 0.0,
        zone_count_with_activity: int = 0,
    ) -> List[float]:
        """
        Construct the 14-element feature vector from a list of recent event
        objects and contextual metadata.

        Parameters
        ----------
        recent_events:
            List of event dataclass instances from the last scoring window.
        current_time:
            Datetime for which the prediction is being made (used for
            temporal features).
        customer_count:
            Approximate number of customers currently in the store.
        avg_dwell_time:
            Average dwell time (seconds) across all tracked persons.
        zone_count_with_activity:
            Number of zones that have had detections in the current window.

        Returns
        -------
        List of 14 floats.
        """
        # Temporal features.
        hour = float(current_time.hour)
        dow = float(current_time.weekday())

        # Event count features.
        counts: Dict[str, float] = {
            "sweeping": 0.0,
            "dwell": 0.0,
            "empty_shelf": 0.0,
            "watchlist_match": 0.0,
            "queue": 0.0,
            "accident": 0.0,
            "staff_alert": 0.0,
            "tamper": 0.0,
            "pos_anomaly": 0.0,
        }

        _name_to_key: Dict[str, str] = {
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

        for event in recent_events:
            if isinstance(event, dict):
                key = event.get("event_type")
            else:
                key = _name_to_key.get(type(event).__name__)
            if key and key in counts:
                counts[key] += 1.0

        return [
            hour,
            dow,
            counts["sweeping"],
            counts["dwell"],
            counts["empty_shelf"],
            counts["watchlist_match"],
            counts["queue"],
            counts["accident"],
            counts["staff_alert"],
            counts["tamper"],
            counts["pos_anomaly"],
            float(customer_count),
            float(avg_dwell_time),
            float(zone_count_with_activity),
        ]

    def train(
        self,
        X: List[List[float]],
        y: List[float],
    ) -> None:
        """
        Train / retrain the LightGBM model and persist it to ``model_path``.

        Parameters
        ----------
        X:
            List of 14-element feature vectors.
        y:
            Binary labels (1.0 = theft incident, 0.0 = normal).

        Raises
        ------
        RuntimeError
            If LightGBM is not installed.
        """
        if not _LGB_OK:
            raise RuntimeError(
                "predictive_scorer.train: 'lightgbm' is not installed. "
                "Install with: pip install lightgbm"
            )

        import numpy as np  # noqa: PLC0415

        X_arr = np.array(X, dtype=np.float32)
        y_arr = np.array(y, dtype=np.float32)

        if len(X_arr) == 0 or len(y_arr) == 0:
            raise ValueError("predictive_scorer.train: empty training data.")

        train_data = lgb.Dataset(X_arr, label=y_arr)  # type: ignore[union-attr]

        params: Dict = {
            "objective": "binary",
            "metric": "binary_logloss",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "n_estimators": 200,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "verbose": -1,
        }

        logger.info(
            "predictive_scorer.train: training on %d samples.", len(X_arr)
        )

        callbacks = [lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)]  # type: ignore[union-attr]

        try:
            self._model = lgb.train(  # type: ignore[union-attr]
                params,
                train_data,
                num_boost_round=200,
                valid_sets=[train_data],
                callbacks=callbacks,
            )
            self._using_lgb = True
            self._save_model()
            logger.info("predictive_scorer.train: training complete.")
        except Exception as exc:  # noqa: BLE001
            logger.error("predictive_scorer.train: training failed: %s", exc)
            raise
