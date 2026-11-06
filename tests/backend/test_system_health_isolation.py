"""Regression tests for tenant/agent-scoped system-health faults."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db import system_health_store as health_store


@pytest.fixture
def isolated_health_store(tmp_path: Path):
    previous_path = health_store._DB_PATH
    previous_conn = health_store._conn
    health_store._DB_PATH = tmp_path / "system-health.db"
    health_store._conn = None
    health_store.init_db()
    try:
        yield health_store
    finally:
        if health_store._conn is not None:
            health_store._conn.close()
        health_store._DB_PATH = previous_path
        health_store._conn = previous_conn


def test_recovering_one_agent_does_not_clear_another(isolated_health_store):
    store = isolated_health_store
    store.record_fault("model_fallback", "agent A fallback", tenant_id="tenant-a", entity_id="agent-a")
    store.record_fault("model_fallback", "agent B fallback", tenant_id="tenant-a", entity_id="agent-b")

    store.resolve_fault("model_fallback", "tenant-a", "agent-a")

    faults = {row["component"]: row for row in store.list_faults()}
    assert faults["model_fallback:tenant-a:agent-a"]["resolved_ts"] is not None
    assert faults["model_fallback:tenant-a:agent-b"]["resolved_ts"] is None


def test_legacy_fault_is_retired_only_by_its_own_agent(isolated_health_store):
    store = isolated_health_store
    store.record_fault(
        "product_count_failed",
        "legacy agent A failure",
        detail="agent_id=agent-a\nagent_version=1.11.2",
        tenant_id="tenant-a",
    )

    store.resolve_fault("product_count_failed", "tenant-a", "agent-b")
    legacy = next(row for row in store.list_faults() if row["component"] == "product_count_failed")
    assert legacy["resolved_ts"] is None

    store.resolve_fault("product_count_failed", "tenant-a", "agent-a")
    legacy = next(row for row in store.list_faults() if row["component"] == "product_count_failed")
    assert legacy["resolved_ts"] is not None
