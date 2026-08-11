"""Durable, bounded outbox for edge incident delivery.

Incidents are retained locally until the cloud acknowledges them. Preview frames
are intentionally not queued: they are disposable, while an incident is not.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger("vantag.outbox")


class IncidentOutbox:
    """SQLite-backed retry queue safe for camera worker threads."""

    def __init__(self, path: Path, max_items: int = 500) -> None:
        self.path = Path(path)
        self.max_items = max(50, int(max_items))
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS incident_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    dedupe_key TEXT,
                    created_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL
                )"""
            )
            # Existing installations may have the pre-dedupe schema. SQLite
            # migrations are intentionally local and idempotent because the
            # agent must be able to upgrade without losing queued incidents.
            try:
                conn.execute("ALTER TABLE incident_outbox ADD COLUMN dedupe_key TEXT")
            except sqlite3.OperationalError:
                pass
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incident_outbox_due "
                "ON incident_outbox(next_attempt_at, id)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_incident_outbox_dedupe "
                "ON incident_outbox(dedupe_key) WHERE dedupe_key IS NOT NULL"
            )

    def enqueue(self, payload: dict) -> None:
        """Persist an incident and evict the oldest rows over the hard cap."""
        encoded = json.dumps(payload, separators=(",", ":"), default=str)
        # The edge event's stable id makes retries idempotent locally. If a
        # request timed out after the server accepted it, the same incident is
        # not added repeatedly on every camera retry.
        event_id = payload.get("incident_id") or payload.get("event_id")
        dedupe_key = str(event_id) if event_id else hashlib.sha256(encoded.encode()).hexdigest()
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO incident_outbox "
                "(payload, dedupe_key, created_at, next_attempt_at) VALUES (?, ?, ?, ?)",
                (encoded, dedupe_key, now, now),
            )
            conn.execute(
                """DELETE FROM incident_outbox WHERE id IN (
                    SELECT id FROM incident_outbox ORDER BY id DESC LIMIT -1 OFFSET ?
                )""",
                (self.max_items,),
            )

    def flush(self, sender: Callable[[dict], bool], limit: int = 20) -> int:
        """Send due incidents; delete only after a successful acknowledgement."""
        sent = 0
        now = time.time()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, payload, attempts FROM incident_outbox "
                "WHERE next_attempt_at <= ? ORDER BY id LIMIT ?",
                (now, max(1, min(int(limit), 100))),
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row["payload"])
                    ok = bool(sender(payload))
                except Exception as exc:  # noqa: BLE001
                    log.debug("outbox send failed: %s", exc)
                    ok = False
                if ok:
                    conn.execute("DELETE FROM incident_outbox WHERE id = ?", (row["id"],))
                    sent += 1
                    continue
                attempts = int(row["attempts"]) + 1
                # Bounded exponential backoff: 5s, 10s ... max 10 minutes.
                delay = min(600.0, 5.0 * (2 ** min(attempts - 1, 7)))
                conn.execute(
                    "UPDATE incident_outbox SET attempts = ?, next_attempt_at = ? WHERE id = ?",
                    (attempts, time.time() + delay, row["id"]),
                )
        return sent

    def pending_count(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM incident_outbox").fetchone()
            return int(row["n"] if row else 0)
