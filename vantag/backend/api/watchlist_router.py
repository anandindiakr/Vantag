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

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

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
) -> Optional[WatchlistMatchEvent]:
    """
    Called by the pipeline when a face match is detected.

    Appends to the in-memory match list and flushes to disk.
    Returns the ``WatchlistMatchEvent`` model, or ``None`` if the entry_id
    is unknown.
    """
    entry = _entries.get(entry_id)
    if entry is None:
        logger.warning(
            "record_match: unknown entry_id=%s", entry_id
        )
        return None

    match = {
        "match_id": str(uuid.uuid4()),
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
async def list_entries() -> WatchlistListResponse:
    """Return all watchlist entries without face embeddings."""
    models = [_entry_to_model(e) for e in _entries.values()]
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
) -> WatchlistEntryResponse:
    """
    Add a new entry to the watchlist.

    The face image is saved to disk; the pipeline will pick it up and
    compute the embedding on its next watchlist reload cycle.
    """
    _ensure_dir()

    # Validate content type loosely.
    content_type = face_image.content_type or ""
    if not (content_type.startswith("image/") or face_image.filename.lower().endswith((".jpg", ".jpeg", ".png"))):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="face_image must be a JPEG or PNG image.",
        )

    entry_id = str(uuid.uuid4())
    ext = ".jpg" if "jpeg" in content_type or "jpg" in (face_image.filename or "") else ".png"
    img_filename = f"{entry_id}{ext}"
    img_path = _WATCHLIST_DIR / img_filename

    try:
        contents = await face_image.read()
        with img_path.open("wb") as fh:
            fh.write(contents)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save face image: {exc}",
        ) from exc

    now = datetime.now(tz=timezone.utc).isoformat()
    image_url = f"/api/snapshots/watchlist/{img_filename}"

    entry = {
        "entry_id": entry_id,
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
async def remove_entry(entry_id: str) -> None:
    """Remove an entry from the watchlist and delete the associated face image."""
    entry = _entries.get(entry_id)
    if entry is None:
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
) -> WatchlistMatchesResponse:
    """
    Return the most recent watchlist face-match events.

    Results are ordered newest-first.
    """
    recent = list(reversed(_matches[-limit:]))
    models: List[WatchlistMatchEvent] = []
    for raw in recent:
        try:
            models.append(_match_to_model(raw))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping malformed match entry | error=%s", exc)
            continue
    return WatchlistMatchesResponse(matches=models, total=len(_matches))
