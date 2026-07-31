"""
backend/api/partner_admin_router.py
======================================
Super-admin management of partners, commission rules, and the payout ledger.

All routes require ``require_super_admin`` — mirrors the pattern used by
``admin_router.py``. Mounted at: /api/admin/partners, /api/admin/commission-*
"""
from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.partner import CommissionLedger, CommissionRule, Partner, PartnerReferral
from ..middleware.tenant_middleware import require_super_admin
from .partner_router import _hash_password

partner_admin_router = APIRouter(prefix="/api/admin", tags=["Admin - Partners"])


def _generate_referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "REF-" + "".join(secrets.choice(alphabet) for _ in range(8))


def _generate_temp_password() -> str:
    return secrets.token_urlsafe(9)


# ── Partners CRUD ────────────────────────────────────────────────────────

class CreatePartnerRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    partner_type: str = "installer"  # installer/distributor/referrer
    country: str | None = None
    notes: str | None = None


@partner_admin_router.post("/partners", status_code=201)
async def create_partner(
    body: CreatePartnerRequest,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    existing = await session.execute(select(Partner).where(Partner.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A partner with this email already exists")

    if body.partner_type not in ("installer", "distributor", "referrer"):
        raise HTTPException(status_code=400, detail="partner_type must be installer/distributor/referrer")

    code = _generate_referral_code()
    while (await session.execute(select(Partner).where(Partner.referral_code == code))).scalar_one_or_none():
        code = _generate_referral_code()

    temp_password = _generate_temp_password()
    partner = Partner(
        id=str(uuid.uuid4()),
        referral_code=code,
        name=body.name,
        email=body.email.lower(),
        phone=body.phone,
        hashed_password=_hash_password(temp_password),
        partner_type=body.partner_type,
        country=body.country,
        notes=body.notes,
        status="active",
    )
    session.add(partner)
    await session.commit()

    # Best-effort welcome email with the temporary password + referral link.
    try:
        from ..services.email_service import send_email
        region_domain_map = {
            "IN": "retailnazar.com", "SG": "retail-vantag.com", "MY": "jagajaga.my",
            "PH": "retailbantay.com", "ID": "retailpantau.com",
        }
        domain = region_domain_map.get((body.country or "IN").upper(), "retail-vantag.com")
        referral_link = f"https://{domain}/register?ref={code}"
        subject = "Your Vantag Partner Account is ready"
        html = (
            f"<p>Hi {body.name},</p>"
            f"<p>Your partner portal account has been created.</p>"
            f"<p><strong>Login:</strong> https://{domain}/partner/login<br>"
            f"<strong>Email:</strong> {body.email}<br>"
            f"<strong>Temporary password:</strong> {temp_password}</p>"
            f"<p><strong>Your permanent referral link:</strong> {referral_link}</p>"
            f"<p>Please log in and change your password immediately.</p>"
        )
        text = f"Login: https://{domain}/partner/login | Email: {body.email} | Temp password: {temp_password} | Referral link: {referral_link}"
        import asyncio
        asyncio.create_task(send_email(body.email.lower(), subject, html, text))
    except Exception:  # noqa: BLE001
        pass

    return {
        "id": partner.id,
        "referral_code": code,
        "temp_password": temp_password,
        "message": "Partner created. Welcome email sent (best-effort).",
    }


@partner_admin_router.get("/partners")
async def list_partners(
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(select(Partner).order_by(Partner.created_at.desc()))
    partners = result.scalars().all()

    out = []
    for p in partners:
        ref_count = (
            await session.execute(
                select(PartnerReferral).where(PartnerReferral.partner_id == p.id)
            )
        ).scalars().all()
        out.append({
            "id": p.id,
            "name": p.name,
            "email": p.email,
            "phone": p.phone,
            "partner_type": p.partner_type,
            "referral_code": p.referral_code,
            "status": p.status,
            "country": p.country,
            "referred_customers": len(ref_count),
            "created_at": p.created_at.isoformat(),
        })
    return {"partners": out, "total": len(out)}


class UpdatePartnerRequest(BaseModel):
    status: str | None = None  # active/suspended
    partner_type: str | None = None
    notes: str | None = None


@partner_admin_router.patch("/partners/{partner_id}")
async def update_partner(
    partner_id: str,
    body: UpdatePartnerRequest,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(select(Partner).where(Partner.id == partner_id))
    partner = result.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    if body.status and body.status not in ("active", "suspended"):
        raise HTTPException(status_code=400, detail="status must be active/suspended")
    if body.status:
        partner.status = body.status
    if body.partner_type:
        if body.partner_type not in ("installer", "distributor", "referrer"):
            raise HTTPException(status_code=400, detail="Invalid partner_type")
        partner.partner_type = body.partner_type
    if body.notes is not None:
        partner.notes = body.notes

    await session.commit()
    return {"id": partner.id, "status": partner.status, "partner_type": partner.partner_type}


# ── Commission rules (admin-editable rate table) ────────────────────────

class CommissionRuleRequest(BaseModel):
    rule_type: str  # fixed_pct/tiered_volume/flat_referral
    product_plan: str = "*"
    region: str = "*"
    tier_name: str | None = None
    tier_min_streams: int = 0
    tier_max_streams: int | None = None
    rate_pct: float
    is_active: bool = True


@partner_admin_router.get("/commission-rules")
async def list_commission_rules(
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(CommissionRule).order_by(CommissionRule.rule_type, CommissionRule.tier_min_streams)
    )
    rules = result.scalars().all()
    return {
        "rules": [
            {
                "id": r.id,
                "rule_type": r.rule_type,
                "product_plan": r.product_plan,
                "region": r.region,
                "tier_name": r.tier_name,
                "tier_min_streams": r.tier_min_streams,
                "tier_max_streams": r.tier_max_streams,
                "rate_pct": float(r.rate_pct),
                "is_active": r.is_active,
            }
            for r in rules
        ]
    }


@partner_admin_router.post("/commission-rules", status_code=201)
async def create_commission_rule(
    body: CommissionRuleRequest,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if body.rule_type not in ("fixed_pct", "tiered_volume", "flat_referral"):
        raise HTTPException(status_code=400, detail="Invalid rule_type")
    rule = CommissionRule(
        id=str(uuid.uuid4()),
        rule_type=body.rule_type,
        product_plan=body.product_plan,
        region=body.region,
        tier_name=body.tier_name,
        tier_min_streams=body.tier_min_streams,
        tier_max_streams=body.tier_max_streams,
        rate_pct=body.rate_pct,
        is_active=body.is_active,
    )
    session.add(rule)
    await session.commit()
    return {"id": rule.id}


class UpdateCommissionRuleRequest(BaseModel):
    rate_pct: float | None = None
    tier_min_streams: int | None = None
    tier_max_streams: int | None = None
    is_active: bool | None = None


@partner_admin_router.patch("/commission-rules/{rule_id}")
async def update_commission_rule(
    rule_id: str,
    body: UpdateCommissionRuleRequest,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(select(CommissionRule).where(CommissionRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Commission rule not found")

    if body.rate_pct is not None:
        rule.rate_pct = body.rate_pct
    if body.tier_min_streams is not None:
        rule.tier_min_streams = body.tier_min_streams
    if body.tier_max_streams is not None:
        rule.tier_max_streams = body.tier_max_streams
    if body.is_active is not None:
        rule.is_active = body.is_active

    await session.commit()
    return {"id": rule.id, "rate_pct": float(rule.rate_pct)}


# ── Commission ledger (view all + approve/mark-paid) ────────────────────

@partner_admin_router.get("/commission-ledger")
async def list_commission_ledger(
    partner_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(CommissionLedger)
    if partner_id:
        stmt = stmt.where(CommissionLedger.partner_id == partner_id)
    if status_filter:
        stmt = stmt.where(CommissionLedger.status == status_filter)
    stmt = stmt.order_by(CommissionLedger.computed_at.desc())

    result = await session.execute(stmt)
    entries = result.scalars().all()
    return {
        "entries": [
            {
                "id": e.id,
                "partner_id": e.partner_id,
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
        "total": len(entries),
    }


class UpdateLedgerStatusRequest(BaseModel):
    status: str  # pending/approved/paid


@partner_admin_router.patch("/commission-ledger/{ledger_id}")
async def update_ledger_status(
    ledger_id: str,
    body: UpdateLedgerStatusRequest,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if body.status not in ("pending", "approved", "paid"):
        raise HTTPException(status_code=400, detail="status must be pending/approved/paid")

    result = await session.execute(select(CommissionLedger).where(CommissionLedger.id == ledger_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Ledger entry not found")

    entry.status = body.status
    if body.status == "paid":
        entry.paid_at = datetime.now(timezone.utc)
    await session.commit()
    return {"id": entry.id, "status": entry.status}
