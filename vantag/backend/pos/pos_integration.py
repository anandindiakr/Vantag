"""
backend/pos/pos_integration.py
================================
POS (Point-of-Sale) integration and sweethearting detection module.

Sweethearting: a cashier intentionally failing to scan items while
appearing to do so — detected here by comparing the POS basket item
count against the camera's computer-vision estimate of basket size.

Transaction schema (dict)
--------------------------
{
    "transaction_id":           str,
    "cashier_id":               str,
    "camera_id":                str,
    "store_id":                 str,                # optional
    "timestamp":                str | datetime,     # ISO-8601 or datetime
    "items":                    list[dict],         # each item: {sku, qty, price}
    "total_amount":             float,
    "basket_size_camera_estimate": int | float,     # vision estimate of items passed
}

Anomaly escalation
------------------
If a cashier accumulates ≥ 3 anomalies within any rolling 60-minute
window, the anomaly is escalated (risk_score boosted to ≥ 80).

REST integration
----------------
Endpoints are defined in pos_router.py; this module provides the
business-logic class consumed by those routes.
"""

from __future__ import annotations

import csv
import io
import logging
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Ratio of (vision estimate / POS item count) below which we flag
_SWEETHEATING_RATIO_THRESHOLD: float = 0.5

# Escalation: anomaly count within this window triggers higher risk
_ESCALATION_WINDOW_MINUTES: int = 60
_ESCALATION_THRESHOLD: int = 3

# Base risk scores
_RISK_SCORE_NORMAL: float = 30.0
_RISK_SCORE_SWEETHEATING: float = 60.0
_RISK_SCORE_ESCALATED: float = 85.0

# Maximum stored transactions / anomaly events
_MAX_TRANSACTIONS: int = 10_000
_MAX_ANOMALIES: int = 1_000


# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class POSAnomalyEvent:
    """A detected POS anomaly (sweethearting or escalated pattern)."""

    cashier_id: str
    camera_id: str
    transaction_id: str
    risk_score: float
    anomaly_type: str           # "sweethearting" | "escalated_pattern"
    timestamp: datetime
    store_id: str = ""
    pos_item_count: int = 0
    camera_estimate: float = 0.0
    ratio: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "cashier_id": self.cashier_id,
            "camera_id": self.camera_id,
            "transaction_id": self.transaction_id,
            "risk_score": self.risk_score,
            "anomaly_type": self.anomaly_type,
            "timestamp": self.timestamp.isoformat(),
            "store_id": self.store_id,
            "pos_item_count": self.pos_item_count,
            "camera_estimate": self.camera_estimate,
            "ratio": self.ratio,
            "notes": self.notes,
        }


@dataclass
class POSTransaction:
    """Parsed and validated POS transaction record."""

    transaction_id: str
    cashier_id: str
    camera_id: str
    store_id: str
    timestamp: datetime
    items: List[dict]
    total_amount: float
    basket_size_camera_estimate: float
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def pos_item_count(self) -> int:
        """Sum of quantities across all line items."""
        total = 0
        for item in self.items:
            qty = item.get("qty", item.get("quantity", 1))
            try:
                total += int(qty)
            except (TypeError, ValueError):
                total += 1
        return max(total, len(self.items))


# ─── POSIntegration ──────────────────────────────────────────────────────────

class POSIntegration:
    """
    Main POS integration class.

    Thread-safe via an internal lock.  All public methods may be called
    from concurrent FastAPI request handlers.

    Parameters
    ----------
    sweetheating_ratio_threshold:
        (vision_estimate / pos_count) ratio below which a transaction is
        flagged as sweethearting (default 0.5).
    escalation_window_minutes:
        Rolling window used to count per-cashier anomalies (default 60).
    escalation_threshold:
        Number of anomalies within the window that triggers escalation
        (default 3).
    """

    def __init__(
        self,
        sweetheating_ratio_threshold: float = _SWEETHEATING_RATIO_THRESHOLD,
        escalation_window_minutes: int = _ESCALATION_WINDOW_MINUTES,
        escalation_threshold: int = _ESCALATION_THRESHOLD,
    ) -> None:
        self._ratio_threshold = sweetheating_ratio_threshold
        self._esc_window = timedelta(minutes=escalation_window_minutes)
        self._esc_threshold = escalation_threshold

        self._lock = threading.Lock()

        # Ring buffer of all ingested transactions
        self._transactions: Deque[POSTransaction] = deque(maxlen=_MAX_TRANSACTIONS)

        # Ring buffer of detected anomalies
        self._anomalies: Deque[POSAnomalyEvent] = deque(maxlen=_MAX_ANOMALIES)

        # Per-cashier anomaly timestamps for escalation detection
        # cashier_id → deque of anomaly datetimes
        self._cashier_anomaly_times: Dict[str, Deque[datetime]] = defaultdict(
            lambda: deque(maxlen=500)
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_transaction(self, raw: dict) -> POSTransaction:
        """
        Parse and validate a raw transaction dict into a POSTransaction.

        Raises
        ------
        ValueError
            If required fields are missing or malformed.
        """
        required = [
            "transaction_id",
            "cashier_id",
            "camera_id",
            "items",
            "total_amount",
            "basket_size_camera_estimate",
        ]
        for field_name in required:
            if field_name not in raw:
                raise ValueError(
                    f"POS transaction missing required field: '{field_name}'"
                )

        # Parse timestamp
        ts_raw = raw.get("timestamp", datetime.now(tz=timezone.utc).isoformat())
        if isinstance(ts_raw, datetime):
            ts = ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
        else:
            try:
                ts = datetime.fromisoformat(str(ts_raw))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                ts = datetime.now(tz=timezone.utc)

        return POSTransaction(
            transaction_id=str(raw["transaction_id"]),
            cashier_id=str(raw["cashier_id"]),
            camera_id=str(raw["camera_id"]),
            store_id=str(raw.get("store_id", "")),
            timestamp=ts,
            items=list(raw["items"]) if isinstance(raw["items"], list) else [],
            total_amount=float(raw["total_amount"]),
            basket_size_camera_estimate=float(raw["basket_size_camera_estimate"]),
            raw=raw,
        )

    def _cashier_anomaly_count_in_window(self, cashier_id: str, now: datetime) -> int:
        """Count anomalies for a cashier within the rolling escalation window."""
        cutoff = now - self._esc_window
        times = self._cashier_anomaly_times[cashier_id]
        # Prune old entries
        while times and times[0] < cutoff:
            times.popleft()
        return len(times)

    def _record_cashier_anomaly(self, cashier_id: str, ts: datetime) -> None:
        self._cashier_anomaly_times[cashier_id].append(ts)

    # ── Public API ────────────────────────────────────────────────────────────

    def ingest_transaction(self, transaction: dict) -> Optional[POSAnomalyEvent]:
        """
        Process a single POS transaction dict.

        Parses the transaction, appends it to the internal buffer, runs
        sweethearting detection, and returns a POSAnomalyEvent if detected.

        Parameters
        ----------
        transaction:
            Raw transaction dict (see module docstring for schema).

        Returns
        -------
        POSAnomalyEvent if anomalous, else None.
        """
        try:
            tx = self._parse_transaction(transaction)
        except ValueError as exc:
            logger.warning("POSIntegration.ingest_transaction: %s", exc)
            return None

        with self._lock:
            self._transactions.append(tx)
            anomaly = self.detect_sweethearting(tx)
            if anomaly is not None:
                self._anomalies.append(anomaly)
                self._record_cashier_anomaly(tx.cashier_id, tx.timestamp)
                logger.warning(
                    "POSAnomalyEvent | type=%s cashier=%s tx=%s risk=%.1f",
                    anomaly.anomaly_type,
                    anomaly.cashier_id,
                    anomaly.transaction_id,
                    anomaly.risk_score,
                )
            return anomaly

    def detect_sweethearting(
        self, transaction: "POSTransaction | dict"
    ) -> Optional[POSAnomalyEvent]:
        """
        Run sweethearting detection on a single transaction.

        Can accept either a POSTransaction dataclass or a raw dict (which
        will be parsed first — note: does NOT lock or record to buffers
        when called directly with a dict).

        Algorithm
        ---------
        1. Compute ratio = basket_size_camera_estimate / pos_item_count.
        2. If ratio < sweetheating_ratio_threshold → flag sweethearting.
        3. If the cashier has ≥ escalation_threshold anomalies in the
           rolling window → escalate risk score and anomaly_type.

        Parameters
        ----------
        transaction:
            A POSTransaction (preferred) or raw dict.

        Returns
        -------
        POSAnomalyEvent if anomalous, else None.
        """
        if isinstance(transaction, dict):
            try:
                tx: POSTransaction = self._parse_transaction(transaction)
            except ValueError:
                return None
        else:
            tx = transaction

        pos_count = tx.pos_item_count
        vision_estimate = tx.basket_size_camera_estimate
        now = tx.timestamp

        # Edge case: no items scanned — nothing to compare
        if pos_count == 0:
            return None

        # Edge case: camera estimate is zero but items were scanned — not
        # necessarily sweethearting (camera may have missed occlusions)
        if vision_estimate <= 0:
            return None

        # ratio = camera_basket_estimate / pos_items_scanned
        # A low ratio means camera sees far fewer items than were rung up → anomaly
        ratio = vision_estimate / pos_count

        if ratio >= self._ratio_threshold:
            return None  # Normal transaction

        # ── Anomaly detected ──────────────────────────────────────────────────

        # Check for escalation (NOTE: when called from detect_sweethearting
        # directly with a dict, _cashier_anomaly_count_in_window uses the
        # already-recorded times; no double-recording occurs here)
        anomaly_count = self._cashier_anomaly_count_in_window(tx.cashier_id, now)
        if anomaly_count >= self._esc_threshold:
            anomaly_type = "escalated_pattern"
            risk_score = _RISK_SCORE_ESCALATED
            notes = (
                f"Cashier has {anomaly_count} anomalies in the last "
                f"{int(self._esc_window.total_seconds() // 60)} minutes."
            )
        else:
            anomaly_type = "sweethearting"
            risk_score = _RISK_SCORE_SWEETHEATING
            notes = (
                f"Vision estimate ({vision_estimate:.1f}) vs POS count ({pos_count}) "
                f"ratio={ratio:.2f} < threshold={self._ratio_threshold}"
            )

        return POSAnomalyEvent(
            cashier_id=tx.cashier_id,
            camera_id=tx.camera_id,
            transaction_id=tx.transaction_id,
            risk_score=risk_score,
            anomaly_type=anomaly_type,
            timestamp=now,
            store_id=tx.store_id,
            pos_item_count=pos_count,
            camera_estimate=vision_estimate,
            ratio=round(ratio, 4),
            notes=notes,
        )

    def ingest_from_csv(self, filepath: str) -> Tuple[int, int]:
        """
        Bulk-import transactions from a CSV file.

        Expected CSV columns (case-insensitive, with aliases):
        transaction_id, cashier_id, camera_id, store_id, timestamp,
        items (serialised as item count integer), total_amount,
        basket_size_camera_estimate

        For CSV ingestion, 'items' is interpreted as a single integer
        representing the item count (not a full item list), since CSV
        cannot represent nested structures.  Each row becomes a synthetic
        transaction with a flat list of {"sku": "item_N", "qty": 1} dicts.

        Parameters
        ----------
        filepath:
            Absolute or relative path to the CSV file.

        Returns
        -------
        (total_rows, anomaly_count): counts of processed rows and anomalies found.
        """
        total = 0
        anomalies_found = 0

        try:
            with open(filepath, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    row_lower = {k.strip().lower(): v.strip() for k, v in row.items()}

                    # Parse item count — CSV stores as integer
                    try:
                        item_count = int(
                            row_lower.get("items", row_lower.get("item_count", "1"))
                        )
                    except ValueError:
                        item_count = 1

                    synthetic_items = [
                        {"sku": f"ITEM_{i + 1}", "qty": 1}
                        for i in range(max(item_count, 1))
                    ]

                    try:
                        total_amount = float(
                            row_lower.get("total_amount", row_lower.get("total", "0"))
                        )
                    except ValueError:
                        total_amount = 0.0

                    try:
                        cam_estimate = float(
                            row_lower.get(
                                "basket_size_camera_estimate",
                                row_lower.get("camera_estimate", str(item_count)),
                            )
                        )
                    except ValueError:
                        cam_estimate = float(item_count)

                    raw = {
                        "transaction_id": row_lower.get(
                            "transaction_id", row_lower.get("txn_id", f"csv-{total}")
                        ),
                        "cashier_id": row_lower.get(
                            "cashier_id", row_lower.get("cashier", "unknown")
                        ),
                        "camera_id": row_lower.get(
                            "camera_id", row_lower.get("camera", "csv-cam")
                        ),
                        "store_id": row_lower.get("store_id", row_lower.get("store", "")),
                        "timestamp": row_lower.get("timestamp", ""),
                        "items": synthetic_items,
                        "total_amount": total_amount,
                        "basket_size_camera_estimate": cam_estimate,
                    }

                    anomaly = self.ingest_transaction(raw)
                    if anomaly is not None:
                        anomalies_found += 1
                    total += 1

        except FileNotFoundError:
            logger.error("POSIntegration.ingest_from_csv: file not found: %s", filepath)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "POSIntegration.ingest_from_csv: unexpected error: %s", exc
            )

        logger.info(
            "CSV ingestion complete | file=%s rows=%d anomalies=%d",
            filepath,
            total,
            anomalies_found,
        )
        return total, anomalies_found

    # ── Query methods ─────────────────────────────────────────────────────────

    def get_anomalies(self, limit: int = 50) -> List[POSAnomalyEvent]:
        """Return the most recent anomaly events, newest first."""
        with self._lock:
            all_anomalies = list(self._anomalies)
        return list(reversed(all_anomalies))[:limit]

    def get_stats(self) -> dict:
        """
        Return aggregated statistics.

        Returns
        -------
        dict with keys:
          - total_transactions: int
          - total_anomalies: int
          - anomaly_rate: float  (0.0 – 1.0)
          - top_flagged_cashiers: list[{cashier_id, count}] (top 10)
          - anomalies_by_type: dict[str, int]
        """
        with self._lock:
            total_tx = len(self._transactions)
            total_an = len(self._anomalies)
            anomalies_snap = list(self._anomalies)

        rate = total_an / total_tx if total_tx > 0 else 0.0

        cashier_counts: Dict[str, int] = defaultdict(int)
        type_counts: Dict[str, int] = defaultdict(int)
        for a in anomalies_snap:
            cashier_counts[a.cashier_id] += 1
            type_counts[a.anomaly_type] += 1

        top_cashiers = sorted(
            [{"cashier_id": k, "count": v} for k, v in cashier_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        return {
            "total_transactions": total_tx,
            "total_anomalies": total_an,
            "anomaly_rate": round(rate, 4),
            "top_flagged_cashiers": top_cashiers,
            "anomalies_by_type": dict(type_counts),
        }
