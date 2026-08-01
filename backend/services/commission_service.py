"""
backend/services/commission_service.py
=========================================
Computes and records partner commissions for a paid invoice.

This module is intentionally the ONLY place that turns a "gross invoice
amount" into a "commission amount" — the actual percentages come from the
admin-editable ``commission_rules`` table (never hardcoded here), so rates
can be tuned from the Admin Partner UI without a code change or deploy.

Called from ``billing_router._process_webhook_event`` right after an
invoice/subscription-charge is marked paid.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.billing import Invoice
from ..db.models.partner import CommissionLedger, CommissionRule, Partner, PartnerReferral

logger = logging.getLogger("vantag.commission")


async def _active_stream_count(session: AsyncSession, partner_id: str) -> int:
    """
    Cumulative active-stream footprint for a partner (used by tiered_volume
    rules). Approximated as the count of that partner's referred tenants
    that are currently active/trial — a reasonable proxy for "active
    streams" until per-camera stream counts are wired in.
    """
    from ..db.models.tenant import Tenant

    result = await session.execute(
        select(func.count(Tenant.id))
        .select_from(PartnerReferral)
        .join(Tenant, Tenant.id == PartnerReferral.tenant_id)
        .where(
            PartnerReferral.partner_id == partner_id,
            Tenant.status.in_(("active", "trial")),
        )
    )
    return int(result.scalar_one() or 0)


async def _find_rule(
    session: AsyncSession,
    *,
    rule_type: str,
    region: str | None,
    stream_count: int,
) -> CommissionRule | None:
    """
    Look up the best-matching active commission rule.

    Matching precedence: exact region match beats "*" (all-regions); for
    tiered_volume rules the stream_count must fall within
    [tier_min_streams, tier_max_streams].
    """
    stmt = select(CommissionRule).where(
        CommissionRule.rule_type == rule_type,
        CommissionRule.is_active.is_(True),
    )
    result = await session.execute(stmt)
    candidates = list(result.scalars().all())
    if not candidates:
        return None

    def _region_matches(r: CommissionRule) -> bool:
        return r.region in ("*", None) or r.region == region

    def _tier_matches(r: CommissionRule) -> bool:
        if rule_type != "tiered_volume":
            return True
        lo = r.tier_min_streams or 0
        hi = r.tier_max_streams
        return stream_count >= lo and (hi is None or stream_count <= hi)

    matches = [r for r in candidates if _region_matches(r) and _tier_matches(r)]
    if not matches:
        return None

    # Prefer an exact region match over a wildcard.
    exact = [r for r in matches if r.region == region]
    pool = exact or matches
    # Highest tier_min_streams wins among tiered matches (most specific tier).
    pool.sort(key=lambda r: (r.tier_min_streams or 0), reverse=True)
    return pool[0]


async def compute_commission_for_invoice(
    invoice: Invoice,
    session: AsyncSession,
) -> CommissionLedger | None:
    """
    If the invoice's tenant was referred by a partner, compute and record
    a commission ledger entry for the paid invoice amount.

    Idempotent: a unique constraint on ``commission_ledger.invoice_id``
    ensures a webhook retry never double-counts a commission.
    """
    ref_result = await session.execute(
        select(PartnerReferral).where(PartnerReferral.tenant_id == invoice.tenant_id)
    )
    referral = ref_result.scalar_one_or_none()
    if not referral:
        return None  # this tenant wasn't referred by any partner

    partner_result = await session.execute(
        select(Partner).where(Partner.id == referral.partner_id)
    )
    partner = partner_result.scalar_one_or_none()
    if not partner or partner.status != "active":
        return None

    # Skip if a ledger entry already exists for this invoice (idempotency).
    existing = await session.execute(
        select(CommissionLedger).where(CommissionLedger.invoice_id == invoice.id)
    )
    if existing.scalar_one_or_none():
        return None

    from ..db.models.tenant import Tenant

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == invoice.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    region = tenant.region if tenant else None

    rule: CommissionRule | None = None

    # An admin can pin an exact commission rule to a partner at onboarding
    # time (e.g. a specific distributor tier) — when set, it always wins
    # over the partner_type -> rule_type auto-lookup below.
    if partner.commission_rule_id:
        pinned = await session.execute(
            select(CommissionRule).where(
                CommissionRule.id == partner.commission_rule_id,
                CommissionRule.is_active.is_(True),
            )
        )
        rule = pinned.scalar_one_or_none()
        if not rule:
            logger.warning(
                "Partner=%s has commission_rule_id=%s but it is missing/inactive — falling back to auto-lookup",
                partner.id, partner.commission_rule_id,
            )

    if not rule:
        rule_type_map = {
            "installer": "fixed_pct",
            "distributor": "tiered_volume",
            "referrer": "flat_referral",
        }
        rule_type = rule_type_map.get(partner.partner_type, "fixed_pct")

        stream_count = 0
        if rule_type == "tiered_volume":
            stream_count = await _active_stream_count(session, partner.id)

        rule = await _find_rule(session, rule_type=rule_type, region=region, stream_count=stream_count)
        if not rule:
            logger.warning(
                "No active commission_rule found for partner=%s type=%s region=%s — skipping commission",
                partner.id, rule_type, region,
            )
            return None

    gross = float(invoice.amount)
    rate = float(rule.rate_pct)
    commission_amount = round(gross * rate / 100.0, 2)

    ledger = CommissionLedger(
        id=str(uuid.uuid4()),
        partner_id=partner.id,
        tenant_id=invoice.tenant_id,
        invoice_id=invoice.id,
        rule_id=rule.id,
        gross_amount=gross,
        currency=invoice.currency,
        commission_amount=commission_amount,
        rate_pct=rate,
        status="pending",
        computed_at=datetime.now(timezone.utc),
    )
    session.add(ledger)
    logger.info(
        "Commission computed: partner=%s tenant=%s invoice=%s rate=%s%% amount=%s %s",
        partner.id, invoice.tenant_id, invoice.id, rate, commission_amount, invoice.currency,
    )
    return ledger
