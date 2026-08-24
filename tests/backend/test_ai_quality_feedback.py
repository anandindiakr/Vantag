"""Regression tests for the reviewed-AI feedback and quality metrics store."""
from __future__ import annotations

from pathlib import Path

from backend.db import system_health_store as health_store


def test_ai_quality_is_tenant_scoped(tmp_path: Path):
    previous_path = health_store._DB_PATH
    previous_conn = health_store._conn
    try:
        health_store._DB_PATH = tmp_path / "system-health.db"
        health_store._conn = None
        health_store.init_db()

        health_store.record_ai_feedback("tenant-a", "event-a", "confirmed")
        health_store.record_ai_feedback("tenant-a", "event-b", "false_positive")
        health_store.record_ai_feedback("tenant-b", "event-c", "confirmed")

        tenant_a = health_store.ai_quality_summary("tenant-a")
        tenant_b = health_store.ai_quality_summary("tenant-b")

        assert tenant_a["reviewed"] == 2
        assert tenant_a["confirmed"] == 1
        assert tenant_a["false_positive"] == 1
        assert tenant_a["false_positive_rate"] == 0.5
        assert tenant_b["reviewed"] == 1
        assert tenant_b["false_positive"] == 0
    finally:
        if health_store._conn is not None:
            health_store._conn.close()
        health_store._DB_PATH = previous_path
        health_store._conn = previous_conn


def test_feedback_upsert_relabels_an_event(tmp_path: Path):
    previous_path = health_store._DB_PATH
    previous_conn = health_store._conn
    try:
        health_store._DB_PATH = tmp_path / "system-health.db"
        health_store._conn = None
        health_store.init_db()

        health_store.record_ai_feedback("tenant-a", "event-a", "uncertain", "review later")
        health_store.record_ai_feedback("tenant-a", "event-a", "confirmed", "verified")

        summary = health_store.ai_quality_summary("tenant-a")
        assert summary["reviewed"] == 1
        assert summary["confirmed"] == 1
        assert summary["uncertain"] == 0
    finally:
        if health_store._conn is not None:
            health_store._conn.close()
        health_store._DB_PATH = previous_path
        health_store._conn = previous_conn
