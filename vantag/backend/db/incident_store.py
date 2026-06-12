"""
backend/db/incident_store.py
============================
SQLite-based local incident audit store.

* Completely separate from the PostgreSQL/SaaS tenant database.
* Uses stdlib sqlite3 — zero extra dependencies.
* Thread-safe: check_same_thread=False + a threading.Lock for writes.
* DB file: <project_root>/data/incidents.db  (created automatically).
* Incidents older than 30 days are deleted on startup cleanup.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Path resolution ──────────────────────────────────────────────────────────
# __file__ = vantag/backend/db/incident_store.py
# project root = vantag/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR     = _PROJECT_ROOT / "data"
_DB_PATH      = _DATA_DIR / "incidents.db"

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()


# ── Connection ────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    global _conn  # noqa: PLW0603
    if _conn is None:
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


# ── Public API ────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create the incidents table + index if they don't already exist."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = _get_conn()
    with _lock, conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS incidents (
                incident_id   TEXT PRIMARY KEY,
                store_id      TEXT NOT NULL,
                camera_id     TEXT,
                event_type    TEXT,
                severity      TEXT,
                description   TEXT,
                occurred_at   TEXT,
                snapshot_url  TEXT,
                acknowledged  INTEGER DEFAULT 0,
                is_demo       INTEGER DEFAULT 0,
                metadata      TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_store_time
                ON incidents(store_id, occurred_at DESC);
        """)
    logger.info("SQLite incident store initialised | path=%s", _DB_PATH)


def insert_incident(event: Dict[str, Any]) -> None:
    """
    Persist one incident.  Idempotent — duplicate incident_id is silently ignored.
    Accepts both canonical keys (type / timestamp) and legacy keys
    (event_type / occurred_at) so it works for both demo and real events.
    """
    incident_id = event.get("incident_id") or event.get("id")
    if not incident_id:
        return  # nothing to persist

    store_id    = event.get("store_id", "")
    camera_id   = event.get("camera_id", "")
    event_type  = event.get("type") or event.get("event_type", "")
    severity    = event.get("severity", "")
    description = event.get("description", "")
    occurred_at = event.get("timestamp") or event.get("occurred_at") or datetime.now(timezone.utc).isoformat()
    snapshot_url = event.get("snapshot_url")
    acknowledged = 1 if event.get("acknowledged") else 0
    is_demo      = 1 if event.get("is_demo") else 0
    metadata_raw = event.get("metadata", {})
    metadata_str = json.dumps(metadata_raw) if isinstance(metadata_raw, dict) else (metadata_raw or "{}")

    conn = _get_conn()
    with _lock, conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO incidents
                (incident_id, store_id, camera_id, event_type, severity,
                 description, occurred_at, snapshot_url, acknowledged,
                 is_demo, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (incident_id, store_id, camera_id, event_type, severity,
             description, occurred_at, snapshot_url, acknowledged,
             is_demo, metadata_str),
        )


def query_incidents(
    store_id: str,
    page: int = 1,
    limit: int = 50,
    event_type: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Return paginated incidents for a store, newest first.

    Returns:
        (items, total, pages)
    """
    conn   = _get_conn()
    offset = (page - 1) * limit

    base_where = "store_id = ?"
    params: list = [store_id]
    if event_type:
        base_where += " AND event_type = ?"
        params.append(event_type)

    total_row = conn.execute(
        f"SELECT COUNT(*) FROM incidents WHERE {base_where}", params
    ).fetchone()
    total = total_row[0] if total_row else 0
    pages = max(1, math.ceil(total / limit))

    rows = conn.execute(
        f"""
        SELECT incident_id, store_id, camera_id, event_type, severity,
               description, occurred_at, snapshot_url, acknowledged,
               is_demo, metadata, created_at
        FROM incidents
        WHERE {base_where}
        ORDER BY occurred_at DESC
        LIMIT ? OFFSET ?
        """,
        params + [limit, offset],
    ).fetchall()

    items: List[Dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        try:
            d["metadata"] = json.loads(d.get("metadata") or "{}")
        except (ValueError, TypeError):
            d["metadata"] = {}
        # Normalise to canonical keys used by stores_router
        d["type"]      = d.pop("event_type", "")
        d["timestamp"] = d.pop("occurred_at", "")
        d["is_demo"]   = bool(d.get("is_demo", 0))
        d["acknowledged"] = bool(d.get("acknowledged", 0))
        items.append(d)

    return items, total, pages


def cleanup_old(days: int = 30) -> int:
    """Delete incidents older than `days` days. Returns count deleted."""
    conn = _get_conn()
    with _lock, conn:
        cursor = conn.execute(
            "DELETE FROM incidents WHERE created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        deleted = cursor.rowcount
    if deleted:
        logger.info("Cleaned up %d incident(s) older than %d days", deleted, days)
    return deleted


def get_all_store_ids() -> List[str]:
    """Return distinct store_ids that have at least one incident in the DB."""
    conn = _get_conn()
    rows = conn.execute("SELECT DISTINCT store_id FROM incidents").fetchall()
    return [r[0] for r in rows]
