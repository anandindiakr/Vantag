"""Tenant, TenantUser, EdgeAgent ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(5), nullable=False)  # IN/SG/MY
    region: Mapped[str] = mapped_column(String(20), nullable=False)  # india/singapore/malaysia
    plan_id: Mapped[str] = mapped_column(String(50), default="starter")
    status: Mapped[str] = mapped_column(String(20), default="trial")  # trial/active/suspended/cancelled
    language: Mapped[str] = mapped_column(String(10), default="en")  # en/hi/ms/zh
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0)
    onboarding_token: Mapped[str | None] = mapped_column(String(200))
    razorpay_customer_id: Mapped[str | None] = mapped_column(String(200))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    users: Mapped[list[TenantUser]] = relationship("TenantUser", back_populates="tenant", cascade="all, delete-orphan")
    cameras: Mapped[list["CameraConfig"]] = relationship("CameraConfig", back_populates="tenant", cascade="all, delete-orphan")
    edge_agents: Mapped[list[EdgeAgent]] = relationship("EdgeAgent", back_populates="tenant", cascade="all, delete-orphan")
    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="tenant", cascade="all, delete-orphan")


class TenantUser(Base):
    __tablename__ = "tenant_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner/admin/viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verify_token: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="users")


class EdgeAgent(Base):
    __tablename__ = "edge_agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50))  # android/windows/raspberry_pi/mac
    device_name: Mapped[str | None] = mapped_column(String(200))
    api_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="offline")  # online/offline
    capabilities: Mapped[dict | None] = mapped_column(JSONB)
    camera_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="edge_agents")
