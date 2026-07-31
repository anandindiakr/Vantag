"""
backend/db/models/partner.py
=============================
Dealer / distributor / freelancer referral & commission ORM models.

A ``Partner`` is a dealer, distributor, or freelance business promoter who
refers paying customers (``Tenant`` rows) to the platform. Each partner has
a permanent, unique ``referral_code`` that is attached to a customer at
signup via ``PartnerReferral`` and never changes.

Commission amounts are NOT hardcoded — they are looked up from the
admin-editable ``CommissionRule`` table (seeded with the rates from the
Vantag Partner Distribution Playbook, but fully adjustable in the Admin UI)
and recorded per-invoice in ``CommissionLedger`` so partners have an
auditable, append-only earnings history.

Isolation: every partner-facing query MUST filter by ``partner_id`` to
guarantee a partner can only ever see their own referrals/earnings.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Partner(Base):
    """A dealer / distributor / freelance referral partner."""

    __tablename__ = "partners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # installer  -> fixed_pct dealer cut (default 25% of MRP)
    # distributor -> tiered_volume margin (Tier 1-4, by cumulative active streams)
    # referrer   -> flat_referral commission on lifetime contract value
    partner_type: Mapped[str] = mapped_column(String(20), default="installer")
    # Optional distributor -> sub-dealer hierarchy (not used by the UI yet,
    # reserved so sub-dealer rollups can be added without a schema change).
    parent_partner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("partners.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/suspended
    country: Mapped[str | None] = mapped_column(String(5))
    notes: Mapped[str | None] = mapped_column(Text)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    referrals: Mapped[list["PartnerReferral"]] = relationship(
        "PartnerReferral", back_populates="partner", cascade="all, delete-orphan"
    )
    ledger_entries: Mapped[list["CommissionLedger"]] = relationship(
        "CommissionLedger", back_populates="partner", cascade="all, delete-orphan"
    )


class PartnerReferral(Base):
    """
    Permanent link between a partner and the tenant (customer) they referred.

    One tenant can only ever have one referring partner — this row is
    created once at signup and is never reassigned through the app UI,
    guaranteeing the "permanent referral ID" behaviour requested.
    """

    __tablename__ = "partner_referrals"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_partner_referrals_tenant"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    partner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    referred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="referrals")


class CommissionRule(Base):
    """
    Admin-editable commission rate table.

    Seeded with the defaults from the Vantag Partner Distribution Playbook
    (25% fixed dealer cut, 5/10/15/20% volume tiers, 20% flat referral) but
    every rate/threshold here can be changed from the Admin Partner UI —
    nothing about the commission math is hardcoded in application code.
    """

    __tablename__ = "commission_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)  # fixed_pct/tiered_volume/flat_referral
    # Which plan/product this rule applies to ("*" = all plans)
    product_plan: Mapped[str] = mapped_column(String(50), default="*")
    region: Mapped[str] = mapped_column(String(20), default="*")  # india/singapore/.../* = all
    tier_name: Mapped[str | None] = mapped_column(String(50))  # e.g. "Tier 1 (Elite Partner)"
    tier_min_streams: Mapped[int] = mapped_column(Integer, default=0)
    tier_max_streams: Mapped[int | None] = mapped_column(Integer)  # null = unbounded
    rate_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class CommissionLedger(Base):
    """
    One row per commission-earning billing event. Append-only source of
    truth for a partner's "My Earnings" view and the admin payout workflow.
    """

    __tablename__ = "commission_ledger"
    __table_args__ = (UniqueConstraint("invoice_id", name="uq_commission_ledger_invoice"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    partner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    invoice_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("commission_rules.id"))
    gross_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), nullable=False)
    commission_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    rate_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/approved/paid
    notes: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    partner: Mapped[Partner] = relationship("Partner", back_populates="ledger_entries")
