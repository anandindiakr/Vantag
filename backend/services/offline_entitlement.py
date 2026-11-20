from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

CORE_FEATURES = ["people_count", "shoplifting", "inventory_movement", "fall_detected", "restricted_zone", "loitering", "suspicious_behavior", "crowding"]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def effective_expiry(tenant, subscriptions, now: datetime | None = None) -> datetime:
    current = _utc(now or datetime.now(timezone.utc))
    if tenant.status not in {"active", "trial"}:
        raise ValueError("This account cannot receive a new offline entitlement")
    candidates = []
    if tenant.trial_ends_at:
        candidates.append(_utc(tenant.trial_ends_at))
    elif tenant.status == "trial" and tenant.created_at:
        candidates.append(_utc(tenant.created_at) + timedelta(days=3))
    for subscription in subscriptions:
        paid_to_end = subscription.status == "active" or (subscription.status == "cancelled" and subscription.cancel_at_period_end)
        if paid_to_end and subscription.current_period_end:
            candidates.append(_utc(subscription.current_period_end))
    valid = [end for end in candidates if end > current]
    if not valid:
        raise ValueError("No future paid-through date, trial or explicit extension is recorded; contact the administrator")
    return max(valid)


def signing_key():
    filename = os.getenv("VANTAG_OFFLINE_SIGNING_KEY_FILE", "")
    key_id = os.getenv("VANTAG_OFFLINE_KEY_ID", "")
    if not filename or not key_id:
        raise ValueError("Offline entitlement signing is not configured")
    key = serialization.load_pem_private_key(Path(filename).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Offline entitlements require an Ed25519 signing key")
    return key_id, key


def sign_entitlement(claims: dict) -> dict:
    key_id, key = signing_key()
    document = dict(claims, key_id=key_id)
    payload = base64.urlsafe_b64encode(json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).decode("ascii")
    return {"payload": payload, "signature": base64.urlsafe_b64encode(key.sign(payload.encode("ascii"))).decode("ascii")}


def demo_claims(admin: dict, tenant_id: str, issuer: str, device_id: str, licence_type: str, days: int | None, camera_limit: int, revision: int) -> dict:
    if admin.get("is_super_admin") is not True or not admin.get("user_id"):
        raise ValueError("Only a superadmin can issue demo licences")
    if not isinstance(device_id, str) or len(device_id) != 64 or any(character not in "0123456789abcdef" for character in device_id):
        raise ValueError("A device-bound renewal request is required")
    if licence_type not in {"internal_demo", "evaluation"}:
        raise ValueError("Unsupported demo policy")
    if licence_type == "internal_demo" and days is not None:
        raise ValueError("Internal demo grants do not have an expiry")
    if licence_type == "evaluation" and (type(days) is not int or not 1 <= days <= 365):
        raise ValueError("Select an evaluation period from 1 to 365 days")
    if type(camera_limit) is not int or not 1 <= camera_limit <= 256:
        raise ValueError("Select a camera limit from 1 to 256")
    now = datetime.now(timezone.utc)
    return {"version": 1, "issuer": issuer, "tenant_id": tenant_id, "entitlement_id": str(uuid.uuid4()), "revision": revision, "issued_at": now.timestamp(), "not_before": (now - timedelta(minutes=1)).timestamp(), "expires_at": None if licence_type == "internal_demo" else (now + timedelta(days=days)).timestamp(), "grace_days": 7, "camera_limit": camera_limit, "features": CORE_FEATURES, "device_id": device_id, "licence_type": licence_type, "issuing_role": "super_admin", "issued_by": admin["user_id"]}


async def issue_demo(session, admin: dict, tenant_id: str, device_id: str, licence_type: str, days: int | None, camera_limit: int) -> dict:
    if admin.get("is_super_admin") is not True:
        raise ValueError("Only a superadmin can issue demo licences")
    from sqlalchemy import select
    from ..config.regions import get_region
    from ..db.models.admin import AdminAuditLog
    from ..db.models.tenant import Tenant

    tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id).with_for_update())).scalar_one_or_none()
    if tenant is None or tenant.status not in {"active", "trial"}:
        raise ValueError("Select an active or trial account for this demo device")
    previous = (await session.execute(select(AdminAuditLog).where(AdminAuditLog.action == "issue_offline_entitlement", AdminAuditLog.target_id == tenant.id).order_by(AdminAuditLog.created_at.desc()).limit(1))).scalar_one_or_none()
    revision = int(json.loads(previous.detail)["revision"]) + 1 if previous else 1
    claims = demo_claims(admin, tenant.id, get_region(tenant.country)["domain"], device_id, licence_type, days, camera_limit, revision)
    envelope = sign_entitlement(claims)
    session.add(AdminAuditLog(admin_user_id=admin["user_id"], admin_email=admin.get("email"), action="issue_offline_entitlement", target_type="tenant", target_id=tenant.id, detail=json.dumps({name: claims[name] for name in ("revision", "entitlement_id", "device_id", "expires_at", "licence_type", "issued_by")})))
    await session.flush()
    return envelope


async def issue_for_user(session, user: dict, device_id: str | None = None) -> dict:
    from sqlalchemy import select
    from ..config.plans import get_plan
    from ..config.regions import get_region
    from ..db.models.admin import AdminAuditLog
    from ..db.models.billing import Subscription
    from ..db.models.tenant import Tenant

    if user.get("role") not in {"owner", "admin"}:
        raise ValueError("Only a site owner or administrator can issue offline access")
    tenant = (await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]).with_for_update())).scalar_one_or_none()
    if tenant is None:
        raise ValueError("Account not found")
    subscriptions = (await session.execute(select(Subscription).where(Subscription.tenant_id == tenant.id))).scalars().all()
    now = datetime.now(timezone.utc)
    expiry = effective_expiry(tenant, subscriptions, now)
    plan = get_plan(tenant.plan_id)
    if not plan:
        raise ValueError("No valid subscription plan is configured")
    previous = (await session.execute(select(AdminAuditLog).where(AdminAuditLog.action == "issue_offline_entitlement", AdminAuditLog.target_id == tenant.id).order_by(AdminAuditLog.created_at.desc()).limit(1))).scalar_one_or_none()
    revision = int(json.loads(previous.detail)["revision"]) + 1 if previous else 1
    claims = {"version": 1, "issuer": get_region(tenant.country)["domain"], "tenant_id": tenant.id, "entitlement_id": str(uuid.uuid4()), "revision": revision, "issued_at": now.timestamp(), "not_before": (now - timedelta(minutes=1)).timestamp(), "expires_at": expiry.timestamp(), "grace_days": 7, "camera_limit": plan["max_cameras"], "features": CORE_FEATURES, "device_id": device_id}
    envelope = sign_entitlement(claims)
    session.add(AdminAuditLog(admin_user_id=user["user_id"], admin_email=user.get("email"), action="issue_offline_entitlement", target_type="tenant", target_id=tenant.id, detail=json.dumps({"revision": revision, "entitlement_id": claims["entitlement_id"], "device_id": device_id, "expires_at": expiry.isoformat(), "features": CORE_FEATURES})))
    await session.flush()
    return envelope
