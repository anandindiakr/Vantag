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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..middleware.tenant_middleware import get_current_user_id
from ..db.database import get_session
from ..db.models.camera import CameraConfig
from ..db.models.site import Site, slugify_site

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
async def list_stores(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> List[StoreResponse]:
    """Return all stores for the current tenant.

    Two sources, merged:

    1. Real ``sites`` rows the tenant created (multi-store). These are
       authoritative — they exist even with zero cameras assigned, so a new
       branch shows up immediately instead of only after a camera is added.
    2. Cameras with no ``site_id``, grouped by the LEGACY location-prefix
       slug. This is what every existing install has today, and keeping it
       means nobody's dashboard changes on deploy.
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        return []

    try:
        rows = (
            await session.execute(
                select(CameraConfig)
                .where(CameraConfig.tenant_id == tenant_id)
                .options(selectinload(CameraConfig.site))
            )
        ).scalars().all()
        sites = (
            await session.execute(
                select(Site).where(Site.tenant_id == tenant_id).order_by(Site.created_at)
            )
        ).scalars().all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load stores from DB | tenant=%s err=%s", tenant_id, exc)
        return []

    # Seed with real sites so a branch with no cameras yet is still visible.
    store_camera_map: dict = {s.slug: [] for s in sites}
    site_by_slug = {s.slug: s for s in sites}

    for cam in rows:
        # effective_store_id is the single source of truth for this mapping —
        # do NOT re-derive the slug here, that duplication is what previously
        # let the same camera land under two different store ids.
        store_camera_map.setdefault(cam.effective_store_id, []).append(cam)


    # Pull live risk/events from the in-memory pipeline when it is available
    # (single-tenant / on-box deployments). Safe no-op for SaaS tenants.
    risk_scores: dict = {}
    recent_events: dict = {}
    if _pipeline is not None:
        risk_scores = getattr(_pipeline, "risk_scores", {}) or {}
        recent_events = getattr(_pipeline, "recent_events", {}) or {}
        for store_id in risk_scores:
            store_camera_map.setdefault(store_id, [])

    stores: List[StoreResponse] = []
    for store_id, cams in store_camera_map.items():
        risk_data = risk_scores.get(store_id, {})
        score = float(risk_data.get("score", 0.0)) if isinstance(risk_data, dict) else 0.0

        active = sum(
            1 for cam in cams if (getattr(cam, "conn_status", "") or "").lower() == "online"
        )
        last_events = recent_events.get(store_id, [])
        last_event_at = (
            (last_events[0].get("timestamp") or last_events[0].get("occurred_at"))
            if last_events else None
        )
        location_label = next(
            (c.location for c in cams if getattr(c, "location", None)),
            store_id.replace("_", " ").title(),
        )

        # A real Site row wins: it carries the name/address the user actually
        # typed, instead of a slug reverse-engineered back into Title Case.
        site = site_by_slug.get(store_id)
        display_name = site.name if site is not None else store_id.replace("_", " ").title()
        if site is not None and (site.address or site.city):
            location_label = ", ".join(p for p in (site.address, site.city) if p)

        stores.append(
            StoreResponse(
                store_id=store_id,
                name=display_name,
                location=location_label,
                camera_count=len(cams),
                active_cameras=active,
                risk_score=round(score, 2),
                risk_severity=_score_to_severity(score),
                last_event_at=last_event_at,
                is_managed=site is not None,
                site_id=site.id if site is not None else None,
            )
        )

    return stores


# ---------------------------------------------------------------------------
# Store (Site) management — real CRUD.
#
# Before this, /api/stores was read-only and a "store" was a slug derived from
# camera_configs.location, so stores could not be created, renamed or deleted
# and renaming a camera silently moved it to another store. These endpoints
# back the store list with a real, tenant-scoped `sites` row.
#
# Route ordering note: these use POST/PATCH/DELETE, so they never shadow the
# existing GET /{store_id} route below.
# ---------------------------------------------------------------------------


class SiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    address: Optional[str] = Field(None, max_length=2000)
    city: Optional[str] = Field(None, max_length=120)
    timezone_name: str = Field("Asia/Kolkata", max_length=64)
    open_time: str = Field("09:00", max_length=5)
    close_time: str = Field("21:00", max_length=5)


class SiteUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    address: Optional[str] = Field(None, max_length=2000)
    city: Optional[str] = Field(None, max_length=120)
    timezone_name: Optional[str] = Field(None, max_length=64)
    open_time: Optional[str] = Field(None, max_length=5)
    close_time: Optional[str] = Field(None, max_length=5)
    is_active: Optional[bool] = None


class SiteCameraAssign(BaseModel):
    camera_ids: List[str] = Field(default_factory=list)


def _site_payload(site: Site, camera_count: int = 0) -> dict:
    return {
        "id": site.id,
        "store_id": site.slug,
        "slug": site.slug,
        "name": site.name,
        "address": site.address,
        "city": site.city,
        "timezone_name": site.timezone_name,
        "open_time": site.open_time,
        "close_time": site.close_time,
        "is_active": site.is_active,
        "camera_count": camera_count,
        "created_at": site.created_at.isoformat() if site.created_at else None,
    }


async def _unique_slug(session: AsyncSession, tenant_id: str, name: str,
                       exclude_id: str | None = None) -> str:
    """Slug that is unique within the tenant, suffixing _2, _3 … on collision."""
    base = slugify_site(name)
    candidate = base
    n = 1
    while True:
        q = select(Site.id).where(Site.tenant_id == tenant_id, Site.slug == candidate)
        if exclude_id:
            q = q.where(Site.id != exclude_id)
        clash = (await session.execute(q)).first()
        if not clash:
            return candidate
        n += 1
        candidate = f"{base}_{n}"


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a store / branch")
async def create_store(
    body: SiteCreate,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")

    slug = await _unique_slug(session, str(tenant_id), body.name)
    site = Site(
        tenant_id=str(tenant_id),
        name=body.name.strip(),
        slug=slug,
        address=body.address,
        city=body.city,
        timezone_name=body.timezone_name,
        open_time=body.open_time,
        close_time=body.close_time,
    )
    session.add(site)
    await session.commit()
    await session.refresh(site)
    logger.info("Store created | tenant=%s slug=%s", tenant_id, slug)
    return _site_payload(site)


async def _load_site(session: AsyncSession, tenant_id: str, store_id: str) -> Site:
    """Resolve a store_id (slug OR uuid) to a Site owned by this tenant."""
    site = (
        await session.execute(
            select(Site).where(
                Site.tenant_id == tenant_id,
                (Site.slug == store_id) | (Site.id == store_id),
            )
        )
    ).scalars().first()
    if site is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No such store. Stores that were auto-derived from a camera's "
                "location text are not editable — create a real store, then "
                "assign its cameras to it."
            ),
        )
    return site


@router.patch("/{store_id}", summary="Rename / update a store")
async def update_store(
    store_id: str,
    body: SiteUpdate,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")

    site = await _load_site(session, str(tenant_id), store_id)
    data = body.model_dump(exclude_unset=True)

    if "name" in data and data["name"] and data["name"].strip() != site.name:
        site.name = data["name"].strip()
        # Keep the slug stable on rename. Changing it would orphan every
        # incident already recorded against the old slug.
    for field in ("address", "city", "timezone_name", "open_time", "close_time", "is_active"):
        if field in data and data[field] is not None:
            setattr(site, field, data[field])

    await session.commit()
    await session.refresh(site)
    return _site_payload(site)


@router.delete("/{store_id}", summary="Delete a store")
async def delete_store(
    store_id: str,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")

    site = await _load_site(session, str(tenant_id), store_id)
    # Cameras are UNASSIGNED, never deleted — site_id is ON DELETE SET NULL.
    # They fall back to their legacy location-derived store id so nothing
    # disappears from the customer's dashboard.
    freed = (
        await session.execute(
            select(func.count()).select_from(CameraConfig).where(CameraConfig.site_id == site.id)
        )
    ).scalar() or 0
    await session.delete(site)
    await session.commit()
    logger.info("Store deleted | tenant=%s slug=%s cameras_unassigned=%s",
                tenant_id, site.slug, freed)
    return {"deleted": True, "store_id": site.slug, "cameras_unassigned": int(freed)}


@router.post("/{store_id}/cameras", summary="Assign cameras to a store")
async def assign_cameras(
    store_id: str,
    body: SiteCameraAssign,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")

    site = await _load_site(session, str(tenant_id), store_id)

    # Tenant scoping is enforced on the WHERE clause, not trusted from the
    # body — a caller cannot move another tenant's camera into their store.
    rows = (
        await session.execute(
            select(CameraConfig).where(
                CameraConfig.tenant_id == str(tenant_id),
                CameraConfig.camera_id.in_(body.camera_ids or []),
            )
        )
    ).scalars().all()

    for cam in rows:
        cam.site_id = site.id
    await session.commit()

    matched = {c.camera_id for c in rows}
    unknown = [c for c in (body.camera_ids or []) if c not in matched]
    return {
        "store_id": site.slug,
        "assigned": sorted(matched),
        "unknown_camera_ids": unknown,
    }


@router.delete("/{store_id}/cameras/{camera_id}", summary="Unassign a camera from a store")
async def unassign_camera(
    store_id: str,
    camera_id: str,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")

    site = await _load_site(session, str(tenant_id), store_id)
    cam = (
        await session.execute(
            select(CameraConfig).where(
                CameraConfig.tenant_id == str(tenant_id),
                CameraConfig.camera_id == camera_id,
                CameraConfig.site_id == site.id,
            )
        )
    ).scalars().first()
    if cam is None:
        raise HTTPException(status_code=404, detail="Camera not assigned to this store")
    cam.site_id = None
    await session.commit()
    return {"store_id": site.slug, "unassigned": camera_id}


# ---------------------------------------------------------------------------
# GET /api/stores/{store_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Get store detail",
)
async def get_store(
    store_id: str,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> StoreResponse:
    """Return detail for a single store, derived from the tenant camera table."""
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")

    try:
        rows = (
            await session.execute(
                select(CameraConfig).where(CameraConfig.tenant_id == tenant_id)
            )
        ).scalars().all()
    except Exception:  # noqa: BLE001
        rows = []

    cameras = []
    for cam in rows:
        location = cam.location or ""
        prefix = location.split("\u2013")[0].split("-")[0].strip() if location else ""
        cam_store_id = (prefix or "auto-detected").lower().replace(" ", "_")
        if cam_store_id == store_id:
            cameras.append(cam)

    # Live risk/events only exist when an on-box pipeline is running.
    risk_data = None
    recent_events: dict = {}
    if _pipeline is not None:
        risk_data = getattr(_pipeline, "risk_scores", {}).get(store_id)
        recent_events = getattr(_pipeline, "recent_events", {}) or {}

    if risk_data is None and not cameras:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{store_id}' not found.",
        )

    score = float((risk_data or {}).get("score", 0.0))
    active = sum(
        1 for cam in cameras if (getattr(cam, "conn_status", "") or "").lower() == "online"
    )
    location_label = next(
        (c.location for c in cameras if getattr(c, "location", None)),
        store_id.replace("_", " ").title(),
    )
    last_events = recent_events.get(store_id, [])
    last_event_at = (
        (last_events[0].get("timestamp") or last_events[0].get("occurred_at"))
        if last_events else None
    )

    return StoreResponse(
        store_id=store_id,
        name=_store_display_name(store_id),
        location=location_label,
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
    # Analytics (risk scoring) only exist when an on-box pipeline is running.
    # On the multi-tenant SaaS backend there is no pipeline, so return a clean
    # zero score rather than a 503.
    if _pipeline is None:
        return RiskScoreResponse(
            store_id=store_id,
            score=0.0,
            severity=SeverityLevel.LOW,
            event_counts={},
            window_seconds=300,
            computed_at=datetime.now(tz=timezone.utc),
        )

    pipeline = _pipeline

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
    # Heatmaps are produced by the on-box pipeline. Return an empty grid on the
    # SaaS backend instead of raising 503.
    if _pipeline is None:
        return HeatmapResponse(
            store_id=store_id,
            window=window,
            grid_rows=10,
            grid_cols=10,
            cells=[],
            generated_at=datetime.now(tz=timezone.utc),
        )

    pipeline = _pipeline
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
    # Incident history is held in the on-box pipeline's in-memory buffer. On the
    # SaaS backend there is none yet — return an empty page rather than 503.
    if _pipeline is None:
        return IncidentListResponse(
            incidents=[],
            pagination=PaginationMeta(page=page, limit=limit, total=0, pages=1),
        )

    pipeline = _pipeline
    # recent_events[store_id] is already newest-first (index 0 = most
    # recent) — both live events (appendleft in _emit_edge_event /
    # demo_router._inject) and SQLite hydration on startup preserve this
    # convention. Do NOT reverse here — doing so previously put the oldest
    # entries first, burying brand-new incidents on the last page.
    all_incidents: List[dict] = list(pipeline.recent_events.get(store_id, []))

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
                    is_demo=bool(raw.get("is_demo", False)),
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
    # Queue analytics come from the on-box pipeline. Empty list on SaaS.
    if _pipeline is None:
        return QueueStatusResponse(
            lanes=[],
            retrieved_at=datetime.now(tz=timezone.utc),
        )

    pipeline = _pipeline
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
