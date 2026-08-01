"""
backend/api/partner_router.py
================================
Partner-facing authentication and self-service portal endpoints.

Deliberately isolated from the tenant auth system (``auth_router.py`` /
``tenant_middleware.py``): partners log in via a completely separate JWT
claim shape (``partner_id`` instead of ``tenant_id``), so a tenant session
token can never be used to call a partner endpoint and vice versa.

All ``/me/*`` routes are hard-scoped to ``partner_id`` from the token —
a partner can only ever see their own referred customers and earnings.

Mounted at: /api/partner
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.partner import CommissionLedger, Partner, PartnerReferral

try:
    from jose import jwt
except ImportError:  # pragma: no cover - jose is a hard dependency elsewhere
    jwt = None

try:
    import bcrypt as _bcrypt

    def _hash_password(pw: str) -> str:
        return _bcrypt.hashpw(pw.encode("utf-8"), _bcrypt.gensalt(rounds=12)).decode("utf-8")

    def _verify_password(pw: str, h: str) -> bool:
        try:
            return _bcrypt.checkpw(pw.encode("utf-8"), h.encode("utf-8"))
        except (ValueError, TypeError):
            return False
except ImportError as _exc:  # pragma: no cover
    raise RuntimeError("bcrypt is required but not installed.") from _exc


def _jwt_secret() -> str:
    return os.getenv("VANTAG_JWT_SECRET", "change-me")


_PARTNER_JWT_EXPIRE_HOURS = 24
_bearer = HTTPBearer(auto_error=False)

partner_router = APIRouter(prefix="/api/partner", tags=["partner"])


# ── Auth dependency (partner-only, isolated from tenant auth) ──────────────

async def get_current_partner(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> Partner:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, _jwt_secret(), algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    partner_id = payload.get("partner_id")
    if not partner_id or payload.get("scope") != "partner":
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await session.execute(select(Partner).where(Partner.id == partner_id))
    partner = result.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    if partner.status != "active":
        raise HTTPException(status_code=403, detail="Partner account suspended")

    token_ver = payload.get("ver")
    if token_ver is not None and int(token_ver) != int(partner.token_version or 0):
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")

    return partner


def _make_partner_token(partner: Partner) -> str:
    data = {
        "partner_id": partner.id,
        "email": partner.email,
        "scope": "partner",
        "ver": partner.token_version or 0,
        "exp": datetime.now(timezone.utc) + timedelta(hours=_PARTNER_JWT_EXPIRE_HOURS),
    }
    return jwt.encode(data, _jwt_secret(), algorithm="HS256")


class PartnerLoginRequest(BaseModel):
    email: EmailStr
    password: str


@partner_router.post("/login")
async def partner_login(
    body: PartnerLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Partner).where(Partner.email == body.email.lower())
    )
    partner = result.scalar_one_or_none()
    if not partner or not _verify_password(body.password, partner.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if partner.status != "active":
        raise HTTPException(status_code=403, detail="Partner account suspended")

    return {
        "access_token": _make_partner_token(partner),
        "token_type": "bearer",
        "partner_id": partner.id,
        "name": partner.name,
        "referral_code": partner.referral_code,
        "partner_type": partner.partner_type,
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@partner_router.post("/change-password")
async def partner_change_password(
    body: ChangePasswordRequest,
    partner: Partner = Depends(get_current_partner),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not _verify_password(body.current_password, partner.hashed_password):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    partner.hashed_password = _hash_password(body.new_password)
    partner.token_version = (partner.token_version or 0) + 1
    await session.commit()
    return {"message": "Password updated. Please sign in again."}


@partner_router.get("/me")
async def get_me(
    partner: Partner = Depends(get_current_partner),
    session: AsyncSession = Depends(get_session),
) -> dict:
    region_domain_map = {
        "india": "retailnazar.com",
        "singapore": "retail-vantag.com",
        "malaysia": "jagajaga.my",
        "philippines": "retailbantay.com",
        "indonesia": "retailpantau.com",
    }
    domain = region_domain_map.get((partner.country or "").lower(), "retail-vantag.com")

    commission_rule = None
    if partner.commission_rule_id:
        from ..db.models.partner import CommissionRule

        rule_result = await session.execute(
            select(CommissionRule).where(CommissionRule.id == partner.commission_rule_id)
        )
        rule = rule_result.scalar_one_or_none()
        if rule:
            commission_rule = {
                "id": rule.id,
                "rule_type": rule.rule_type,
                "tier_name": rule.tier_name,
                "rate_pct": float(rule.rate_pct),
            }

    return {
        "id": partner.id,
        "name": partner.name,
        "email": partner.email,
        "phone": partner.phone,
        "partner_type": partner.partner_type,
        "referral_code": partner.referral_code,
        "referral_link": f"https://{domain}/register?ref={partner.referral_code}",
        "status": partner.status,
        "created_at": partner.created_at.isoformat(),
        "commission_rule": commission_rule,
    }


@partner_router.get("/me/referrals")
async def get_my_referrals(
    partner: Partner = Depends(get_current_partner),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    List every tenant permanently referred by the logged-in partner, along
    with their current subscription (plan/price/status) and full paid
    invoice history — so a partner can see exactly which of their referred
    customers are live-paying and what commission each invoice generated.
    """
    from ..db.models.billing import Invoice, Subscription
    from ..db.models.partner import CommissionLedger
    from ..db.models.tenant import Tenant

    result = await session.execute(
        select(PartnerReferral, Tenant)
        .join(Tenant, Tenant.id == PartnerReferral.tenant_id)
        .where(PartnerReferral.partner_id == partner.id)
        .order_by(PartnerReferral.referred_at.desc())
    )
    rows = result.all()
    tenant_ids = [tenant.id for _, tenant in rows]

    subs_by_tenant: dict[str, Subscription] = {}
    if tenant_ids:
        subs_result = await session.execute(
            select(Subscription)
            .where(Subscription.tenant_id.in_(tenant_ids))
            .order_by(Subscription.created_at.desc())
        )
        for sub in subs_result.scalars().all():
            subs_by_tenant.setdefault(sub.tenant_id, sub)  # first = most recent

    invoices_by_tenant: dict[str, list[Invoice]] = {}
    commission_by_invoice: dict[str, CommissionLedger] = {}
    if tenant_ids:
        inv_result = await session.execute(
            select(Invoice)
            .where(Invoice.tenant_id.in_(tenant_ids))
            .order_by(Invoice.created_at.desc())
        )
        for inv in inv_result.scalars().all():
            invoices_by_tenant.setdefault(inv.tenant_id, []).append(inv)

        ledger_result = await session.execute(
            select(CommissionLedger).where(CommissionLedger.partner_id == partner.id)
        )
        for entry in ledger_result.scalars().all():
            commission_by_invoice[entry.invoice_id] = entry

    referrals = []
    for referral, tenant in rows:
        sub = subs_by_tenant.get(tenant.id)
        tenant_invoices = invoices_by_tenant.get(tenant.id, [])
        referrals.append({
            "tenant_id": tenant.id,
            "name": tenant.name,
            "country": tenant.country,
            "plan_id": tenant.plan_id,
            "status": tenant.status,
            "referred_at": referral.referred_at.isoformat(),
            "subscription": {
                "plan_id": sub.plan_id,
                "status": sub.status,
                "amount": float(sub.amount) if sub.amount is not None else None,
                "currency": sub.currency,
                "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
                "cancel_at_period_end": sub.cancel_at_period_end,
            } if sub else None,
            "payment_history": [
                {
                    "invoice_id": inv.id,
                    "amount": float(inv.amount),
                    "currency": inv.currency,
                    "status": inv.status,
                    "invoice_number": inv.invoice_number,
                    "created_at": inv.created_at.isoformat(),
                    "commission_amount": (
                        float(commission_by_invoice[inv.id].commission_amount)
                        if inv.id in commission_by_invoice else None
                    ),
                    "commission_status": (
                        commission_by_invoice[inv.id].status if inv.id in commission_by_invoice else None
                    ),
                }
                for inv in tenant_invoices
            ],
        })

    return {"referrals": referrals, "total": len(referrals)}


@partner_router.get("/me/earnings")
async def get_my_earnings(
    status_filter: Optional[str] = None,
    partner: Partner = Depends(get_current_partner),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Commission ledger for the logged-in partner only. Optional
    ``status_filter`` of pending/approved/paid.
    """
    stmt = select(CommissionLedger).where(CommissionLedger.partner_id == partner.id)
    if status_filter:
        stmt = stmt.where(CommissionLedger.status == status_filter)
    stmt = stmt.order_by(CommissionLedger.computed_at.desc())

    result = await session.execute(stmt)
    entries = result.scalars().all()

    totals: dict[str, float] = {}
    for e in entries:
        totals[e.currency] = totals.get(e.currency, 0.0) + float(e.commission_amount)

    return {
        "entries": [
            {
                "id": e.id,
                "tenant_id": e.tenant_id,
                "invoice_id": e.invoice_id,
                "gross_amount": float(e.gross_amount),
                "currency": e.currency,
                "commission_amount": float(e.commission_amount),
                "rate_pct": float(e.rate_pct),
                "status": e.status,
                "computed_at": e.computed_at.isoformat(),
                "paid_at": e.paid_at.isoformat() if e.paid_at else None,
            }
            for e in entries
        ],
        "totals_by_currency": totals,
        "total_count": len(entries),
    }
