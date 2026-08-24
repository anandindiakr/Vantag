"""
backend/api/watchlist_router.py
================================
Watchlist CRUD API for the Vantag platform.

Endpoints
---------
GET    /api/watchlist                  – list all entries (no embeddings)
POST   /api/watchlist                  – add entry (multipart: name, alert_level, face_image)
DELETE /api/watchlist/{entry_id}       – remove entry
GET    /api/watchlist/matches?limit=50 – recent match events

Face embeddings are stored on disk and kept separate from the API responses.
The face image is written to ``snapshots/watchlist/{entry_id}.jpg``.
Embeddings would normally be computed by the face recognition model;
this router stores the raw image and leaves embedding computation to the
pipeline (which reads from the same directory on startup).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from ..middleware.tenant_middleware import get_current_user_id

from .models import (
    AlertLevel,
    WatchlistEntryResponse,
    WatchlistListResponse,
    WatchlistMatchEvent,
    WatchlistMatchesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["Watchlist"])

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_WATCHLIST_DIR: Path = _BASE_DIR / "snapshots" / "watchlist"
_META_FILE: Path = _WATCHLIST_DIR / "watchlist_meta.json"
_MATCHES_FILE: Path = _WATCHLIST_DIR / "match_events.json"

# ---------------------------------------------------------------------------
# In-memory registries
# ---------------------------------------------------------------------------

_entries: Dict[str, dict] = {}     # entry_id → entry dict (no embeddings)
_matches: List[dict] = []           # chronological match events


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _ensure_dir() -> None:
    _WATCHLIST_DIR.mkdir(parents=True, exist_ok=True)


def _load_state() -> None:
    """Load entries and match events from disk on startup."""
    global _entries, _matches  # noqa: PLW0603
    _ensure_dir()

    if _META_FILE.exists():
        try:
            with _META_FILE.open("r", encoding="utf-8") as fh:
                _entries = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load watchlist metadata | error=%s", exc)
            _entries = {}

    if _MATCHES_FILE.exists():
        try:
            with _MATCHES_FILE.open("r", encoding="utf-8") as fh:
                _matches = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load match events | error=%s", exc)
            _matches = []


def _flush_entries() -> None:
    _ensure_dir()
    try:
        with _META_FILE.open("w", encoding="utf-8") as fh:
            json.dump(_entries, fh, indent=2, default=str)
    except OSError as exc:
        logger.error("Failed to flush watchlist metadata | error=%s", exc)


def _flush_matches() -> None:
    _ensure_dir()
    try:
        # Keep only the last 10 000 matches to avoid unbounded growth.
        trimmed = _matches[-10_000:]
        with _MATCHES_FILE.open("w", encoding="utf-8") as fh:
            json.dump(trimmed, fh, indent=2, default=str)
    except OSError as exc:
        logger.error("Failed to flush match events | error=%s", exc)


def _tenant_id(user: dict) -> str:
    tenant_id = str(user.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return tenant_id


def _entry_to_model(entry: dict) -> WatchlistEntryResponse:
    return WatchlistEntryResponse(
        entry_id=entry["entry_id"],
        name=entry["name"],
        alert_level=AlertLevel(entry["alert_level"]),
        notes=entry.get("notes"),
        created_at=datetime.fromisoformat(entry["created_at"]),
        image_url=entry.get("image_url"),
    )


def _match_to_model(match: dict) -> WatchlistMatchEvent:
    return WatchlistMatchEvent(
        match_id=match["match_id"],
        entry_id=match["entry_id"],
        entry_name=match["entry_name"],
        alert_level=AlertLevel(match["alert_level"]),
        camera_id=match["camera_id"],
        store_id=match["store_id"],
        confidence=float(match["confidence"]),
        matched_at=datetime.fromisoformat(match["matched_at"]),
        snapshot_url=match.get("snapshot_url"),
    )


# Load state at module import time.
_load_state()


# ---------------------------------------------------------------------------
# Public API used by the pipeline to record matches
# ---------------------------------------------------------------------------


def record_match(
    entry_id: str,
    camera_id: str,
    store_id: str,
    confidence: float,
    snapshot_url: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Optional[WatchlistMatchEvent]:
    """
    Called by the pipeline when a face match is detected.

    Appends to the in-memory match list and flushes to disk.
    Returns the ``WatchlistMatchEvent`` model, or ``None`` if the entry_id
    is unknown.
    """
    entry = _entries.get(entry_id)
    if entry is None or (tenant_id is not None and entry.get("tenant_id") != str(tenant_id)):
        logger.warning("record_match: unknown or cross-tenant entry_id=%s", entry_id)
        return None

    match = {
        "match_id": str(uuid.uuid4()),
        "tenant_id": entry.get("tenant_id"),
        "entry_id": entry_id,
        "entry_name": entry["name"],
        "alert_level": entry["alert_level"],
        "camera_id": camera_id,
        "store_id": store_id,
        "confidence": round(confidence, 4),
        "matched_at": datetime.now(tz=timezone.utc).isoformat(),
        "snapshot_url": snapshot_url,
    }
    _matches.append(match)
    _flush_matches()
    if entry["alert_level"] == "staff":
        # Staff member recognised — audit log only, no alert is raised.
        logger.info(
            "Staff face recognised (no alert) | entry=%s camera=%s confidence=%.2f",
            entry_id,
            camera_id,
            confidence,
        )
        return None
    logger.info(
        "Watchlist match recorded | entry=%s camera=%s confidence=%.2f",
        entry_id,
        camera_id,
        confidence,
    )
    return _match_to_model(match)


# ---------------------------------------------------------------------------
# GET /api/watchlist
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=WatchlistListResponse,
    summary="List all watchlist entries",
)
async def list_entries(
    user: dict = Depends(get_current_user_id),
) -> WatchlistListResponse:
    """Return only the authenticated tenant's watchlist entries."""
    tenant_id = _tenant_id(user)
    models = [_entry_to_model(e) for e in _entries.values() if e.get("tenant_id") == tenant_id]
    models.sort(key=lambda e: e.created_at, reverse=True)
    return WatchlistListResponse(entries=models, total=len(models))


# ---------------------------------------------------------------------------
# POST /api/watchlist
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=WatchlistEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a watchlist entry",
)
async def add_entry(
    name: str = Form(..., description="Display name of the individual."),
    alert_level: AlertLevel = Form(AlertLevel.MEDIUM, description="Alert severity level."),
    notes: Optional[str] = Form(None, description="Operator notes."),
    face_image: UploadFile = File(..., description="Reference face JPEG/PNG image."),
    user: dict = Depends(get_current_user_id),
) -> WatchlistEntryResponse:
    """
    Add a new entry to the watchlist.

    The face image is saved to disk; the pipeline will pick it up and
    compute the embedding on its next watchlist reload cycle.
    """
    _ensure_dir()
    tenant_id = _tenant_id(user)

    # Validate content type loosely.
    content_type = face_image.content_type or ""
    filename = (face_image.filename or "").lower()
    if not (content_type.startswith("image/") or filename.endswith((".jpg", ".jpeg", ".png"))):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="face_image must be a JPEG or PNG image.",
        )

    entry_id = str(uuid.uuid4())
    ext = ".jpg" if "jpeg" in content_type or "jpg" in filename or "jpeg" in filename else ".png"
    img_filename = f"{entry_id}{ext}"
    tenant_dir = _WATCHLIST_DIR / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    img_path = tenant_dir / img_filename

    try:
        contents = await face_image.read(2_000_001)
        if len(contents) > 2_000_000:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Face image is too large")
        with img_path.open("wb") as fh:
            fh.write(contents)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save face image: {exc}",
        ) from exc

    now = datetime.now(tz=timezone.utc).isoformat()
    image_url = f"/api/snapshots/watchlist/{tenant_id}/{img_filename}"

    entry = {
        "entry_id": entry_id,
        "tenant_id": tenant_id,
        "name": name,
        "alert_level": alert_level.value,
        "notes": notes,
        "created_at": now,
        "image_url": image_url,
        "image_path": str(img_path),
    }
    _entries[entry_id] = entry
    _flush_entries()

    logger.info("Watchlist entry added | entry_id=%s name=%s", entry_id, name)
    return _entry_to_model(entry)


# ---------------------------------------------------------------------------
# DELETE /api/watchlist/{entry_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a watchlist entry",
)
async def remove_entry(
    entry_id: str,
    user: dict = Depends(get_current_user_id),
) -> None:
    """Remove an entry from the authenticated tenant's watchlist."""
    tenant_id = _tenant_id(user)
    entry = _entries.get(entry_id)
    if entry is None or entry.get("tenant_id") != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist entry '{entry_id}' not found.",
        )

    # Delete face image file.
    img_path = Path(entry.get("image_path", ""))
    if img_path.exists():
        try:
            img_path.unlink()
        except OSError as exc:
            logger.warning(
                "Could not delete face image | path=%s error=%s", img_path, exc
            )

    del _entries[entry_id]
    _flush_entries()
    logger.info("Watchlist entry removed | entry_id=%s", entry_id)


# ---------------------------------------------------------------------------
# GET /api/watchlist/matches
# ---------------------------------------------------------------------------


@router.get(
    "/matches",
    response_model=WatchlistMatchesResponse,
    summary="Recent watchlist match events",
)
async def list_matches(
    limit: int = Query(50, ge=1, le=500, description="Maximum number of matches to return."),
    user: dict = Depends(get_current_user_id),
) -> WatchlistMatchesResponse:
    """
    Return the most recent watchlist face-match events.

    Results are ordered newest-first.
    """
    tenant_id = _tenant_id(user)
    tenant_matches = [
        raw for raw in _matches
        if raw.get("tenant_id") == tenant_id
    ]
    recent = list(reversed(tenant_matches[-limit:]))
    models: List[WatchlistMatchEvent] = []
    for raw in recent:
        try:
            models.append(_match_to_model(raw))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping malformed match entry | error=%s", exc)
            continue
    return WatchlistMatchesResponse(matches=models, total=len(tenant_matches))
