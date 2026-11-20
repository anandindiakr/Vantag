import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_schedule_is_site_local_and_theft_remains_on():
    from agent.local.policy import feature_enabled
    camera = {"enabled": True, "detections": {"shoplifting": True, "people_count": True}, "detection_schedule": {"enabled": True, "start": "22:00", "end": "06:00"}}
    claims = {"features": ["shoplifting", "people_count"]}
    evening = datetime(2026, 11, 16, 16, tzinfo=timezone.utc)
    assert feature_enabled(camera, "people_count", claims, "Asia/Jakarta", evening)
    daytime = evening + timedelta(hours=12)
    assert not feature_enabled(camera, "people_count", claims, "Asia/Jakarta", daytime)
    assert feature_enabled(camera, "shoplifting", claims, "Asia/Jakarta", daytime)
    camera["enabled"] = False
    assert not feature_enabled(camera, "shoplifting", claims, "Asia/Jakarta", daytime)


def test_silent_detector_failure_is_not_a_measured_zero():
    from agent.local.detector import VerifiedDetector
    broken = SimpleNamespace(device="cpu", status={"inference_count": 3}, detect=lambda *args, **kwargs: [])
    detector = VerifiedDetector(broken, lambda: pytest.fail("CPU must not silently retry forever"))
    with pytest.raises(RuntimeError, match="not a measured zero"):
        detector.detect(None)
    assert detector.status["runtime_error"]


def test_gpu_loss_requires_successful_cpu_inference():
    from agent.local.detector import VerifiedDetector
    broken = SimpleNamespace(device="cuda", status={"inference_count": 3}, detect=lambda *args, **kwargs: [])
    cpu = SimpleNamespace(device="cpu", status={"is_preferred": True, "inference_count": 0})

    def infer(*args, **kwargs):
        cpu.status["inference_count"] += 1
        return ["real-result"]

    cpu.detect = infer
    detector = VerifiedDetector(broken, lambda: cpu)
    assert detector.detect(None) == ["real-result"]
    assert detector.device == "cpu"
    assert detector.status["runtime_fallback"]
    assert not detector.status["runtime_error"]


def test_stopped_generation_cannot_deliver_late_events(tmp_path):
    from agent.local.runtime import LocalSink
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    sink = LocalSink(store)
    sink.enabled = False
    assert not sink.post_event({"event_type": "shoplifting"})
    assert not sink.push_frame("cam", base64.b64encode(b"frame").decode())
    assert store.events() == []


def test_count_sample_timestamp_survives_persistence(tmp_path):
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    store.record_count("cam", "2026-11-16", 1, 2, "run", updated_at=123)
    assert store.counts("2026-11-16")[0]["updated_at"] == 123


def test_expired_api_retains_evidence_but_denies_frames_and_processing(tmp_path):
    from fastapi.testclient import TestClient
    from agent.local.licensing import EntitlementStatus
    from agent.local.server import create_app
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    image = base64.b64encode(b"saved-evidence").decode()
    store.record_event({"event_id": "one", "snapshot_b64": image})
    licence = SimpleNamespace(status=lambda: EntitlementStatus("expired"))
    with TestClient(create_app(store, licence, None), base_url="http://127.0.0.1") as client:
        client.post("/api/setup", json={"username": "owner", "password": "a-long-unique-password"})
        events = client.get("/api/events").json()
        assert client.get(events[0]["evidence"]["snapshot_b64"]).content == b"saved-evidence"
        assert client.get("/api/frame/cam").status_code == 403
        assert client.post("/api/cameras", json={"name": "blocked"}).status_code == 403
        assert client.get("/api/counts.csv?day=2026-11-16").status_code == 200
        assert client.get("/api/counts?day=not-a-date").status_code == 400


def test_backup_restore_preserves_current_licence_and_owner(tmp_path):
    from agent.local.storage import export_backup, restore_backup
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path / "site")
    store.create_owner("owner", "a-long-unique-password")
    store.set("entitlement", {"revision": 1, "last_seen": 10})
    camera_id = store.save_camera({"name": "Original", "rtsp_url": "rtsp://user:pass%23@192.168.1.102:554/Streaming/Channels/101"})
    store.record_event({"event_id": "saved", "snapshot_b64": base64.b64encode(b"picture").decode()})
    store.record_count(camera_id, "2026-11-16", 1, 2, "run")
    backup = tmp_path / "backup.zip"
    export_backup(store, backup)
    store.set("entitlement", {"revision": 2, "last_seen": 20})
    store.delete_camera(camera_id)
    restore_backup(store, backup)
    assert store.cameras()[0]["name"] == "Original"
    assert store.get("entitlement") == {"revision": 2, "last_seen": 20}
    assert store.authenticate("owner", "a-long-unique-password")
    assert store.counts("2026-11-16")[0]["entries"] == 2
    assert store.events()[0]["evidence"]["snapshot_b64"]


def test_backup_rejects_path_traversal(tmp_path):
    import zipfile
    from agent.local.storage import restore_backup
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path / "site")
    backup = tmp_path / "bad.zip"
    with zipfile.ZipFile(backup, "w") as archive:
        archive.writestr("site.sqlite3", "bad")
        archive.writestr("manifest.json", "{}")
        archive.writestr("../escaped", "bad")
    with pytest.raises(ValueError, match="Unexpected file"):
        restore_backup(store, backup)
    assert not (tmp_path / "escaped").exists()


def test_quota_blocks_new_records_without_removing_history(tmp_path):
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    store.record_event({"event_id": "retained"})
    store.set("storage", {"quota_mb": 0})
    with pytest.raises(ValueError, match="storage limit"):
        store.record_event({"event_id": "blocked"})
    assert [event["event_id"] for event in store.events()] == ["retained"]


def test_camera_api_preserves_encoded_password_and_rejects_bad_schedule(tmp_path):
    from fastapi.testclient import TestClient
    from agent.local.licensing import EntitlementStatus
    from agent.local.server import create_app
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    licence = SimpleNamespace(status=lambda: EntitlementStatus("active", claims={"camera_limit": 3, "features": ["people_count"]}))
    with TestClient(create_app(store, licence, None), base_url="http://127.0.0.1") as client:
        client.post("/api/setup", json={"username": "owner", "password": "a-long-unique-password"})
        camera = {"name": "Channel 1", "rtsp_url": "rtsp://viewer:pass%23@192.168.1.102:554/Streaming/Channels/101", "detections": {"people_count": True}}
        response = client.post("/api/cameras", json=camera)
        assert response.status_code == 200
        assert "%23" in store.cameras(include_secrets=True)[0]["rtsp_url"]
        camera["detection_schedule"] = {"enabled": True, "start": "25:99"}
        assert client.post("/api/cameras", json=camera).status_code == 422
        assert "pass" not in json.dumps(client.get("/api/cameras").json())
