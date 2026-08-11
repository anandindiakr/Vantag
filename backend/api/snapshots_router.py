"""
backend/api/snapshots_router.py
================================
Authenticated snapshot file serving.

Replaces the unauthenticated ``StaticFiles`` mount for the /snapshots directory.

Endpoints
---------
GET /api/snapshots/{tenant_id}/{camera_id}/{filename}
    Serves a camera snapshot. Requires a valid JWT whose ``tenant_id`` claim
    matches the ``tenant_id`` path segment.

GET /api/snapshots/watchlist/{tenant_id}/{filename}
    Serves a tenant-scoped watchlist profile image.

GET /api/snapshots/watchlist/{filename}
    Serves a legacy flat watchlist image only when its recorded owner matches
    the authenticated tenant.

GET /api/snapshots/demo/{filename}
    Serves a demo-mode snapshot. New demo files encode the tenant in the
    filename and are stored below ``snapshots/demo/{tenant_id}/``.

Security
--------
* JWT authentication is required on every request.
* Tenant-scoped paths are verified against the JWT tenant claim.
* Path traversal is blocked.
* Files outside the snapshots root directory are never served.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..middleware.tenant_middleware import get_current_user_id_img

snapshots_router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])

_SNAPSHOTS_ROOT = Path(__file__).resolve().parent.parent.parent / "snapshots"


def _safe_path(base: Path, *parts: str) -> Path:
    """Resolve a path and reject any result outside ``base``."""
    try:
        candidate = (base / Path(*parts)).resolve()
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")

    base_resolved = base.resolve()
    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise HTTPException(status_code=404, detail="Not found")
    return candidate


def _reject_traversal(value: str) -> None:
    """Reject path separators and parent-directory tokens."""
    if ".." in value or "/" in value or "\\" in value:
        raise HTTPException(status_code=404, detail="Not found")


def _legacy_watchlist_tenant(filename: str) -> str | None:
    """Resolve an old flat watchlist filename to its recorded owner."""
    meta_file = _SNAPSHOTS_ROOT / "watchlist" / "watchlist_meta.json"
    try:
        entries = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    values = entries.values() if isinstance(entries, dict) else []
    for entry in values:
        if not isinstance(entry, dict):
            continue
        image_path = str(entry.get("image_path") or "")
        image_url = str(entry.get("image_url") or "")
        if Path(image_path).name == filename or image_url.rstrip("/").endswith("/" + filename):
            owner = str(entry.get("tenant_id") or "").strip()
            return owner or None
    return None


def _legacy_demo_tenant(filename: str) -> str | None:
    """Resolve an old flat demo snapshot to its incident owner."""
    incident_id = Path(filename).stem
    try:
        from ..db import incident_store

        incident = incident_store.get_incident(incident_id)
    except Exception:
        return None
    owner = str((incident or {}).get("tenant_id") or "").strip()
    return owner or None


# Reserved prefixes MUST be declared before the generic /{tenant_id}/... routes.
# Otherwise FastAPI interprets /watchlist/foo and /demo/foo as tenant_id paths.


@snapshots_router.get("/watchlist/{tenant_id}/{filename}")
async def get_tenant_watchlist_snapshot(
    tenant_id: str,
    filename: str,
    user: dict = Depends(get_current_user_id_img),
) -> FileResponse:
    """Serve a new tenant-scoped watchlist image."""
    _reject_traversal(tenant_id)
    _reject_traversal(filename)
    if str(user.get("tenant_id")) != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    file_path = _safe_path(_SNAPSHOTS_ROOT, "watchlist", tenant_id, filename)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(str(file_path), media_type="image/jpeg")


@snapshots_router.get("/watchlist/{filename}")
async def get_watchlist_snapshot(
    filename: str,
    user: dict = Depends(get_current_user_id_img),
) -> FileResponse:
    """Serve a legacy flat watchlist image only to its recorded owner."""
    _reject_traversal(filename)
    owner = _legacy_watchlist_tenant(filename)
    if owner is None or owner != str(user.get("tenant_id")):
        raise HTTPException(status_code=404, detail="Snapshot not found")

    file_path = _safe_path(_SNAPSHOTS_ROOT, "watchlist", filename)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(str(file_path), media_type="image/jpeg")


@snapshots_router.get("/demo/{filename}")
async def get_demo_snapshot(
    filename: str,
    user: dict = Depends(get_current_user_id_img),
) -> FileResponse:
    """Serve a demo snapshot with tenant ownership for new files.

    New files use ``{tenant_id}__{incident_id}.jpg`` in the URL while the
    actual file remains under ``snapshots/demo/{tenant_id}/``. Older files
    without the prefix remain readable for backwards compatibility.
    """
    _reject_traversal(filename)
    if "__" in filename:
        tenant_id, stored_filename = filename.split("__", 1)
        _reject_traversal(tenant_id)
        _reject_traversal(stored_filename)
        if str(user.get("tenant_id")) != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")
        file_path = _safe_path(_SNAPSHOTS_ROOT, "demo", tenant_id, stored_filename)
    else:
        # Legacy demo snapshots predate tenant-aware storage. Resolve their
        # owner from the persisted incident before serving them; do not fall
        # back to "any authenticated user" because the filename is guessable.
        owner = _legacy_demo_tenant(filename)
        if owner is None or owner != str(user.get("tenant_id")):
            raise HTTPException(status_code=404, detail="Snapshot not found")
        file_path = _safe_path(_SNAPSHOTS_ROOT, "demo", filename)

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(str(file_path), media_type="image/jpeg")


@snapshots_router.get("/{tenant_id}/{camera_id}/{filename}")
async def get_camera_snapshot(
    tenant_id: str,
    camera_id: str,
    filename: str,
    user: dict = Depends(get_current_user_id_img),
) -> FileResponse:
    """Serve a tenant-scoped camera snapshot (JWT header or query token)."""
    _reject_traversal(tenant_id)
    _reject_traversal(camera_id)
    _reject_traversal(filename)
    if str(user.get("tenant_id")) != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    file_path = _safe_path(_SNAPSHOTS_ROOT, tenant_id, camera_id, filename)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(str(file_path), media_type="image/jpeg")
