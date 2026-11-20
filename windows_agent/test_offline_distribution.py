import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_offline_build_writes_configuration_used_by_normal_launch(tmp_path):
    import build_exe
    from standalone_entry import local_mode_requested

    writer = getattr(build_exe, "write_offline_launch_config", None)
    assert callable(writer), "Offline builds need a normal-launch configuration, not only smoke-test flags"
    writer(tmp_path)
    assert local_mode_requested([], tmp_path)
    assert json.loads((tmp_path / "config.json").read_text()) == {"mode": "offline"}


def test_engineering_stage_contains_valid_test_licence_without_private_key(tmp_path):
    from build_offline_test import stage_test_package
    from agent.local.licensing import evaluate_entitlement

    source = tmp_path / "source"
    internal = source / "_internal"
    (internal / "offline-ui" / "assets").mkdir(parents=True)
    (internal / "offline-ui" / "offline.html").write_text("test fixture")
    (internal / "models").mkdir()
    (internal / "models" / "offline-manifest.json").write_text("{}")
    (internal / "offline_keys.json").write_text('{"production-key":"must-not-change"}')
    (source / "VantagAgent.exe").write_bytes(b"test executable fixture")
    destination = tmp_path / "stage"
    now = datetime(2026, 11, 16, 10, tzinfo=timezone.utc)
    metadata = stage_test_package(source, destination, now=now)
    envelope = json.loads((destination / "offline-entitlement.json").read_text())
    keys = json.loads((destination / "_internal" / "offline_keys.json").read_text())
    active = evaluate_entitlement(envelope, keys, "isolated-test-device", now)
    assert active.state == "active"
    assert active.claims["purpose"] == "engineering-test-not-for-resale"
    assert active.claims["expires_at"] == (now + timedelta(days=3)).timestamp()
    assert active.claims["grace_days"] == 7
    assert active.claims["camera_limit"] == 8
    assert "people_count" in active.claims["features"]
    assert "assistant" not in active.claims["features"]
    assert evaluate_entitlement(envelope, keys, "isolated-test-device", now + timedelta(days=4)).state == "grace"
    assert evaluate_entitlement(envelope, keys, "isolated-test-device", now + timedelta(days=11)).state == "expired"
    assert json.loads((destination / "config.json").read_text()) == {"mode": "offline"}
    assert json.loads((internal / "offline_keys.json").read_text()) == {"production-key": "must-not-change"}
    assert metadata["commercial_redistribution_approved"] is False
    assert metadata["disconnected_core_validated"] is False
    for path in destination.rglob("*"):
        if path.is_file():
            assert b"PRIVATE KEY" not in path.read_bytes()


def test_engineering_stage_refuses_customer_configuration(tmp_path):
    from build_offline_test import stage_test_package

    source = tmp_path / "source"
    source.mkdir()
    (source / "config.json").write_text('{"mode":"online","api_key":"customer-secret"}')
    with pytest.raises(ValueError, match="customer|configuration"):
        stage_test_package(source, tmp_path / "stage")
