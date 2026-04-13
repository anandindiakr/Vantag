"""
backend/api/tenants_router.py
=============================
Tenant self-service endpoints: profile, cameras, settings, edge agents.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.tenant import Tenant, EdgeAgent
from ..db.models.camera import CameraConfig
from ..db.models.event import DetectionEvent
from ..middleware.tenant_middleware import get_current_user_id

tenants_router = APIRouter(prefix="/api/tenants", tags=["tenants"])


@tenants_router.get("/me")
async def get_my_tenant(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "email": tenant.email,
        "phone": tenant.phone,
        "country": tenant.country,
        "region": tenant.region,
        "plan_id": tenant.plan_id,
        "status": tenant.status,
        "language": tenant.language,
        "trial_ends_at": tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        "created_at": tenant.created_at.isoformat(),
    }


class UpdateSettingsBody(BaseModel):
    language: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None


@tenants_router.patch("/me/settings")
async def update_settings(
    body: UpdateSettingsBody,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await session.execute(
            update(Tenant).where(Tenant.id == user["tenant_id"]).values(**updates)
        )
        await session.commit()
    return {"updated": True, **updates}


@tenants_router.get("/me/cameras")
async def get_my_cameras(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(CameraConfig).where(CameraConfig.tenant_id == user["tenant_id"])
    )
    cameras = result.scalars().all()
    return {
        "cameras": [
            {
                "id": c.id,
                "camera_id": c.camera_id,
                "name": c.name,
                "ip_address": c.ip_address,
                "brand": c.brand,
                "location": c.location,
                "conn_status": c.conn_status,
                "enabled": c.enabled,
                "fps_target": c.fps_target,
            }
            for c in cameras
        ]
    }


@tenants_router.get("/me/edge-agents")
async def get_my_edge_agents(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(EdgeAgent).where(EdgeAgent.tenant_id == user["tenant_id"])
    )
    agents = result.scalars().all()
    return {
        "agents": [
            {
                "id": a.id,
                "device_type": a.device_type,
                "device_name": a.device_name,
                "status": a.status,
                "camera_count": a.camera_count,
                "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
            }
            for a in agents
        ]
    }


@tenants_router.get("/me/events")
async def get_my_events(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(DetectionEvent)
        .where(DetectionEvent.tenant_id == user["tenant_id"])
        .order_by(DetectionEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    events = result.scalars().all()
    return {
        "events": [
            {
                "id": e.id,
                "camera_id": e.camera_id,
                "event_type": e.event_type,
                "severity": e.severity,
                "confidence": e.confidence,
                "risk_score": e.risk_score,
                "location": e.location,
                "created_at": e.created_at.isoformat(),
                "acknowledged": e.acknowledged,
            }
            for e in events
        ]
    }
