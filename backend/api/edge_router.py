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
GET  /api/edge/agents                – list tenant's agents + live status (JWT)
"""
from __future__ import annotations

import asyncio
import base64
import os
import time
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.tenant import EdgeAgent, Tenant
from ..db.models.camera import CameraConfig
from ..db.models.event import DetectionEvent
from ..middleware.tenant_middleware import get_current_user_id

edge_router = APIRouter(prefix="/api/edge", tags=["edge-agent"])

logger = logging.getLogger("vantag.edge")

# ---------------------------------------------------------------------------
# Live pipeline wiring (populated by main.py via set_pipeline) + snapshot store
# ---------------------------------------------------------------------------

# Populated by main.py via set_pipeline() — same shared instance used by
# demo_router / stores_router so edge incidents fan out to the live dashboard.
_pipeline = None  # type: ignore[assignment]

# Snapshot root that snapshots_router serves at
# /api/snapshots/{tenant_id}/{camera_id}/{filename}
_SNAPSHOTS_ROOT = Path(__file__).resolve().parent.parent.parent / "snapshots"


def set_pipeline(p) -> None:  # type: ignore[no-untyped-def]
    global _pipeline  # noqa: PLW0603
    _pipeline = p


# ---------------------------------------------------------------------------
# Live frame relay — in-memory latest-frame cache
# ---------------------------------------------------------------------------
# Cameras are almost always on a private LAN the cloud backend cannot reach
# directly (see cameras_router.test_camera_connection). The Edge Agent already
# opens the RTSP stream locally, so it pushes a low-fps JPEG frame here and
# cameras_router's /stream endpoint reads the latest one for that camera.
#
# Keyed by camera_id -> (jpeg_bytes, monotonic_timestamp, tenant_id).
# In-memory only (per-process); fine for a single backend instance. If the
# backend is ever scaled horizontally this should move to Redis.
_latest_edge_frames: dict[str, tuple[bytes, float, str]] = {}
_FRAME_STALE_SEC = 15.0  # treat a frame as unavailable if older than this


def get_latest_edge_frame(tenant_id: str, camera_id: str) -> bytes | None:
    """Return the most recent JPEG frame pushed by the Edge Agent for this
    camera, or None if no frame has arrived recently (or it belongs to a
    different tenant)."""
    entry = _latest_edge_frames.get(camera_id)
    if entry is None:
        return None
    jpeg_bytes, ts, frame_tenant_id = entry
    if frame_tenant_id != tenant_id:
        return None
    if (time.monotonic() - ts) > _FRAME_STALE_SEC:
        return None
    return jpeg_bytes


def _save_edge_snapshot(tenant_id: str, camera_id: str, b64: str) -> str | None:
    """Decode a base64 JPEG from the edge agent and persist it under the
    snapshots root so the JWT-scoped snapshots endpoint can serve it.

    Returns the public ``/api/snapshots/...`` URL, or None on failure.
    """
    if not b64:
        return None
    try:
        # Strip an optional data-URI prefix ("data:image/jpeg;base64,....")
        if "," in b64 and b64.strip().lower().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64)
        cam_dir = _SNAPSHOTS_ROOT / str(tenant_id) / str(camera_id)
        cam_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{uuid.uuid4().hex}.jpg"
        (cam_dir / fname).write_bytes(raw)
        return f"/api/snapshots/{tenant_id}/{camera_id}/{fname}"
    except Exception:  # noqa: BLE001
        return None


async def _emit_edge_event(event: dict, store_id: str) -> None:
    """Fan a canonical edge event into the live pipeline, mirroring
    demo_router._inject(): recent_events + risk buffer + SQLite persist +
    WebSocket broadcast. No-op if the pipeline is not wired yet.
    """
    pipe = _pipeline
    if pipe is None:
        return
    event_type = event["type"]
    # Risk weight per event type (same scale demo_router uses)
    weights = {
        "face_match": 40, "shoplifting": 30, "tamper": 25,
        "fall_detected": 25, "fall": 25, "restricted_zone": 20,
        "loitering": 15, "inventory_movement": 10, "queue": 10,
        "queue_breach": 10,
    }
    weight = weights.get(event_type, 10)

    # 1) recent_events deque (read by stores_router.list_incidents)
    try:
        pipe.recent_events[store_id].appendleft(event)
    except Exception:  # noqa: BLE001
        pass
    # 2) risk-score buffer: (event_type, weight, monotonic) keyed by store_id
    try:
        async with pipe._event_buffer_lock:
            pipe._event_buffer[store_id].append(
                (event_type, weight, time.monotonic())
            )
    except Exception:  # noqa: BLE001
        pass
    # 3) persist to SQLite incident store (audit history)
    try:
        from ..db import incident_store as _istore  # lazy import

        await asyncio.to_thread(_istore.insert_incident, event)
    except Exception:  # noqa: BLE001
        pass
    # 4) WebSocket broadcast to the dashboard
    try:
        if pipe._ws_broadcast:
            await pipe._ws_broadcast({
                "type":         "incident",
                "incident_id":  event["incident_id"],
                "store_id":     store_id,
                "camera_id":    event["camera_id"],
                "event_type":   event_type,
                "severity":     event["severity"],
                "description":  event["description"],
                "occurred_at":  event["timestamp"],
                "snapshot_url": event.get("snapshot_url"),
                "is_demo":      False,
            })
    except Exception:  # noqa: BLE001
        pass

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

# In-memory per-tenant "please run a LAN camera scan" flags. Single uvicorn
# process, so a plain dict is sufficient (mirrors _bootstrap_tokens). The agent
# consumes the flag on its next heartbeat.
_scan_requests: dict[str, bool] = {}  # tenant_id → scan_requested

# ---------------------------------------------------------------------------
# RTSP probe jobs — the cloud cannot reach private LAN IPs, so path probing
# (e.g. "auto-detect RTSP path" for Hikvision/Dahua/...) is delegated to the
# tenant's online Edge Agent. Jobs are queued here, delivered in the heartbeat
# response, and the agent POSTs the result back to /edge/rtsp-probe-result.
# ---------------------------------------------------------------------------
_rtsp_probe_jobs: dict[str, list[dict]] = {}    # tenant_id → queued jobs
_rtsp_probe_results: dict[str, dict] = {}       # job_id → result record
_PROBE_RESULT_TTL = 600  # seconds


def _prune_probe_results() -> None:
    cutoff = datetime.now(timezone.utc).timestamp() - _PROBE_RESULT_TTL
    stale = [k for k, v in _rtsp_probe_results.items() if v.get("_ts", 0) < cutoff]
    for k in stale:
        _rtsp_probe_results.pop(k, None)


def queue_rtsp_probe(tenant_id: str, ip: str, port: int = 554,
                     username: str | None = None, password: str | None = None,
                     brand: str | None = None) -> str:
    """Queue an agent-side RTSP path probe. Returns the job_id to poll."""
    _prune_probe_results()
    job_id = uuid.uuid4().hex
    _rtsp_probe_jobs.setdefault(tenant_id, []).append({
        "job_id": job_id, "ip": ip, "port": port,
        "username": username, "password": password, "brand": brand,
    })
    _rtsp_probe_results[job_id] = {
        "status": "pending",
        "_ts": datetime.now(timezone.utc).timestamp(),
    }
    return job_id


def consume_rtsp_probes(tenant_id: str) -> list[dict]:
    """Return (and clear) queued probe jobs for this tenant's agent."""
    return _rtsp_probe_jobs.pop(tenant_id, [])


def get_rtsp_probe_result(job_id: str) -> dict | None:
    return _rtsp_probe_results.get(job_id)


def request_camera_scan(tenant_id: str) -> None:
    """Mark that the given tenant's agent should run a discovery scan."""
    _scan_requests[tenant_id] = True


def consume_camera_scan(tenant_id: str) -> bool:
    """Return True (and clear) if a scan was requested for this tenant."""
    return _scan_requests.pop(tenant_id, False)


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
                "rtsp_url": c.get_rtsp_url() if hasattr(c, "get_rtsp_url") else c.rtsp_url,
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
    return {
        "ok": True,
        "server_time": now.isoformat(),
        "scan_requested": consume_camera_scan(agent.tenant_id),
        "rtsp_probe_jobs": consume_rtsp_probes(agent.tenant_id),
    }


class FramePushBody(BaseModel):
    camera_id: str
    frame_b64: str


@edge_router.post("/frame")
async def push_frame(
    body: FramePushBody,
    agent: EdgeAgent = Depends(_verify_agent),
) -> dict:
    """Receive a low-fps JPEG frame from the Edge Agent for live preview.

    The cloud backend cannot reach camera RTSP URLs on a private LAN, so the
    on-site Edge Agent (which already has the stream open locally) pushes a
    frame every ~200ms. The most recent frame per camera is kept in memory
    and served by cameras_router's ``/stream`` endpoint. This is best-effort
    and intentionally lightweight — no retries, no persistence.
    """
    b64 = body.frame_b64
    if not b64:
        return {"ok": False}
    try:
        if "," in b64 and b64.strip().lower().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64)
    except Exception:  # noqa: BLE001
        return {"ok": False}
    _latest_edge_frames[body.camera_id] = (raw, time.monotonic(), agent.tenant_id)
    return {"ok": True}


class RtspProbeResultBody(BaseModel):
    job_id: str
    success: bool
    rtsp_path: str | None = None
    rtsp_url: str | None = None
    brand: str | None = None
    tried_paths: list[str] | None = None
    error: str | None = None


@edge_router.post("/rtsp-probe-result")
async def rtsp_probe_result(
    body: RtspProbeResultBody,
    agent: EdgeAgent = Depends(_verify_agent),
) -> dict:
    """Edge Agent reports the outcome of an RTSP path probe job."""
    rec = _rtsp_probe_results.get(body.job_id)
    if rec is None:
        # Unknown/expired job — accept silently so the agent doesn't retry.
        return {"ok": True, "known": False}
    rec.update({
        "status": "done",
        "success": body.success,
        "rtsp_path": body.rtsp_path,
        "rtsp_url": body.rtsp_url,
        "brand": body.brand,
        "tried_paths": body.tried_paths or [],
        "error": body.error,
        "_ts": datetime.now(timezone.utc).timestamp(),
    })
    return {"ok": True, "known": True}


class DiscoveredCameraItem(BaseModel):
    ip: str
    port: int = 554
    brand: str | None = None
    model: str | None = None
    rtsp_path: str | None = None
    rtsp_url: str | None = None
    thumbnail_b64: str | None = None
    onvif: bool = False
    confidence: float | None = None
    needs_credentials: bool = False
    used_default_credential: bool = False


class DiscoveredCamerasBody(BaseModel):
    cameras: list[DiscoveredCameraItem] = []


@edge_router.post("/cameras/discovered")
async def ingest_discovered_cameras(
    body: DiscoveredCamerasBody,
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Receive LAN-discovered cameras from the edge agent and upsert them as
    ``CameraConfig`` rows (``enabled=False`` — awaiting user confirmation).

    The agent runs the scan on the tenant's private store network; the backend
    persists the results so they surface in the dashboard's auto-detected list.
    """
    upserted = 0
    for cam in body.cameras:
        if not cam.ip:
            continue
        camera_id = "disc-" + cam.ip.replace(".", "-")

        # Save the thumbnail (if any) so the dashboard can render a preview.
        thumb_url = None
        if cam.thumbnail_b64:
            thumb_url = _save_edge_snapshot(agent.tenant_id, camera_id, cam.thumbnail_b64)

        frame_ok = bool(cam.rtsp_url and cam.thumbnail_b64)
        probe = {
            "port": cam.port,
            "rtsp_path": cam.rtsp_path,
            "onvif": cam.onvif,
            "confidence": cam.confidence,
            "needs_credentials": cam.needs_credentials,
            "used_default_credential": cam.used_default_credential,
            "thumbnail_url": thumb_url,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        }

        existing = (
            await session.execute(
                select(CameraConfig).where(
                    CameraConfig.tenant_id == agent.tenant_id,
                    CameraConfig.camera_id == camera_id,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            row = CameraConfig(
                tenant_id=agent.tenant_id,
                camera_id=camera_id,
                name=cam.brand or f"Camera {cam.ip}",
                ip_address=cam.ip,
                brand=cam.brand,
                model=cam.model,
                conn_status="online" if frame_ok else "pending",
                probe_result=probe,
                enabled=False,
            )
            if cam.rtsp_url:
                row.set_rtsp_url(cam.rtsp_url)
            session.add(row)
            upserted += 1
        else:
            # Only refresh discovery metadata; never override an already
            # user-confirmed (enabled) camera's connection details.
            existing.ip_address = cam.ip
            if cam.brand:
                existing.brand = cam.brand
            if cam.model:
                existing.model = cam.model
            existing.probe_result = probe
            if not existing.enabled:
                existing.conn_status = "online" if frame_ok else "pending"
                if cam.rtsp_url:
                    existing.set_rtsp_url(cam.rtsp_url)
            upserted += 1

    await session.commit()
    logger.info(
        "Edge agent reported %d discovered camera(s) | tenant=%s",
        upserted, agent.tenant_id,
    )
    return {"ok": True, "upserted": upserted}


@edge_router.post("/events")
async def ingest_event(
    body: DetectionEventBody,
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Receive a detection event from the edge agent and fan it out to the
    live dashboard pipeline (recent_events + risk buffer + SQLite + WebSocket).
    """
    # 1) Decode + persist the snapshot JPEG so the dashboard can display it.
    snapshot_url = None
    if body.snapshot_b64:
        snapshot_url = _save_edge_snapshot(
            agent.tenant_id, body.camera_id, body.snapshot_b64
        )

    # 2) Derive the store_id the dashboard keys incidents by (from the
    #    camera's location, mirroring stores_router._camera_store_id).
    location = body.location
    if location is None:
        try:
            cam = (
                await session.execute(
                    select(CameraConfig).where(
                        CameraConfig.tenant_id == agent.tenant_id,
                        CameraConfig.camera_id == body.camera_id,
                    )
                )
            ).scalar_one_or_none()
            if cam is not None:
                location = cam.location
        except Exception:  # noqa: BLE001
            location = None
    store_id = (location or "auto-detected").split("–")[0].strip().lower().replace(" ", "_")

    # 3) Persist the audit row in the per-tenant detection_events table.
    event = DetectionEvent(
        id=str(uuid.uuid4()),
        tenant_id=agent.tenant_id,
        camera_id=body.camera_id,
        edge_agent_id=agent.id,
        event_type=body.event_type,
        severity=body.severity,
        confidence=body.confidence,
        risk_score=body.risk_score,
        location=location,
        snapshot_url=snapshot_url,
        event_meta=body.metadata,
    )
    session.add(event)
    await session.commit()

    # 4) Build the canonical incident dict and fan it into the live pipeline.
    description = (
        (body.metadata or {}).get("description")
        if isinstance(body.metadata, dict)
        else None
    ) or f"{body.event_type.replace('_', ' ').title()} detected on {body.camera_id}"
    incident = {
        "incident_id": event.id,
        "type": body.event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "store_id": store_id,
        "camera_id": body.camera_id,
        "severity": body.severity,
        "confidence": body.confidence,
        "risk_score": body.risk_score,
        "description": description,
        "snapshot_url": snapshot_url,
        "metadata": body.metadata or {},
        "acknowledged": False,
        "is_demo": False,
    }
    try:
        await _emit_edge_event(incident, store_id)
    except Exception:  # noqa: BLE001
        pass

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
                "rtsp_url": c.get_rtsp_url() if hasattr(c, "get_rtsp_url") else c.rtsp_url,
                "name": c.name,
                "location": c.location,
                "fps_target": c.fps_target,
                "confidence_threshold": (getattr(c, "analyzer_config", None) or {}).get("confidence_threshold"),
            }
            for c in cameras
        ]
    }


@edge_router.get("/agents")
async def list_agents(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return all EdgeAgent rows for the calling tenant with derived live status.

    ``effective_status`` is ``"online"`` only when ``last_heartbeat`` is within
    the last 5 minutes; otherwise ``"offline"``.  This avoids a background
    cron job to flip the DB column and is always accurate at read time.
    """
    from datetime import timedelta

    tenant_id = user["tenant_id"]
    result = await session.execute(
        select(EdgeAgent).where(EdgeAgent.tenant_id == tenant_id)
    )
    agents = result.scalars().all()
    now = datetime.now(timezone.utc)
    stale_threshold = timedelta(minutes=5)

    items = []
    for a in agents:
        if a.last_heartbeat is not None:
            hb = a.last_heartbeat
            # Ensure tz-aware comparison
            if hb.tzinfo is None:
                from datetime import timezone as _tz
                hb = hb.replace(tzinfo=_tz.utc)
            age = now - hb
            effective_status = "online" if age <= stale_threshold else "offline"
            last_heartbeat_iso = hb.isoformat()
            last_heartbeat_age_seconds = int(age.total_seconds())
        else:
            effective_status = "offline"
            last_heartbeat_iso = None
            last_heartbeat_age_seconds = None

        items.append({
            "agent_id": a.id,
            "device_type": a.device_type,
            "device_name": a.device_name or a.device_type,
            "status": effective_status,
            "last_heartbeat": last_heartbeat_iso,
            "last_heartbeat_age_seconds": last_heartbeat_age_seconds,
            "camera_count": a.camera_count,
            "capabilities": a.capabilities,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    return {"agents": items, "total": len(items)}


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

    # Provision (or reuse) an EdgeAgent credential so the downloaded agent has
    # something to authenticate every heartbeat/event call with (X-API-Key).
    existing_agent = (
        await session.execute(
            select(EdgeAgent).where(EdgeAgent.tenant_id == tenant_id)
        )
    ).scalars().first()
    if existing_agent is not None:
        agent = existing_agent
    else:
        from ..services.tenant_service import provision_edge_agent

        agent = await provision_edge_agent(
            session,
            tenant_id,
            device_type="windows",
            device_name="Edge Agent (bootstrap)",
        )
    await session.commit()
    return {
        "registered": created,
        "total": len(body.cameras),
        "agent_id": agent.id,
        "api_key": agent.api_key,
        "store_id": "auto-detected",
    }


# ─── Downloadable, runnable Edge Agent package ──────────────────────────────
agent_download_router = APIRouter(prefix="/api/agent", tags=["edge-agent"])

# Repo root → vantag/  (edge_router.py is at vantag/backend/api/edge_router.py)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_AGENT_PKG_DIR = _REPO_ROOT / "windows_agent"

_RUN_BAT = """@echo off
REM Vantag Edge Agent launcher (Windows)
cd /d "%~dp0"
if not exist "requirements.txt" (
  echo.
  echo ============================================================
  echo   STOP - the files are still inside the ZIP.
  echo.
  echo   You double-clicked run.bat from inside the zip preview.
  echo   Please do this instead:
  echo     1^) Close this window
  echo     2^) Find vantag-edge-agent-windows.zip in your Downloads
  echo     3^) Right-click it and choose "Extract All..."
  echo     4^) Open the EXTRACTED folder
  echo     5^) Double-click run.bat there
  echo ============================================================
  echo.
  pause
  exit /b 1
)
where python >nul 2>nul || (echo Python 3.10+ is required. Install from python.org && pause && exit /b 1)
if not exist .venv (python -m venv .venv)
call .venv\\Scripts\\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m agent.main
pause
"""

_RUN_SH = """#!/usr/bin/env bash
# Vantag Edge Agent launcher (Linux/macOS)
set -e
cd "$(dirname "$0")"
if [ ! -f requirements.txt ]; then
  echo "ERROR: requirements.txt not found. Did you extract the zip first?"
  echo "Run:  unzip vantag-edge-agent-linux.zip -d vantag-agent && cd vantag-agent && ./run.sh"
  exit 1
fi
command -v python3 >/dev/null 2>&1 || { echo "Python 3.10+ is required."; exit 1; }
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m agent.main
"""

_README = """# Vantag Edge Agent - SETUP INSTRUCTIONS

############################################################
#  STEP 1 (IMPORTANT): EXTRACT THIS ZIP FIRST              #
#  Do NOT run run.bat from inside the zip preview window.  #
#  Right-click the downloaded .zip -> "Extract All..."     #
#  then open the extracted folder before continuing.       #
############################################################

This package is pre-configured for YOUR account (your keys are already inside
config.json - keep it private).

## What this does
It runs on a PC that is on the SAME local network (LAN) as your cameras. It
connects OUT to the Vantag cloud, so your cameras never need to be exposed to
the internet. This is why cameras on your LAN cannot be tested directly from
the website - the Edge Agent is what reaches them.

## Requirements
- A Windows or Linux PC kept switched on, on the same network as the cameras
- Python 3.10 or newer (Windows: install from https://python.org and tick
  "Add Python to PATH" during install)

## Windows - how to run
1. Extract the zip (see STEP 1 above).
2. Open the extracted folder.
3. Double-click `run.bat`.
   The first run downloads dependencies (a few minutes) and then starts.
4. Leave the window open. Your cameras turn ONLINE in the dashboard in ~30s.

## Linux / Raspberry Pi - how to run
    unzip vantag-edge-agent-linux.zip -d vantag-agent
    cd vantag-agent
    chmod +x run.sh
    ./run.sh

## After it starts
- Cameras appear ONLINE in your dashboard within ~30 seconds.
- Use "Auto-Scan with Edge Agent" on the Manage Cameras page to discover
  cameras on your LAN automatically.
- Real AI detections show on the Incidents page with snapshot evidence.

## Need help?
Email support@retailnazar.com (India) / support@retail-vantag.com, or use the
"Need help setting up?" chat in the app.
"""


def _agent_version() -> str:
    """Read __version__ from the bundled agent package (single source of truth)."""
    try:
        import re
        text = (_AGENT_PKG_DIR / "agent" / "__init__.py").read_text(encoding="utf-8")
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "0.0.0"


def _build_agent_zip(config: dict, platform: str) -> bytes:
    import io
    import json
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Bundle the agent python package (windows_agent/agent/*.py).
        pkg = _AGENT_PKG_DIR / "agent"
        if pkg.exists():
            for path in pkg.rglob("*.py"):
                arc = Path("agent") / path.relative_to(pkg)
                zf.write(path, str(arc))
        # requirements.txt (from the agent dir, fall back to a minimal set).
        req = _AGENT_PKG_DIR / "requirements.txt"
        if req.exists():
            zf.write(req, "requirements.txt")
        else:
            zf.writestr(
                "requirements.txt",
                "opencv-python-headless\nonnxruntime\nnumpy\nrequests\npaho-mqtt\npsutil\n",
            )
        # Prefilled config.json (sits next to the package; loaded by config.load()).
        zf.writestr("config.json", json.dumps(config, indent=2))
        # Version stamp so users can tell which build they have.
        zf.writestr("VERSION.txt", f"Vantag Edge Agent v{_agent_version()}\n")
        # Launchers + readme.
        zf.writestr("run.bat", _RUN_BAT)
        zf.writestr("run.sh", _RUN_SH)
        zf.writestr("README.md", _README)
    return buf.getvalue()


@agent_download_router.get("/download")
async def download_agent(
    request: Request,
    platform: str = "windows",
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Build and return a credentialed, ready-to-run Edge Agent zip."""
    from fastapi import Response

    tenant_id = user["tenant_id"]

    # Provision (or reuse) the caller's EdgeAgent credential.
    agent = (
        await session.execute(
            select(EdgeAgent).where(EdgeAgent.tenant_id == tenant_id)
        )
    ).scalars().first()
    if agent is None:
        from ..services.tenant_service import provision_edge_agent

        agent = await provision_edge_agent(
            session,
            tenant_id,
            device_type=platform,
            device_name="Edge Agent (download)",
        )
        await session.commit()

    # Load this tenant's cameras to prefill the agent config.
    cams = (
        await session.execute(
            select(CameraConfig).where(
                CameraConfig.tenant_id == tenant_id,
                CameraConfig.enabled == True,  # noqa: E712
            )
        )
    ).scalars().all()

    # Behind an nginx reverse-proxy, request.base_url resolves to the internal
    # address (http://127.0.0.1:8000).  Use the forwarded headers that nginx
    # sends (X-Forwarded-Proto + Host) to build the correct public URL so the
    # downloaded config.json points the store-LAN agent at the real domain.
    proto = request.headers.get("X-Forwarded-Proto", "https")
    host = request.headers.get("Host", request.url.netloc)
    # Nginx 301-redirects "www.<domain>" -> "<domain>" for canonicalization.
    # HTTP clients downgrade POST->GET on a 301, so if the agent's baked-in
    # backend_url uses the "www." host, every heartbeat/frame-push POST the
    # agent sends gets silently turned into a GET and never reaches the
    # backend. Always strip "www." here so the agent talks to the bare
    # canonical domain directly and never hits that redirect.
    if host.startswith("www."):
        host = host[4:]
    backend_url = f"{proto}://{host}"
    # MQTT broker is on the same VPS — strip the port from the Host header to
    # get just the hostname (retail-vantag.com / retailnazar.com / etc.)
    mqtt_host = host.split(":")[0]

    config = {
        "api_key": agent.api_key,
        "agent_id": agent.id,
        "backend_url": backend_url,
        "mqtt_host": mqtt_host,
        "mqtt_port": int(os.getenv("MQTT_PORT", "1883")),
        "tenant_id": tenant_id,
        # NOTE: keys here MUST match windows_agent/agent/config.py::CameraConfig
        # fields (id, name, rtsp_url, location, ...). Any extra/renamed key makes
        # CameraConfig(**c) raise TypeError, which AgentConfig.load() swallows and
        # then falls back to an EMPTY config (no api_key) -> dead agent.
        "cameras": [
            {
                "id": c.camera_id,
                "name": c.name,
                "rtsp_url": (c.get_rtsp_url() if hasattr(c, "get_rtsp_url") else None) or "",
                "location": getattr(c, "location", "") or "",
                "confidence": (getattr(c, "analyzer_config", None) or {}).get("confidence_threshold"),
            }
            for c in cams
        ],
    }

    data = _build_agent_zip(config, platform)
    fname = f"vantag-edge-agent-{platform}-v{_agent_version()}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
