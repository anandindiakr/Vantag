"""
backend/api/edge_router.py
==========================
Edge Agent API — registration, heartbeat, event ingestion.
Called by the Android app and Windows Edge Agent.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.tenant import EdgeAgent, Tenant
from ..db.models.camera import CameraConfig
from ..db.models.event import DetectionEvent

edge_router = APIRouter(prefix="/api/edge", tags=["edge-agent"])


async def _verify_agent(
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> EdgeAgent:
    result = await session.execute(
        select(EdgeAgent).where(EdgeAgent.api_key == x_api_key)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return agent


class RegisterBody(BaseModel):
    device_type: str
    device_name: str | None = None
    os_version: str | None = None
    app_version: str | None = None
    capabilities: dict | None = None


class HeartbeatBody(BaseModel):
    camera_statuses: dict[str, str] | None = None  # camera_id → online/offline
    cpu_percent: float | None = None
    memory_percent: float | None = None
    fps_per_camera: dict[str, float] | None = None


class DetectionEventBody(BaseModel):
    camera_id: str
    event_type: str
    severity: str = "medium"
    confidence: float | None = None
    risk_score: float | None = None
    location: str | None = None
    snapshot_b64: str | None = None
    metadata: dict | None = None


@edge_router.post("/register")
async def register_agent(
    body: RegisterBody,
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Called once when edge agent first starts. Returns camera configs."""
    await session.execute(
        update(EdgeAgent)
        .where(EdgeAgent.id == agent.id)
        .values(
            device_type=body.device_type,
            device_name=body.device_name,
            capabilities=body.capabilities,
            status="online",
            last_heartbeat=datetime.now(timezone.utc),
        )
    )
    # Get camera configs for this tenant
    result = await session.execute(
        select(CameraConfig)
        .where(CameraConfig.tenant_id == agent.tenant_id, CameraConfig.enabled == True)
    )
    cameras = result.scalars().all()
    await session.commit()

    return {
        "agent_id": agent.id,
        "tenant_id": agent.tenant_id,
        "cameras": [
            {
                "camera_id": c.camera_id,
                "rtsp_url": c.rtsp_url,
                "name": c.name,
                "location": c.location,
                "fps_target": c.fps_target,
                "resolution_width": c.resolution_width,
                "resolution_height": c.resolution_height,
            }
            for c in cameras
        ],
    }


@edge_router.post("/heartbeat")
async def heartbeat(
    body: HeartbeatBody,
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = datetime.now(timezone.utc)
    await session.execute(
        update(EdgeAgent)
        .where(EdgeAgent.id == agent.id)
        .values(status="online", last_heartbeat=now)
    )
    # Update camera connection statuses
    if body.camera_statuses:
        for cam_id, cam_status in body.camera_statuses.items():
            await session.execute(
                update(CameraConfig)
                .where(
                    CameraConfig.tenant_id == agent.tenant_id,
                    CameraConfig.camera_id == cam_id,
                )
                .values(conn_status=cam_status, last_connected_at=now if cam_status == "online" else None)
            )
    await session.commit()
    return {"ok": True, "server_time": now.isoformat()}


@edge_router.post("/events")
async def ingest_event(
    body: DetectionEventBody,
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Receive a detection event from the edge agent."""
    snapshot_url = None
    if body.snapshot_b64:
        # In production: save to object storage (S3/R2), return URL
        snapshot_url = f"/snapshots/{agent.tenant_id}/{body.camera_id}/{uuid.uuid4()}.jpg"

    event = DetectionEvent(
        id=str(uuid.uuid4()),
        tenant_id=agent.tenant_id,
        camera_id=body.camera_id,
        edge_agent_id=agent.id,
        event_type=body.event_type,
        severity=body.severity,
        confidence=body.confidence,
        risk_score=body.risk_score,
        location=body.location,
        snapshot_url=snapshot_url,
        metadata=body.metadata,
    )
    session.add(event)
    await session.commit()

    return {"ok": True, "event_id": event.id}


@edge_router.get("/config")
async def get_config(
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Edge agent polls this to get latest camera configs."""
    result = await session.execute(
        select(CameraConfig)
        .where(CameraConfig.tenant_id == agent.tenant_id, CameraConfig.enabled == True)
    )
    cameras = result.scalars().all()
    return {
        "cameras": [
            {
                "camera_id": c.camera_id,
                "rtsp_url": c.rtsp_url,
                "name": c.name,
                "location": c.location,
                "fps_target": c.fps_target,
            }
            for c in cameras
        ]
    }
