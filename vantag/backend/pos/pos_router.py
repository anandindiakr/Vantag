"""
backend/pos/pos_router.py
===========================
FastAPI router for POS integration endpoints.

Endpoints
---------
POST /api/pos/transaction          — ingest a single POS transaction
POST /api/pos/transactions/bulk    — bulk-import transactions from a CSV file
GET  /api/pos/anomalies?limit=50   — retrieve recent anomaly events
GET  /api/pos/stats                — aggregated statistics

The router maintains a module-level POSIntegration singleton so that
all in-process state (transaction buffer, anomaly buffer, cashier windows)
is shared across requests.  For multi-process deployments these buffers
should be moved to a shared data store (Redis, PostgreSQL, etc.).
"""

from __future__ import annotations

import logging
import tempfile
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from .pos_integration import POSIntegration, POSAnomalyEvent

logger = logging.getLogger(__name__)

# ─── Module-level singleton ───────────────────────────────────────────────────

_pos: POSIntegration = POSIntegration()
_webhook_engine: Any = None  # injected at startup via set_webhook_engine()


def set_webhook_engine(engine: Any) -> None:
    """Inject the WebhookEngine so POS anomalies can trigger outbound webhooks."""
    global _webhook_engine  # noqa: PLW0603
    _webhook_engine = engine

router = APIRouter(prefix="/api/pos", tags=["POS Integration"])


# ─── Pydantic models ──────────────────────────────────────────────────────────

class POSItem(BaseModel):
    sku: str = Field(..., description="Product SKU or barcode.")
    qty: int = Field(1, ge=1, description="Quantity of this item.")
    price: float = Field(0.0, ge=0.0, description="Unit price.")


class POSTransactionRequest(BaseModel):
    """Inbound POS transaction payload."""

    transaction_id: str = Field(..., description="Unique POS transaction identifier.")
    cashier_id: str = Field(..., description="Cashier employee identifier.")
    camera_id: str = Field(..., description="Camera monitoring the checkout lane.")
    store_id: str = Field("", description="Store identifier (optional).")
    timestamp: Optional[str] = Field(
        None, description="ISO-8601 transaction timestamp. Defaults to now."
    )
    items: List[POSItem] = Field(..., min_length=0, description="Scanned line items.")
    total_amount: float = Field(..., ge=0.0, description="Transaction total in local currency.")
    basket_size_camera_estimate: float = Field(
        ...,
        ge=0.0,
        description=(
            "Vision-derived estimate of total items physically passed over the scanner. "
            "Used to detect sweethearting."
        ),
    )

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "cashier_id": self.cashier_id,
            "camera_id": self.camera_id,
            "store_id": self.store_id,
            "timestamp": self.timestamp,
            "items": [item.model_dump() for item in self.items],
            "total_amount": self.total_amount,
            "basket_size_camera_estimate": self.basket_size_camera_estimate,
        }


class POSAnomalyResponse(BaseModel):
    """Anomaly event response payload."""

    cashier_id: str
    camera_id: str
    transaction_id: str
    risk_score: float
    anomaly_type: str
    timestamp: str
    store_id: str
    pos_item_count: int
    camera_estimate: float
    ratio: float
    notes: str

    @classmethod
    def from_event(cls, event: POSAnomalyEvent) -> "POSAnomalyResponse":
        return cls(
            cashier_id=event.cashier_id,
            camera_id=event.camera_id,
            transaction_id=event.transaction_id,
            risk_score=event.risk_score,
            anomaly_type=event.anomaly_type,
            timestamp=event.timestamp.isoformat(),
            store_id=event.store_id,
            pos_item_count=event.pos_item_count,
            camera_estimate=event.camera_estimate,
            ratio=event.ratio,
            notes=event.notes,
        )


class TransactionIngestResponse(BaseModel):
    """Response from a single transaction ingest."""

    transaction_id: str
    anomaly_detected: bool
    anomaly: Optional[POSAnomalyResponse] = None
    message: str


class BulkIngestResponse(BaseModel):
    """Response from a CSV bulk ingest."""

    total_rows: int
    anomaly_count: int
    anomaly_rate: float
    message: str


class POSStatsResponse(BaseModel):
    """Aggregated POS statistics."""

    total_transactions: int
    total_anomalies: int
    anomaly_rate: float
    top_flagged_cashiers: List[Dict[str, Any]]
    anomalies_by_type: Dict[str, int]


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/transaction",
    response_model=TransactionIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest a single POS transaction",
    description=(
        "Process a POS transaction and run sweethearting detection. "
        "Returns the anomaly event if one was detected."
    ),
)
async def ingest_transaction(
    body: POSTransactionRequest,
) -> TransactionIngestResponse:
    """Ingest a single transaction and detect sweethearting."""
    raw = body.to_dict()
    anomaly = _pos.ingest_transaction(raw)

    if anomaly is not None:
        return TransactionIngestResponse(
            transaction_id=body.transaction_id,
            anomaly_detected=True,
            anomaly=POSAnomalyResponse.from_event(anomaly),
            message=f"Anomaly detected: {anomaly.anomaly_type}",
        )

    return TransactionIngestResponse(
        transaction_id=body.transaction_id,
        anomaly_detected=False,
        anomaly=None,
        message="Transaction processed normally.",
    )


@router.post(
    "/transactions/bulk",
    response_model=BulkIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk-import POS transactions from CSV",
    description=(
        "Upload a CSV file of POS transactions for batch processing. "
        "Expected columns: transaction_id, cashier_id, camera_id, store_id, "
        "timestamp, items (count), total_amount, basket_size_camera_estimate."
    ),
)
async def bulk_ingest_transactions(
    file: UploadFile = File(..., description="CSV transaction log file."),
) -> BulkIngestResponse:
    """Accept a CSV upload and process all rows."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV (.csv extension required).",
        )

    # Write to a temporary file so POSIntegration can read it as a path
    try:
        contents = await file.read()
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", delete=False
        ) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to read uploaded file: {exc}",
        ) from exc

    try:
        total_rows, anomaly_count = _pos.ingest_from_csv(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    rate = anomaly_count / total_rows if total_rows > 0 else 0.0

    return BulkIngestResponse(
        total_rows=total_rows,
        anomaly_count=anomaly_count,
        anomaly_rate=round(rate, 4),
        message=(
            f"Processed {total_rows} transactions; "
            f"detected {anomaly_count} anomalie(s)."
        ),
    )


@router.get(
    "/anomalies",
    response_model=List[POSAnomalyResponse],
    summary="Retrieve recent POS anomaly events",
    description="Returns the most recent POS anomaly events, newest first.",
)
async def get_anomalies(
    limit: int = Query(50, ge=1, le=500, description="Maximum number of anomalies to return."),
) -> List[POSAnomalyResponse]:
    """Return recent anomaly events."""
    events = _pos.get_anomalies(limit=limit)
    return [POSAnomalyResponse.from_event(e) for e in events]


@router.get(
    "/stats",
    response_model=POSStatsResponse,
    summary="POS aggregated statistics",
    description=(
        "Returns aggregate statistics: total transaction count, anomaly rate, "
        "top flagged cashiers, and anomaly type breakdown."
    ),
)
async def get_stats() -> POSStatsResponse:
    """Return aggregated POS statistics."""
    stats = _pos.get_stats()
    return POSStatsResponse(**stats)
