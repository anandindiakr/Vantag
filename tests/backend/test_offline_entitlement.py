import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def test_trial_expiry_is_registration_based_not_a_new_trial():
    from backend.services.offline_entitlement import effective_expiry
    now = datetime.now(timezone.utc)
    tenant = SimpleNamespace(status="trial", trial_ends_at=None, created_at=now - timedelta(hours=1))
    assert effective_expiry(tenant, [], now) == tenant.created_at + timedelta(days=3)


def test_active_status_without_paid_dates_does_not_grant_permanent_offline_access():
    from backend.services.offline_entitlement import effective_expiry
    now = datetime.now(timezone.utc)
    tenant = SimpleNamespace(status="active", trial_ends_at=now - timedelta(days=1), created_at=now - timedelta(days=4))
    with pytest.raises(ValueError):
        effective_expiry(tenant, [], now)


def test_paid_and_admin_extension_choose_later_valid_end():
    from backend.services.offline_entitlement import effective_expiry
    now = datetime.now(timezone.utc)
    extension = now + timedelta(days=90)
    tenant = SimpleNamespace(status="active", trial_ends_at=extension, created_at=now - timedelta(days=200))
    subscription = SimpleNamespace(status="active", current_period_end=now + timedelta(days=10), cancel_at_period_end=False)
    assert effective_expiry(tenant, [subscription], now) == extension


@pytest.mark.parametrize("state", ["suspended", "cancelled", "expired"])
def test_suspended_accounts_do_not_get_new_offline_grants(state):
    from backend.services.offline_entitlement import effective_expiry
    now = datetime.now(timezone.utc)
    tenant = SimpleNamespace(status=state, trial_ends_at=now + timedelta(days=90), created_at=now)
    with pytest.raises(ValueError):
        effective_expiry(tenant, [], now)


def test_signer_uses_private_key_only_on_server(tmp_path, monkeypatch):
    from backend.services.offline_entitlement import sign_entitlement
    private = Ed25519PrivateKey.generate()
    keyfile = tmp_path / "private.pem"
    keyfile.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    monkeypatch.setenv("VANTAG_OFFLINE_SIGNING_KEY_FILE", str(keyfile))
    monkeypatch.setenv("VANTAG_OFFLINE_KEY_ID", "release-test")
    now = datetime.now(timezone.utc)
    claims = {"tenant_id": "tenant-a", "expires_at": (now + timedelta(days=3)).timestamp()}
    envelope = sign_entitlement(claims)
    private.public_key().verify(base64.urlsafe_b64decode(envelope["signature"]), envelope["payload"].encode("ascii"))
    parsed = json.loads(base64.urlsafe_b64decode(envelope["payload"]))
    assert parsed["key_id"] == "release-test"
    assert "PRIVATE KEY" not in json.dumps(envelope)


def test_offline_download_refuses_unqualified_artifact(tmp_path):
    import zipfile
    from backend.services.agent_package import build_offline_windows_package, PackageUnavailable
    artifact = tmp_path / "online.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("VantagAgent.exe", "test")
        archive.writestr("PACKAGE_VERSION.txt", "1.11.5")
    with pytest.raises(PackageUnavailable, match="qualified"):
        build_offline_windows_package(artifact, {}, "1.11.5", tmp_path)
    assert [path.name for path in tmp_path.iterdir()] == ["online.zip"]
