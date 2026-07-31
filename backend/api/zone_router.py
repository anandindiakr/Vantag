"""
backend/api/zone_router.py
===========================
Zone CRUD endpoints — read and write zone definitions per camera.

Cameras managed through the dashboard (and auto-discovered by the Windows
Edge Agent) live in the tenant-scoped ``CameraConfig`` DB table (see
``backend/db/models/camera.py``), NOT in the legacy ``cameras.yaml`` file.
This router reads/writes each camera's ``analyzer_config`` JSON column,
matching the exact structure ``cameras_router.py`` already uses for other
per-camera settings (confidence_threshold, etc.).

Zones are stored as JSON so the frontend visual editor can round-trip them
without touching any on-disk config directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.camera import CameraConfig
from ..middleware.tenant_middleware import get_current_user_id as get_current_user

router = APIRouter(prefix="/api/zones", tags=["Zones"])

# ── Pydantic models ───────────────────────────────────────────────────────────


class BboxZone(BaseModel):
    label:       str
    bbox:        list[int]            # [x1, y1, x2, y2] in pixels
    zone_type:   str = "shelf"        # shelf | queue | people_count
    max_queue:   int | None = None    # for queue zones


class PolygonZone(BaseModel):
    name:         str
    polygon:      list[list[int]]     # [[x,y], [x,y], ...]  ≥ 3 points
    severity:     str = "high"
    allowed_hours: list[int] | None = None  # [start_hour, end_hour]


class ZoneConfig(BaseModel):
    shelf_zones:      list[BboxZone]    = []
    restricted_zones: list[PolygonZone] = []
    queue_zones:      list[BboxZone]    = []
    people_count_zones: list[BboxZone] = []
    # ROI masking: areas EXCLUDED from all detection (public sidewalk seen
    # through a window, a mirror/TV reflecting people, out-of-scope aisle).
    exclusion_zones:  list[BboxZone]    = []


class ZoneConfigResponse(BaseModel):
    camera_id:  str
    camera_name: str
    resolution: dict[str, int]
    zones:      ZoneConfig


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _find_camera(
    session: AsyncSession, tenant_id: str | None, cam_id: str
) -> CameraConfig:
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing tenant context.",
        )
    result = await session.execute(
        select(CameraConfig).where(
            CameraConfig.tenant_id == tenant_id,
            CameraConfig.camera_id == cam_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{cam_id}' not found.",
        )
    return row


def _parse_zones(ac: dict[str, Any]) -> ZoneConfig:
    """Extract structured zones from a camera's analyzer_config dict."""
    ac = ac or {}

    # Shelf zones (from inventory_movement)
    im_cfg    = ac.get("inventory_movement") or {}
    raw_shelf = im_cfg.get("zones") or []
    shelves   = [
        BboxZone(label=z.get("label", "Shelf"), bbox=z["bbox"], zone_type="shelf")
        for z in raw_shelf
        if "bbox" in z
    ]

    # Restricted zones
    rz_cfg     = ac.get("restricted_zone") or {}
    raw_rz     = rz_cfg.get("restricted_zones") or []
    restricted = [
        PolygonZone(
            name=z.get("name", "Zone"),
            polygon=z.get("polygon", []),
            severity=z.get("severity", "high"),
            allowed_hours=z.get("allowed_hours"),
        )
        for z in raw_rz
    ]

    # Queue zones
    ql_cfg     = ac.get("queue_length") or {}
    raw_queue  = ql_cfg.get("queue_zones") or []
    queues     = [
        BboxZone(
            label=z.get("label", "Queue"),
            bbox=z["bbox"],
            zone_type="queue",
            max_queue=z.get("max_queue"),
        )
        for z in raw_queue
        if "bbox" in z
    ]

    pc_cfg = ac.get("people_count") or {}
    raw_people_count = pc_cfg.get("zones") or []
    people_count = [
        BboxZone(
            label=z.get("label", "People Count"),
            bbox=z["bbox"],
            zone_type="people_count",
        )
        for z in raw_people_count
        if "bbox" in z
    ]

    excl_cfg = ac.get("exclusion") or {}
    raw_exclusion = excl_cfg.get("zones") or []
    exclusion = [
        BboxZone(
            label=z.get("label", "Excluded Area"),
            bbox=z["bbox"],
            zone_type="exclusion",
        )
        for z in raw_exclusion
        if "bbox" in z
    ]

    return ZoneConfig(
        shelf_zones=shelves,
        restricted_zones=restricted,
        queue_zones=queues,
        people_count_zones=people_count,
        exclusion_zones=exclusion,
    )


def _build_response(row: CameraConfig) -> ZoneConfigResponse:
    return ZoneConfigResponse(
        camera_id=row.camera_id,
        camera_name=row.name or row.camera_id,
        resolution={
            "width":  getattr(row, "resolution_width", None) or 1920,
            "height": getattr(row, "resolution_height", None) or 1080,
        },
        zones=_parse_zones(row.analyzer_config or {}),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/cameras/{cam_id}",
    response_model=ZoneConfigResponse,
    summary="Get zone configuration for a camera",
)
async def get_zones(
    cam_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ZoneConfigResponse:
    row = await _find_camera(session, user.get("tenant_id"), cam_id)
    return _build_response(row)


@router.put(
    "/cameras/{cam_id}",
    response_model=ZoneConfigResponse,
    summary="Save zone configuration for a camera",
    description=(
        "Writes new zone definitions to the camera's analyzer_config in the "
        "database. Takes effect on the next detection cycle."
    ),
)
async def save_zones(
    cam_id: str,
    body:   ZoneConfig,
    user:   dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ZoneConfigResponse:
    row = await _find_camera(session, user.get("tenant_id"), cam_id)

    ac: dict[str, Any] = dict(row.analyzer_config or {})

    # -- Shelf zones → inventory_movement.zones --
    im_cfg = dict(ac.get("inventory_movement") or {
        "drop_threshold": 2,
        "check_interval_seconds": 5.0,
        "cooldown_seconds": 20,
        "person_suppression": True,
    })
    im_cfg["zones"] = [
        {"label": z.label, "bbox": z.bbox}
        for z in body.shelf_zones
    ]
    ac["inventory_movement"] = im_cfg

    # -- Restricted zones → restricted_zone.restricted_zones --
    rz_cfg = dict(ac.get("restricted_zone") or {
        "cooldown_seconds": 15,
        "min_frames_inside": 2,
    })
    rz_cfg["restricted_zones"] = [
        {
            "name": z.name,
            "polygon": z.polygon,
            "severity": z.severity,
            **({"allowed_hours": z.allowed_hours} if z.allowed_hours else {}),
        }
        for z in body.restricted_zones
    ]
    ac["restricted_zone"] = rz_cfg

    # -- Queue zones → queue_length.queue_zones --
    ql_cfg = dict(ac.get("queue_length") or {
        "alert_threshold": 5,
        "check_interval_seconds": 3.0,
        "cooldown_seconds": 60,
    })
    ql_cfg["queue_zones"] = [
        {
            "label": z.label,
            "bbox":  z.bbox,
            "max_queue": z.max_queue or 5,
        }
        for z in body.queue_zones
    ]
    ac["queue_length"] = ql_cfg

    pc_cfg = dict(ac.get("people_count") or {})
    pc_cfg["zones"] = [
        {"label": z.label, "bbox": z.bbox}
        for z in body.people_count_zones
    ]
    ac["people_count"] = pc_cfg

    # -- Exclusion zones (ROI masking) → exclusion.zones --
    excl_cfg = dict(ac.get("exclusion") or {})
    excl_cfg["zones"] = [
        {"label": z.label, "bbox": z.bbox}
        for z in body.exclusion_zones
    ]
    ac["exclusion"] = excl_cfg

    # Reassign (not mutate in place) so SQLAlchemy detects the JSONB change.
    row.analyzer_config = ac
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return _build_response(row)
