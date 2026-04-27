"""SystemAlert and AdminAuditLog ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class SystemAlert(Base):
    __tablename__ = "system_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    level: Mapped[str] = mapped_column(String(20), nullable=False)  # info/warning/critical
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100))  # e.g. "alert_monitor" / "signup"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    admin_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    admin_email: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "suspend_tenant"
    target_type: Mapped[str | None] = mapped_column(String(50))       # e.g. "tenant" / "user"
    target_id: Mapped[str | None] = mapped_column(String(36))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
