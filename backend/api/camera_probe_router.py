"""
backend/api/camera_probe_router.py
===================================
Public endpoint for AI camera auto-configuration.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..middleware.tenant_middleware import get_current_user_id
from ..services.ai_config_service import probe_camera

camera_probe_router = APIRouter(prefix="/api/camera", tags=["camera-probe"])


class ProbeRequest(BaseModel):
    ip: str
    credentials_hint: str | None = None


@camera_probe_router.post("/probe")
async def probe(
    body: ProbeRequest,
    user: dict = Depends(get_current_user_id),
) -> dict:
    """AI-powered camera probe: auto-discovers brand, RTSP URL, and thumbnail."""
    result = await probe_camera(body.ip, body.credentials_hint)
    return result
