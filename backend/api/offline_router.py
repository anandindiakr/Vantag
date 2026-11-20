from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from ..db.database import get_session
from ..middleware.tenant_middleware import get_current_user_id, require_super_admin
from ..services.agent_package import PackageUnavailable, build_offline_windows_package, remove_package
from ..services.offline_entitlement import issue_for_user

router = APIRouter(prefix="/api/agent/offline", tags=["offline-agent"])


class RenewalInput(BaseModel):
    device_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str | None = Field(default=None, max_length=64)


class DemoInput(RenewalInput):
    tenant_id: str = Field(min_length=1, max_length=64)
    licence_type: str = Field(pattern=r"^(internal_demo|evaluation)$")
    days: int | None = Field(default=None, ge=1, le=365, strict=True)
    camera_limit: int = Field(default=8, ge=1, le=256, strict=True)


@router.post("/admin/demo-entitlement")
async def demo_entitlement(body: DemoInput, admin: dict = Depends(require_super_admin), session: AsyncSession = Depends(get_session)):
    from ..services.offline_entitlement import issue_demo
    try:
        envelope = await issue_demo(session, admin, body.tenant_id, body.device_id, body.licence_type, body.days, body.camera_limit)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        await session.rollback()
        raise HTTPException(503, "Offline licence signing is not configured correctly") from exc
    return JSONResponse(envelope, headers={"Content-Disposition": 'attachment; filename="vantag-demo-entitlement.json"', "Cache-Control": "no-store"})


def require_release(user: dict) -> None:
    if user.get("role") not in {"owner", "admin"}:
        raise HTTPException(403, "Only an account owner or administrator can issue offline access")
    if os.getenv("VANTAG_OFFLINE_RELEASE_READY") != "1":
        raise HTTPException(503, "The offline package is under validation and is not available for customer installation yet")
    from .edge_router import _agent_version
    from ..services.agent_package import validate_offline_windows_artifact
    try:
        validate_offline_windows_artifact(Path(os.getenv("VANTAG_WINDOWS_OFFLINE_ARTIFACT", "/app/data/agent-artifacts/windows-offline-agent.zip")), _agent_version())
    except PackageUnavailable as exc:
        raise HTTPException(503, "A qualified offline package and matching licence signer must be installed first") from exc


@router.get("/availability")
async def availability(user: dict = Depends(get_current_user_id)):
    try:
        require_release(user)
        ready = True
    except HTTPException:
        ready = False
    return {"available": ready, "scope": "Same-PC console; qualified core local AI only", "grace_days": 7, "requires_cloud_at_startup": False}


@router.post("/entitlement")
async def renewal(body: RenewalInput, user: dict = Depends(get_current_user_id), session: AsyncSession = Depends(get_session)):
    require_release(user)
    if body.tenant_id and body.tenant_id != user.get("tenant_id"):
        raise HTTPException(403, "The renewal request belongs to another account")
    try:
        envelope = await issue_for_user(session, user, body.device_id)
        await session.commit()
    except (ValueError, OSError) as exc:
        await session.rollback()
        raise HTTPException(409, "Offline entitlement could not be issued. Check account dates and administrator signing configuration.") from exc
    return JSONResponse(envelope, headers={"Content-Disposition": 'attachment; filename="vantag-offline-renewal.json"', "Cache-Control": "no-store"})


@router.get("/download")
async def download(user: dict = Depends(get_current_user_id), session: AsyncSession = Depends(get_session)):
    require_release(user)
    from .edge_router import _agent_version
    filename = None
    try:
        envelope = await issue_for_user(session, user)
        artifact = Path(os.getenv("VANTAG_WINDOWS_OFFLINE_ARTIFACT", "/app/data/agent-artifacts/windows-offline-agent.zip"))
        filename = await run_in_threadpool(build_offline_windows_package, artifact, envelope, _agent_version())
        await session.commit()
    except (ValueError, OSError, PackageUnavailable) as exc:
        if filename:
            remove_package(filename)
        await session.rollback()
        raise HTTPException(503, "Offline download is not ready. The administrator must validate the artifact, signing key and account entitlement.") from exc
    except BaseException:
        if filename:
            remove_package(filename)
        await session.rollback()
        raise
    return FileResponse(filename, media_type="application/zip", filename=f"vantag-offline-agent-v{_agent_version()}.zip", headers={"Cache-Control": "no-store"}, background=BackgroundTask(remove_package, filename))
