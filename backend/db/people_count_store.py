"""
backend/db/people_count_store.py
================================
SQLite-backed live people-count store.

Why SQLite instead of the previous in-process dict:
* The backend runs uvicorn with ``--workers 2`` — each worker is a separate
  OS process with its own memory. Heartbeats (which record counts) can land
  on one worker while the dashboard GET lands on the other, so the in-memory
  store showed empty/stale data. A shared SQLite file (WAL mode) is visible
  to every worker process.
* Counts and the rolling hourly-peak history now survive backend restarts
  and redeploys (persistence requirement).

Tables
------
people_counts_latest : latest count per (tenant, camera) + unix timestamp
people_hourly_peaks  : per-tenant hourly peak of the summed live count

DB file: <project_root>/data/people_counts.db (created automatically).
Peak history older than 7 days is trimmed opportunistically on write.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_DB_PATH = _DATA_DIR / "people_counts.db"

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()

#: A camera's count is stale when no heartbeat updated it for this long.
STALE_SEC = 120.0


def _get_conn() -> sqlite3.Connection:
    global _conn  # noqa: PLW0603
    if _conn is None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=10.0)
        _conn.row_factory = sqlite3.Row
        # WAL: safe concurrent access from multiple uvicorn worker processes.
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


def init_db() -> None:
    conn = _get_conn()
    with _lock, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS people_counts_latest (
                tenant_id  TEXT NOT NULL,
                camera_id  TEXT NOT NULL,
                count      INTEGER NOT NULL DEFAULT 0,
                updated_ts REAL NOT NULL,
                PRIMARY KEY (tenant_id, camera_id)
            );
            CREATE TABLE IF NOT EXISTS people_hourly_peaks (
                tenant_id TEXT NOT NULL,
                hour_iso  TEXT NOT NULL,
                peak      INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (tenant_id, hour_iso)
            );
            """
        )
    logger.info("People-count store ready at %s", _DB_PATH)


def record_counts(tenant_id: str, counts: Dict[str, int]) -> None:
    """Upsert the latest per-camera counts and refresh this hour's peak."""
    if not counts:
        return
    now = time.time()
    conn = _get_conn()
    with _lock, conn:
        for cam_id, n in counts.items():
            try:
                n = max(int(n), 0)
            except (TypeError, ValueError):
                continue
            conn.execute(
                """
                INSERT INTO people_counts_latest (tenant_id, camera_id, count, updated_ts)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, camera_id)
                DO UPDATE SET count = excluded.count, updated_ts = excluded.updated_ts
                """,
                (tenant_id, str(cam_id), n, now),
            )
        # Hourly peak = sum of all live (non-stale) camera counts right now.
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) AS total FROM people_counts_latest"
            " WHERE tenant_id = ? AND updated_ts > ?",
            (tenant_id, now - STALE_SEC),
        ).fetchone()
        total = int(row["total"] or 0)
        hour_key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00Z")
        conn.execute(
            """
            INSERT INTO people_hourly_peaks (tenant_id, hour_iso, peak)
            VALUES (?, ?, ?)
            ON CONFLICT(tenant_id, hour_iso)
            DO UPDATE SET peak = MAX(peak, excluded.peak)
            """,
            (tenant_id, hour_key, total),
        )
        # Trim history older than 7 days.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
            "%Y-%m-%dT%H:00Z"
        )
        conn.execute(
            "DELETE FROM people_hourly_peaks WHERE tenant_id = ? AND hour_iso < ?",
            (tenant_id, cutoff),
        )


def get_latest_counts(tenant_id: str) -> List[Tuple[str, int, float]]:
    """Return [(camera_id, count, updated_ts), ...] for a tenant."""
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT camera_id, count, updated_ts FROM people_counts_latest"
            " WHERE tenant_id = ? ORDER BY camera_id",
            (tenant_id,),
        ).fetchall()
    return [(r["camera_id"], int(r["count"]), float(r["updated_ts"])) for r in rows]


def get_hourly_peaks(tenant_id: str, hours: int = 24) -> List[Tuple[str, int]]:
    """Return the most recent ``hours`` buckets as [(hour_iso, peak), ...] ascending."""
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT hour_iso, peak FROM people_hourly_peaks WHERE tenant_id = ?"
            " ORDER BY hour_iso DESC LIMIT ?",
            (tenant_id, hours),
        ).fetchall()
    return [(r["hour_iso"], int(r["peak"])) for r in reversed(rows)]
