from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.parametrize('admin', [{}, {'role': 'owner'}, {'role': 'admin', 'is_super_admin': False}])
def test_only_superadmin_can_build_demo_claims(admin):
    from backend.services.offline_entitlement import demo_claims
    with pytest.raises(ValueError, match='super'):
        demo_claims(admin, 'tenant-a', 'retail-vantag.com', 'a' * 64, 'internal_demo', None, 8, 1)


def test_internal_demo_and_customer_evaluation_have_distinct_dates():
    from backend.services.offline_entitlement import demo_claims
    admin = {'user_id': 'admin-a', 'is_super_admin': True}
    permanent = demo_claims(admin, 'tenant-a', 'retail-vantag.com', 'a' * 64, 'internal_demo', None, 8, 1)
    assert permanent['expires_at'] is None
    assert permanent['device_id'] == 'a' * 64
    assert permanent['issuing_role'] == 'super_admin'
    timed = demo_claims(admin, 'tenant-a', 'retail-vantag.com', 'a' * 64, 'evaluation', 30, 8, 2)
    assert timed['expires_at'] == timed['issued_at'] + timedelta(days=30).total_seconds()
    assert timed['grace_days'] == 7


@pytest.mark.parametrize('kind,days,device', [('internal_demo', None, ''), ('evaluation', None, 'a' * 64), ('evaluation', 0, 'a' * 64), ('evaluation', 366, 'a' * 64), ('customer', None, 'a' * 64)])
def test_demo_claims_reject_invalid_policy(kind, days, device):
    from backend.services.offline_entitlement import demo_claims
    with pytest.raises(ValueError):
        demo_claims({'user_id': 'admin-a', 'is_super_admin': True}, 'tenant-a', 'retail-vantag.com', device, kind, days, 8, 1)


@pytest.mark.asyncio
async def test_demo_endpoint_auth_signature_and_audit(monkeypatch, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from backend.api.offline_router import router
    from backend.db.database import get_session
    from backend.db.models import site, partner
    from backend.middleware.tenant_middleware import get_current_user_id
    import base64

    key = Ed25519PrivateKey.generate()
    private = tmp_path / 'private.pem'
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    monkeypatch.setenv('VANTAG_OFFLINE_SIGNING_KEY_FILE', str(private))
    monkeypatch.setenv('VANTAG_OFFLINE_KEY_ID', 'test-demo')
    session = MagicMock()
    result_tenant, result_audit = MagicMock(), MagicMock()
    result_tenant.scalar_one_or_none.return_value = SimpleNamespace(id='tenant-a', status='active', country='SG')
    result_audit.scalar_one_or_none.return_value = SimpleNamespace(detail=json.dumps({'revision': 5}))
    session.execute = AsyncMock(side_effect=[result_tenant, result_audit])
    session.flush, session.commit, session.rollback = AsyncMock(), AsyncMock(), AsyncMock()
    user = {'user_id': 'admin-a', 'email': 'test@example.invalid', 'is_super_admin': False}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: user
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    body = {'tenant_id': 'tenant-a', 'device_id': 'a' * 64, 'licence_type': 'internal_demo', 'camera_limit': 8}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.post('/api/agent/offline/admin/demo-entitlement', json=body)).status_code == 403
        session.execute.assert_not_called()
        user['is_super_admin'] = True
        response = await client.post('/api/agent/offline/admin/demo-entitlement', json=body)
    assert response.status_code == 200, response.text
    envelope = response.json()
    key.public_key().verify(base64.urlsafe_b64decode(envelope['signature']), envelope['payload'].encode('ascii'))
    claims = json.loads(base64.urlsafe_b64decode(envelope['payload']))
    assert claims['revision'] == 6
    assert claims['expires_at'] is None
    assert response.headers['cache-control'] == 'no-store'
    assert json.loads(session.add.call_args.args[0].detail)['licence_type'] == 'internal_demo'
    session.commit.assert_awaited_once()
