"""
backend/api/stores_router.py
=============================
REST API for store management and risk intelligence.

Endpoints
---------
GET  /api/stores                                     – list all stores
GET  /api/stores/{store_id}                          – single store detail
GET  /api/stores/{store_id}/risk                     – current risk score snapshot
GET  /api/stores/{store_id}/heatmap?window=hourly    – heatmap grid data
GET  /api/stores/{store_id}/incidents                – paginated incident log
GET  /api/queue-status                               – live queue depth per lane

All data is served from the in-memory state maintained by ``VantagePipeline``.
The pipeline is injected at application startup via the ``set_pipeline`` helper.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from .models import (
    HeatmapCell,
    HeatmapResponse,
    IncidentListResponse,
    IncidentResponse,
    LaneQueueStatus,
    PaginationMeta,
    QueueStatusResponse,
    RiskScoreResponse,
    SeverityLevel,
    StoreResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stores", tags=["Stores"])
queue_router = APIRouter(tags=["Queues"])

# ---------------------------------------------------------------------------
# Pipeline reference (injected at startup)
# ---------------------------------------------------------------------------

_pipeline = None  # type: ignore[assignment]


def set_pipeline(pipeline: object) -> None:  # noqa: ANN001
    """Inject the ``VantagePipeline`` singleton into this router."""
    global _pipeline  # noqa: PLW0603
    _pipeline = pipeline


def _get_pipeline():  # noqa: ANN202
    if _pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inference pipeline is not yet initialised.",
        )
    return _pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_to_severity(score: float) -> SeverityLevel:
    if score >= 80:
        return SeverityLevel.CRITICAL
    if score >= 60:
        return SeverityLevel.HIGH
    if score >= 35:
        return SeverityLevel.MEDIUM
    return SeverityLevel.LOW


def _get_store_ids(pipeline) -> List[str]:  # noqa: ANN001
    """Return distinct store IDs derived from the camera registry."""
    try:
        cameras = pipeline.registry.all_cameras()
        return list({
            cam.location.split("–")[0].strip().replace(" ", "_").lower()
            for cam in cameras
        })
    except Exception:  # noqa: BLE001
        return list(pipeline.risk_scores.keys())


# ---------------------------------------------------------------------------
# GET /api/stores
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=List[StoreResponse],
    summary="List all stores",
)
async def list_stores() -> List[StoreResponse]:
    """Return a list of all stores with their current risk scores."""
    pipeline = _get_pipeline()

    try:
        cameras = pipeline.registry.all_cameras()
    except Exception:  # noqa: BLE001
        cameras = []

    # Group cameras by store (inferred from location prefix).
    store_camera_map: dict = {}
    for cam in cameras:
        store_id = _camera_store_id(cam)
        store_camera_map.setdefault(store_id, []).append(cam)

    # Also include stores that have risk scores but no loaded cameras.
    for store_id in pipeline.risk_scores:
        store_camera_map.setdefault(store_id, [])

    stores: List[StoreResponse] = []
    for store_id, cams in store_camera_map.items():
        risk_data = pipeline.risk_scores.get(store_id, {})
        score = float(risk_data.get("score", 0.0))
        health_status = pipeline.health_monitor.get_status() if pipeline.health_monitor else {}

        active = sum(
            1 for cam in cams if health_status.get(cam.id, {}).get("healthy", False)
        )
        last_events = pipeline.recent_events.get(store_id, [])
        last_event_at = (last_events[-1].get("timestamp") or last_events[-1].get("occurred_at")) if last_events else None

        stores.append(
            StoreResponse(
                store_id=store_id,
                name=_store_display_name(store_id),
                location=_store_location(cams),
                camera_count=len(cams),
                active_cameras=active,
                risk_score=round(score, 2),
                risk_severity=_score_to_severity(score),
                last_event_at=last_event_at,
            )
        )

    return stores


# ---------------------------------------------------------------------------
# GET /api/stores/{store_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Get store detail",
)
async def get_store(store_id: str) -> StoreResponse:
    """Return detail for a single store."""
    pipeline = _get_pipeline()
    risk_data = pipeline.risk_scores.get(store_id)

    try:
        cameras = [
            cam
            for cam in pipeline.registry.all_cameras()
            if _camera_store_id(cam) == store_id
        ]
    except Exception:  # noqa: BLE001
        cameras = []

    if risk_data is None and not cameras:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{store_id}' not found.",
        )

    score = float((risk_data or {}).get("score", 0.0))
    health_status = pipeline.health_monitor.get_status() if pipeline.health_monitor else {}
    active = sum(
        1 for cam in cameras if health_status.get(cam.id, {}).get("healthy", False)
    )
    last_events = pipeline.recent_events.get(store_id, [])
    last_event_at = last_events[-1].get("timestamp") if last_events else None

    return StoreResponse(
        store_id=store_id,
        name=_store_display_name(store_id),
        location=_store_location(cameras),
        camera_count=len(cameras),
        active_cameras=active,
        risk_score=round(score, 2),
        risk_severity=_score_to_severity(score),
        last_event_at=last_event_at,
    )


# ---------------------------------------------------------------------------
# GET /api/stores/{store_id}/risk
# ---------------------------------------------------------------------------


@router.get(
    "/{store_id}/risk",
    response_model=RiskScoreResponse,
    summary="Get current risk score snapshot",
)
async def get_risk(store_id: str) -> RiskScoreResponse:
    """Return the current risk score and event counts for a store."""
    pipeline = _get_pipeline()

    # Validate store exists
    all_stores = _get_store_ids(pipeline)
    if store_id not in all_stores:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{store_id}' not found.",
        )

    risk_data = pipeline.risk_scores.get(store_id)

    # No events yet — return a clean zero score (not an error)
    if risk_data is None:
        return RiskScoreResponse(
            store_id=store_id,
            score=0.0,
            severity=SeverityLevel.LOW,
            event_counts={},
            window_seconds=300,
            computed_at=datetime.now(tz=timezone.utc),
        )

    score = float(risk_data.get("score", 0.0))
    event_counts: dict = risk_data.get("event_counts", {})
    window_seconds: int = int(risk_data.get("window_seconds", 60))
    computed_at: datetime = risk_data.get("computed_at", datetime.now(tz=timezone.utc))

    return RiskScoreResponse(
        store_id=store_id,
        score=round(score, 2),
        severity=_score_to_severity(score),
        event_counts=event_counts,
        window_seconds=window_seconds,
        computed_at=computed_at,
    )


# ---------------------------------------------------------------------------
# GET /api/stores/{store_id}/heatmap
# ---------------------------------------------------------------------------


@router.get(
    "/{store_id}/heatmap",
    response_model=HeatmapResponse,
    summary="Get heatmap grid data",
)
async def get_heatmap(
    store_id: str,
    window: str = Query("hourly", description="Aggregation window: 'hourly' or 'daily'."),
) -> HeatmapResponse:
    """Return normalised heatmap grid data for a store."""
    pipeline = _get_pipeline()
    heatmap_store = pipeline.heatmaps.get(store_id, {})
    raw_grid = heatmap_store.get(window, {})

    grid_rows: int = int(raw_grid.get("rows", 10))
    grid_cols: int = int(raw_grid.get("cols", 10))
    raw_cells: dict = raw_grid.get("cells", {})  # key: "row,col" → float value

    # Normalise values to [0, 1].
    values = list(raw_cells.values())
    max_val = max(values, default=1.0) or 1.0

    cells: List[HeatmapCell] = []
    for cell_key, val in raw_cells.items():
        try:
            row_str, col_str = cell_key.split(",")
            cells.append(
                HeatmapCell(
                    row=int(row_str),
                    col=int(col_str),
                    value=round(float(val) / max_val, 4),
                )
            )
        except (ValueError, AttributeError):
            continue

    return HeatmapResponse(
        store_id=store_id,
        window=window,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
        cells=cells,
        generated_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# GET /api/stores/{store_id}/incidents
# ---------------------------------------------------------------------------


@router.get(
    "/{store_id}/incidents",
    response_model=IncidentListResponse,
    summary="Paginated incident log",
)
async def list_incidents(
    store_id: str,
    page: int = Query(1, ge=1, description="Page number (1-based)."),
    limit: int = Query(20, ge=1, le=200, description="Items per page."),
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g. inventory_movement)."),
) -> IncidentListResponse:
    """Return a paginated list of incidents for a store, newest first."""
    pipeline = _get_pipeline()
    all_incidents: List[dict] = list(
        reversed(pipeline.recent_events.get(store_id, []))
    )

    # Server-side event_type filter — applied before pagination so page counts are correct.
    if event_type and event_type != "all":
        et_lower = event_type.lower()
        all_incidents = [
            r for r in all_incidents
            if (r.get("type") or r.get("event_type", "")).lower() == et_lower
        ]

    total = len(all_incidents)
    pages = max(1, math.ceil(total / limit))
    start = (page - 1) * limit
    end = start + limit
    page_items = all_incidents[start:end]

    incidents: List[IncidentResponse] = []
    for raw in page_items:
        try:
            incidents.append(
                IncidentResponse(
                    incident_id=raw.get("incident_id", ""),
                    store_id=store_id,
                    camera_id=raw.get("camera_id", ""),
                    event_type=raw.get("type", raw.get("event_type", "unknown")),
                    severity=SeverityLevel(raw.get("severity", "low")),
                    description=raw.get("description", ""),
                    occurred_at=raw.get("timestamp", raw.get("occurred_at", datetime.now(tz=timezone.utc))),
                    snapshot_url=raw.get("snapshot_url"),
                    acknowledged=raw.get("acknowledged", False),
                    metadata=raw.get("metadata", {}),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse incident record | error=%s", exc)
            continue

    return IncidentListResponse(
        incidents=incidents,
        pagination=PaginationMeta(page=page, limit=limit, total=total, pages=pages),
    )


# ---------------------------------------------------------------------------
# GET /api/queue-status  (separate router, no /stores prefix)
# ---------------------------------------------------------------------------


@queue_router.get(
    "/api/queue-status",
    response_model=QueueStatusResponse,
    summary="Live queue depth per lane across all stores",
)
async def get_queue_status() -> QueueStatusResponse:
    """Return live queue depths for all checkout lanes in all stores."""
    pipeline = _get_pipeline()
    raw_queues: dict = getattr(pipeline, "queue_status", {})

    lanes: List[LaneQueueStatus] = []
    for lane_id, data in raw_queues.items():
        depth = int(data.get("queue_depth", 0))
        avg_wait = float(data.get("avg_wait_seconds", 0.0))

        if depth >= 8:
            q_status = "critical"
        elif depth >= 4:
            q_status = "busy"
        else:
            q_status = "normal"

        lanes.append(
            LaneQueueStatus(
                lane_id=lane_id,
                camera_id=data.get("camera_id", ""),
                store_id=data.get("store_id", ""),
                queue_depth=depth,
                avg_wait_seconds=avg_wait,
                status=q_status,
                updated_at=data.get("updated_at", datetime.now(tz=timezone.utc)),
            )
        )

    return QueueStatusResponse(
        lanes=lanes,
        retrieved_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _camera_store_id(cam) -> str:  # noqa: ANN001
    """Derive a stable store_id string from a camera's location field."""
    prefix = cam.location.split("–")[0].strip()
    return prefix.lower().replace(" ", "_")


def _store_display_name(store_id: str) -> str:
    """Convert a snake_case store_id back to a human-readable name."""
    return store_id.replace("_", " ").title()


def _store_location(cameras: list) -> str:
    """Return a location string from the first camera, or empty string."""
    if cameras:
        loc = cameras[0].location
        parts = loc.split("–")
        return parts[0].strip() if parts else loc
    return "Unknown"
