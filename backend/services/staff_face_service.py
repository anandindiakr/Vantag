"""
backend/services/staff_face_service.py
======================================
Bridges the Staff Faces / Watchlist enrollment (images uploaded via
``watchlist_router``) to live face matching for edge detection events.

Why this exists
---------------
``watchlist_router`` stores reference face images on disk at
``snapshots/watchlist/{entry_id}.jpg`` plus metadata in
``watchlist_meta.json`` — but nothing ever computed embeddings from those
images or compared them against live frames. This module closes that gap:

* Lazily initialises one shared insightface ``FaceAnalysis`` model
  (ArcFace embeddings, CPU provider — same backend as
  ``backend/analyzers/facial_recognition.py``).
* Loads every enrolled watchlist image, extracts the embedding of the
  largest face, and caches it in memory.
* Auto-reloads whenever ``watchlist_meta.json`` changes on disk (mtime
  check), so newly enrolled staff take effect without a restart.
* ``match_face_b64()`` takes a base64 JPEG (person crop or snapshot sent
  by the edge agent), finds the best face, and returns the closest
  watchlist entry above the similarity threshold.

All functions are synchronous and CPU-bound — callers inside async
routes must wrap them in ``asyncio.to_thread``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("vantag.staff_face")

# Same storage layout as backend/api/watchlist_router.py
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_WATCHLIST_DIR: Path = _BASE_DIR / "snapshots" / "watchlist"
_META_FILE: Path = _WATCHLIST_DIR / "watchlist_meta.json"

# ArcFace cosine similarity: same-person pairs are typically >= 0.4;
# different-person pairs rarely exceed 0.3. 0.40 is a safe default that
# can be tuned per-deployment via env.
_MATCH_THRESHOLD = float(os.environ.get("VANTAG_STAFF_MATCH_THRESHOLD", "0.40"))

_lock = threading.Lock()
_insight_app = None            # shared FaceAnalysis instance (or False if unavailable)
_embeddings: List[Tuple[str, np.ndarray]] = []   # [(entry_id, unit-norm embedding)]
_entry_meta: Dict[str, dict] = {}                # entry_id -> {name, alert_level}
_meta_mtime: float = -1.0


def _get_app():
    """Lazily initialise the shared insightface FaceAnalysis model."""
    global _insight_app  # noqa: PLW0603
    if _insight_app is not None:
        return _insight_app or None
    try:
        from insightface.app import FaceAnalysis  # type: ignore[import]

        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=0, det_size=(640, 640))
        _insight_app = app
        logger.info("staff_face_service: insightface ArcFace initialised")
        return app
    except Exception as exc:  # noqa: BLE001
        _insight_app = False
        logger.warning(
            "staff_face_service: insightface unavailable (%s) — "
            "staff face matching disabled", exc,
        )
        return None


def _largest_face_embedding(app, img_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Return the unit-normalised embedding of the largest detected face."""
    try:
        faces = app.get(img_bgr)
    except Exception as exc:  # noqa: BLE001
        logger.debug("staff_face_service: detect error: %s", exc)
        return None
    if not faces:
        return None
    best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    emb = np.asarray(best.embedding, dtype=np.float32)
    norm = float(np.linalg.norm(emb))
    if norm == 0.0:
        return None
    return emb / norm


def _reload_if_stale() -> None:
    """Recompute embeddings when watchlist_meta.json changed on disk."""
    global _embeddings, _entry_meta, _meta_mtime  # noqa: PLW0603
    try:
        mtime = _META_FILE.stat().st_mtime if _META_FILE.exists() else 0.0
    except OSError:
        mtime = 0.0
    if mtime == _meta_mtime:
        return

    app = _get_app()
    if app is None:
        _meta_mtime = mtime
        return

    import cv2  # local import — heavy module

    entries: Dict[str, dict] = {}
    if _META_FILE.exists():
        try:
            with _META_FILE.open("r", encoding="utf-8") as fh:
                entries = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("staff_face_service: cannot read meta file: %s", exc)
            entries = {}

    new_embeddings: List[Tuple[str, np.ndarray]] = []
    new_meta: Dict[str, dict] = {}
    for entry_id, entry in entries.items():
        img_path = Path(entry.get("image_path") or "")
        if not img_path.exists():
            # Container path may differ from host path recorded at upload
            # time — fall back to tenant-scoped canonical storage first.
            tenant_id = str(entry.get("tenant_id") or "")
            search_dirs = [_WATCHLIST_DIR / tenant_id] if tenant_id else []
            # Legacy entries were stored directly under watchlist/. They are
            # retained for migration, but are not eligible for tenant-scoped
            # live matching unless they have an owner.
            if not tenant_id:
                search_dirs.append(_WATCHLIST_DIR)
            for directory in search_dirs:
                for ext in (".jpg", ".png", ".jpeg"):
                    candidate = directory / f"{entry_id}{ext}"
                    if candidate.exists():
                        img_path = candidate
                        break
                if img_path.exists():
                    break
        if not img_path.exists():
            logger.warning(
                "staff_face_service: image missing for entry %s (%s)",
                entry_id, entry.get("name"),
            )
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            logger.warning("staff_face_service: unreadable image %s", img_path)
            continue
        emb = _largest_face_embedding(app, img)
        if emb is None:
            logger.warning(
                "staff_face_service: no face found in enrolment image for "
                "entry %s (%s) — re-upload a clear frontal photo",
                entry_id, entry.get("name"),
            )
            continue
        new_embeddings.append((entry_id, emb))
        new_meta[entry_id] = {
            "tenant_id": str(entry.get("tenant_id") or ""),
            "name": entry.get("name") or "Unknown",
            "alert_level": (entry.get("alert_level") or "medium").lower(),
        }

    _embeddings = new_embeddings
    _entry_meta = new_meta
    _meta_mtime = mtime
    logger.info(
        "staff_face_service: loaded %d/%d watchlist face embedding(s)",
        len(new_embeddings), len(entries),
    )


def match_face_b64(image_b64: str, tenant_id: Optional[str] = None) -> Optional[dict]:
    """
    Match the largest face in a base64 JPEG against enrolled watchlist faces.
    When ``tenant_id`` is supplied, only that tenant's enrollments are
    considered; legacy ownerless records are excluded.

    Returns ``{"entry_id", "name", "alert_level", "similarity"}`` for the
    best match at or above the threshold, else ``None``.
    Synchronous and CPU-bound — call via ``asyncio.to_thread`` from async code.
    """
    with _lock:
        _reload_if_stale()
        meta = dict(_entry_meta)
        requested_tenant = str(tenant_id) if tenant_id is not None else None
        embeddings = [
            (entry_id, embedding)
            for entry_id, embedding in _embeddings
            if requested_tenant is None
            or meta.get(entry_id, {}).get("tenant_id") == requested_tenant
        ]
    if not embeddings:
        return None
    app = _get_app()
    if app is None:
        return None

    import cv2  # local import — heavy module

    try:
        raw = base64.b64decode(image_b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:  # noqa: BLE001
        return None
    if img is None or img.size == 0:
        return None

    emb = _largest_face_embedding(app, img)
    if emb is None:
        return None

    best_id: Optional[str] = None
    best_sim = 0.0
    for entry_id, ref in embeddings:
        sim = float(np.dot(emb, ref))
        if sim > best_sim:
            best_sim = sim
            best_id = entry_id
    if best_id is None or best_sim < _MATCH_THRESHOLD:
        return None
    info = meta.get(best_id, {})
    return {
        "entry_id": best_id,
        "name": info.get("name", "Unknown"),
        "alert_level": info.get("alert_level", "medium"),
        "similarity": round(best_sim, 4),
    }


def is_available() -> bool:
    """True when insightface is importable (matching can actually run)."""
    return _get_app() is not None
