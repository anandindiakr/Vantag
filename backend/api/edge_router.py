"""
backend/api/edge_router.py
==========================
Edge Agent API — registration, heartbeat, event ingestion.
Called by the Android app and Windows Edge Agent.

Routes
------
POST /api/edge/register              – authenticated registration (X-API-Key)
POST /api/edge/register/bootstrap    – one-time bootstrap (registration_token required)
POST /api/edge/heartbeat             – authenticated heartbeat (X-API-Key)
POST /api/edge/events                – ingest detection event (X-API-Key)
GET  /api/edge/config                – poll latest camera config (X-API-Key)
"""
from __future__ import annotations

import os
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

# ---------------------------------------------------------------------------
# Bootstrap token store (Redis if available, in-memory fallback for dev)
# ---------------------------------------------------------------------------

_BOOTSTRAP_TTL_SECONDS = 15 * 60  # 15 minutes


def _get_redis():
    """Return a Redis client or None if Redis is not configured."""
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return None
    try:
        import redis as _redis
        return _redis.from_url(redis_url, decode_responses=True)
    except Exception:  # noqa: BLE001
        return None


# In-memory fallback for environments without Redis (dev / edge-only)
_bootstrap_tokens: dict[str, str] = {}  # token → tenant_id


def _store_bootstrap_token(token: str, tenant_id: str) -> None:
    r = _get_redis()
    if r:
        r.setex(f"bootstrap:{token}", _BOOTSTRAP_TTL_SECONDS, tenant_id)
    else:
        _bootstrap_tokens[token] = tenant_id


def _consume_bootstrap_token(token: str) -> str | None:
    """Return tenant_id and delete the token (one-time use). Returns None if invalid."""
    r = _get_redis()
    if r:
        key = f"bootstrap:{token}"
        tenant_id = r.get(key)
        if tenant_id:
            r.delete(key)
        return tenant_id
    else:
        return _bootstrap_tokens.pop(token, None)


def generate_registration_token(tenant_id: str) -> str:
    """
    Generate a one-time registration token for an edge agent bootstrap.
    The token is stored with a 15-minute TTL and consumed on first use.
    Called from the onboarding/dashboard flow.
    """
    token = uuid.uuid4().hex
    _store_bootstrap_token(token, tenant_id)
    return token


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
        # Use the authenticated snapshot endpoint path
        snapshot_url = f"/api/snapshots/{agent.tenant_id}/{body.camera_id}/{uuid.uuid4()}.jpg"

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


# ─── Simple edge agent endpoints (registration_token-based, no API key) ──────
class BootstrapRegisterBody(BaseModel):
    registration_token: str  # one-time token generated by the dashboard
    cameras: list[str]


@edge_router.post("/register/bootstrap")
async def bootstrap_register_cameras(
    body: BootstrapRegisterBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Bootstrap registration for the downloadable Python Edge Agent.

    Requires a one-time ``registration_token`` obtained from the dashboard
    (generated by the onboarding step 5 or the Install Edge Agent page).
    The token is consumed on first use and expires after 15 minutes.
    """
    tenant_id = _consume_bootstrap_token(body.registration_token)
    if not tenant_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired registration_token. Generate a new one from the dashboard.",
        )

    tenant_res = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tenant not found")

    created = 0
    for ip in body.cameras:
        cam_id = f"cam-{ip.replace('.', '-')}"
        existing = await session.execute(
            select(CameraConfig).where(
                CameraConfig.tenant_id == tenant_id,
                CameraConfig.camera_id == cam_id,
            )
        )
        if existing.scalar_one_or_none():
            continue
        cam = CameraConfig(
            tenant_id=tenant_id,
            camera_id=cam_id,
            name=f"Camera {ip}",
            location="Auto-detected",
            fps_target=10,
            enabled=True,
        )
        cam.set_rtsp_url(f"rtsp://{ip}:554/stream1")
        session.add(cam)
        created += 1
    await session.commit()
    return {"registered": created, "total": len(body.cameras)}
