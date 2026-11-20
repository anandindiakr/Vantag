from datetime import datetime, timedelta, timezone

import pytest

from test_offline_site import keys, signed_grant


def test_signed_internal_demo_has_no_expiry_but_is_device_bound(keys):
    from agent.local.licensing import evaluate_entitlement
    private, public = keys
    now = datetime.now(timezone.utc)
    device = 'a' * 64
    envelope = signed_grant(private, now, licence_type='internal_demo', issuing_role='super_admin', expires_at=None, device_id=device)
    assert evaluate_entitlement(envelope, public, device, now + timedelta(days=3650)).state == 'active'
    assert evaluate_entitlement(envelope, public, 'b' * 64, now).state == 'invalid'


@pytest.mark.parametrize('overrides', [
    {'device_id': None}, {'device_id': ''}, {'issuing_role': 'owner'},
    {'licence_type': 'customer'}, {'licence_type': 'evaluation'}, {'licence_type': 'unknown'},
])
def test_permanent_grant_requires_explicit_internal_authority(keys, overrides):
    from agent.local.licensing import evaluate_entitlement
    private, public = keys
    now = datetime.now(timezone.utc)
    claims = dict(licence_type='internal_demo', issuing_role='super_admin', expires_at=None, device_id='a' * 64)
    claims.update(overrides)
    assert evaluate_entitlement(signed_grant(private, now, **claims), public, 'a' * 64, now).state == 'invalid'


def test_internal_demo_still_detects_clock_rollback(keys):
    from agent.local.licensing import evaluate_entitlement
    private, public = keys
    now = datetime.now(timezone.utc)
    grant = signed_grant(private, now, licence_type='internal_demo', issuing_role='super_admin', expires_at=None, device_id='a' * 64)
    assert evaluate_entitlement(grant, public, 'a' * 64, now, last_seen=(now + timedelta(hours=1)).timestamp()).state == 'invalid'
