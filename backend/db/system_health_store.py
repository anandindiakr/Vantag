"""
backend/db/system_health_store.py
=================================
SQLite-backed store for backend fault records and Edge Agent model status.

Why SQLite and not an in-process dict
-------------------------------------
The backend runs uvicorn with ``--workers 2`` — each worker is a separate OS
process with its own memory. An Edge Agent heartbeat (which reports detector
model status) can land on worker A while the admin panel GET lands on worker
B, and an AI-Assistant failure can be raised on either. A module-level dict
would therefore show empty/stale data at random — this is exactly the bug that
previously made the People Count dashboard always read 0. A shared SQLite file
in WAL mode is visible to every worker process and survives restarts, so the
admin panel reports the real state rather than "whatever this worker happened
to see".

Tables
------
system_faults      : one row per component, with occurrence count + last alert
agent_model_status : one row per (tenant, agent) — which detector is really
                     running, as verified from the ONNX graph on the agent

DB file: <project_root>/data/system_health.db (created automatically).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_DB_PATH = _DATA_DIR / "system_health.db"

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()

#: An agent's reported model status is stale after this long without heartbeat.
AGENT_STALE_SEC = 180.0


def _get_conn() -> sqlite3.Connection:
    global _conn  # noqa: PLW0603
    if _conn is None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=10.0)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


def init_db() -> None:
    conn = _get_conn()
    with _lock, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS system_faults (
                component     TEXT PRIMARY KEY,
                summary       TEXT NOT NULL DEFAULT '',
                detail        TEXT NOT NULL DEFAULT '',
                tenant_id     TEXT,
                occurrences   INTEGER NOT NULL DEFAULT 0,
                first_seen_ts REAL NOT NULL,
                last_seen_ts  REAL NOT NULL,
                last_alert_ts REAL,
                resolved_ts   REAL
            );
            CREATE TABLE IF NOT EXISTS agent_model_status (
                tenant_id     TEXT NOT NULL,
                agent_id      TEXT NOT NULL,
                agent_version TEXT NOT NULL DEFAULT '',
                status_json   TEXT NOT NULL DEFAULT '{}',
                updated_ts    REAL NOT NULL,
                PRIMARY KEY (tenant_id, agent_id)
            );
            """
        )
    logger.info("System-health store ready at %s", _DB_PATH)


# ── Faults ─────────────────────────────────────────────────────────────────

def record_fault(
    component: str,
    summary: str,
    detail: str = "",
    tenant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Upsert a fault record and return it (including whether to alert).

    Returns the row as a dict plus ``occurrences``; the caller decides whether
    to email based on ``last_alert_ts``.
    """
    now = time.time()
    conn = _get_conn()
    with _lock, conn:
        conn.execute(
            """
            INSERT INTO system_faults (
                component, summary, detail, tenant_id, occurrences,
                first_seen_ts, last_seen_ts, last_alert_ts, resolved_ts
            ) VALUES (?, ?, ?, ?, 1, ?, ?, NULL, NULL)
            ON CONFLICT(component) DO UPDATE SET
                summary     = excluded.summary,
                detail      = excluded.detail,
                tenant_id   = excluded.tenant_id,
                occurrences = system_faults.occurrences + 1,
                last_seen_ts = excluded.last_seen_ts,
                resolved_ts = NULL
            """,
            (component, summary, detail, tenant_id, now, now),
        )
        row = conn.execute(
            "SELECT * FROM system_faults WHERE component = ?", (component,)
        ).fetchone()
    return dict(row) if row else {}


def mark_alerted(component: str) -> None:
    conn = _get_conn()
    with _lock, conn:
        conn.execute(
            "UPDATE system_faults SET last_alert_ts = ? WHERE component = ?",
            (time.time(), component),
        )


def resolve_fault(component: str) -> None:
    conn = _get_conn()
    with _lock, conn:
        conn.execute(
            "UPDATE system_faults SET resolved_ts = ? "
            "WHERE component = ? AND resolved_ts IS NULL",
            (time.time(), component),
        )


def list_faults() -> list[dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM system_faults ORDER BY last_seen_ts DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Agent model status ─────────────────────────────────────────────────────

def record_agent_model_status(
    tenant_id: str,
    agent_id: str,
    agent_version: str,
    status: dict[str, Any],
) -> None:
    now = time.time()
    conn = _get_conn()
    with _lock, conn:
        conn.execute(
            """
            INSERT INTO agent_model_status (
                tenant_id, agent_id, agent_version, status_json, updated_ts
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, agent_id) DO UPDATE SET
                agent_version = excluded.agent_version,
                status_json   = excluded.status_json,
                updated_ts    = excluded.updated_ts
            """,
            (tenant_id, agent_id, agent_version, json.dumps(status), now),
        )


def list_agent_model_status(tenant_id: Optional[str] = None) -> list[dict[str, Any]]:
    conn = _get_conn()
    sql = "SELECT * FROM agent_model_status"
    params: tuple = ()
    if tenant_id:
        sql += " WHERE tenant_id = ?"
        params = (tenant_id,)
    sql += " ORDER BY updated_ts DESC"
    with _lock:
        rows = conn.execute(sql, params).fetchall()

    now = time.time()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["status"] = json.loads(d.pop("status_json") or "{}")
        except Exception:  # noqa: BLE001 — never fail the panel on bad JSON
            d["status"] = {}
        age = now - float(d.get("updated_ts") or 0)
        d["age_seconds"] = round(age, 1)
        # Stale means "this agent stopped heartbeating" — we must NOT present
        # its last-known model status as current, or the panel would claim
        # YOLO26 is active on a machine that is switched off.
        d["stale"] = age > AGENT_STALE_SEC
        out.append(d)
    return out
