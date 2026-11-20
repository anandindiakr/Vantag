import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent))


def signed_grant(private_key, now, **overrides):
    claims = {
        "version": 1, "key_id": "test", "issuer": "retail-vantag.com",
        "tenant_id": "tenant-a", "entitlement_id": "grant-a", "revision": 1,
        "issued_at": now.timestamp(), "not_before": (now - timedelta(minutes=1)).timestamp(),
        "expires_at": (now + timedelta(days=3)).timestamp(), "grace_days": 7,
        "camera_limit": 3, "features": ["people_count", "inventory_movement"],
        "device_id": None,
    }
    claims.update(overrides)
    payload = base64.urlsafe_b64encode(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()).decode()
    return {"payload": payload, "signature": base64.urlsafe_b64encode(private_key.sign(payload.encode("ascii"))).decode()}


@pytest.fixture
def keys():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, {"test": public}


def test_offline_license_active_grace_expired_without_network(keys):
    from agent.local.licensing import evaluate_entitlement
    private, public = keys
    now = datetime.now(timezone.utc)
    grant = signed_grant(private, now)
    assert evaluate_entitlement(grant, public, "device-a", now).state == "active"
    assert evaluate_entitlement(grant, public, "device-a", now + timedelta(days=4)).state == "grace"
    result = evaluate_entitlement(grant, public, "device-a", now + timedelta(days=11))
    assert result.state == "expired" and not result.can_process


@pytest.mark.parametrize("change", ["signature", "tenant", "device", "rollback", "grace"])
def test_offline_license_rejects_invalid_grants(keys, change):
    from agent.local.licensing import evaluate_entitlement
    private, public = keys
    now = datetime.now(timezone.utc)
    overrides = {"device_id": "other"} if change == "device" else {}
    if change == "grace":
        overrides["grace_days"] = 90
    grant = signed_grant(private, now, **overrides)
    if change == "signature":
        grant["payload"] = grant["payload"][:-4] + "AAAA"
    result = evaluate_entitlement(
        grant, public, "device-a", now,
        expected_tenant="other" if change == "tenant" else "tenant-a",
        last_seen=(now + timedelta(hours=1)).timestamp() if change == "rollback" else 0,
    )
    assert result.state == "invalid" and not result.can_process


def test_store_keeps_incidents_across_restart_and_deduplicates(tmp_path):
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    event = {"event_id": "event-a", "camera_id": "cam-a", "event_type": "inventory_movement", "confidence": 0.8}
    assert store.record_event(event)
    assert not store.record_event(event)
    assert len(SiteStore(tmp_path).events()) == 1
    assert SiteStore(tmp_path).events()[0]["verification_state"] == "not_verified_offline"


def test_local_owner_password_is_hashed_and_setup_is_single_use(tmp_path):
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    store.create_owner("owner", "a-long-unique-password")
    assert store.authenticate("owner", "a-long-unique-password")
    assert not store.authenticate("owner", "wrong-password")
    with pytest.raises(ValueError):
        store.create_owner("intruder", "another-long-password")
    assert b"a-long-unique-password" not in (tmp_path / "site.sqlite3").read_bytes()


def test_store_counts_use_persisted_deltas_not_restart_totals(tmp_path):
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    store.record_count("cam-a", "2026-11-16", 2, 3, "run-a")
    store.record_count("cam-a", "2026-11-16", 1, 4, "run-a")
    store.record_count("cam-a", "2026-11-16", 1, 1, "run-b")
    summary = SiteStore(tmp_path).counts("2026-11-16")
    assert summary[0]["entries"] == 5
    assert summary[0]["people_visible"] == 1


def test_store_protects_camera_credentials_and_hides_them_in_listing(tmp_path):
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    store.save_camera({"id": "cam-a", "name": "Entrance", "rtsp_url": "rtsp://admin:Secret%23@192.168.1.102:554/Streaming/Channels/101", "detections": {"people_count": True}})
    assert "Secret" not in json.dumps(store.cameras())
    assert "Secret" not in (tmp_path / "site.sqlite3").read_bytes().decode("latin1")
    assert "Secret%23" in store.cameras(include_secrets=True)[0]["rtsp_url"]


def test_licence_import_is_atomic_and_rejects_revision_rollback(tmp_path, keys):
    from agent.local.store import SiteStore
    from agent.local.licensing import LicenceManager
    private, public = keys
    now = datetime.now(timezone.utc)
    manager = LicenceManager(SiteStore(tmp_path), public, "device-a")
    manager.install(signed_grant(private, now, revision=2), now)
    with pytest.raises(ValueError):
        manager.install(signed_grant(private, now, revision=1), now)
    assert manager.status(now).claims["revision"] == 2


def test_local_api_requires_login_and_rejects_cross_origin(tmp_path):
    from fastapi.testclient import TestClient
    from agent.local.server import create_app
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    with TestClient(create_app(store, None, None), base_url="http://127.0.0.1") as client:
        assert client.get("/api/cameras").status_code == 401
        assert client.post("/api/setup", json={"username": "owner", "password": "a-long-unique-password"}, headers={"Origin": "https://evil.example"}).status_code == 403
        response = client.post("/api/setup", json={"username": "owner", "password": "a-long-unique-password"})
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert client.get("/api/cameras").status_code == 200
        assert client.post("/api/cameras", json={"name": "blocked"}).status_code == 403
        assert client.get("/api/events").status_code == 200
        assert client.get("/api/status", headers={"Host": "evil.example"}).status_code == 400


def test_offline_client_delivers_evidence_without_http(tmp_path, monkeypatch):
    import requests
    from agent.local.store import SiteStore
    from agent.local.runtime import LocalSink
    monkeypatch.setattr(requests.Session, "request", lambda *args, **kwargs: pytest.fail("Offline processing attempted HTTP"))
    store = SiteStore(tmp_path)
    sink = LocalSink(store)
    assert sink.post_event({"event_id": "one", "camera_id": "cam-a", "event_type": "shoplifting", "snapshot_b64": base64.b64encode(b"evidence").decode()})
    assert len(store.events()) == 1
    assert sink.push_frame("cam-a", base64.b64encode(b"preview").decode())
    assert sink.frame("cam-a")[0] == b"preview"
