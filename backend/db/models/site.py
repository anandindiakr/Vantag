"""Site (store / branch / outlet) ORM model.

Why this exists
---------------
Before this model, a "store" was not a real thing in the database. It was
derived at request time by slugifying the prefix of ``camera_configs.location``
(a free-text string like ``"Zone A - Front Door"``), in six different places
with two *different* splitting rules. Consequences:

* stores could not be created, renamed or deleted;
* renaming a camera's location silently moved it to a different "store",
  orphaning its history;
* ``"Zone A - Front Door"`` slugged differently depending on which endpoint
  answered, so the same camera could appear under two store ids;
* every edge agent received *all* tenant cameras, so a tenant with two
  physical branches had each agent trying to reach the other branch's LAN.

``sites`` makes the store a first-class, tenant-scoped row with a stable id.
``camera_configs.site_id`` is nullable so existing installs keep working
untouched: a camera with no site still falls back to the legacy derived
``store_id``. Nothing breaks on deploy; sites are opt-in per tenant.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def slugify_site(name: str) -> str:
    """Stable, URL-safe slug for a site name.

    Deliberately the SINGLE definition of this transform. The legacy code had
    two competing variants (one splitting only on the en-dash, one on both
    en-dash and hyphen) which is exactly how the same camera ended up under two
    different store ids.
    """
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "store"


def derive_legacy_store_id(location: str | None) -> str:
    """Reproduce the OLD derived store_id exactly, for backfill + fallback.

    Kept byte-compatible with the historical behaviour so that backfilling
    does not renumber any tenant's existing dashboard groupings. Splits on
    BOTH the en-dash and the hyphen, which was the majority variant.
    """
    location = location or ""
    prefix = location.split("\u2013")[0].split("-")[0].strip() if location else ""
    return (prefix or "auto-detected").lower().replace(" ", "_")


class Site(Base):
    """A physical store / branch / outlet belonging to one tenant."""

    __tablename__ = "sites"
    __table_args__ = (
        # Two sites in the same tenant may not share a slug — the slug is what
        # appears in URLs and what the legacy store_id backfills into.
        UniqueConstraint("tenant_id", "slug", name="uq_sites_tenant_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Stable, human-readable id used in URLs and as the bridge to the legacy
    # derived store_id so existing incident history keeps lining up.
    slug: Mapped[str] = mapped_column(String(120), nullable=False)

    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120))
    timezone_name: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    open_time: Mapped[str] = mapped_column(String(5), default="09:00")
    close_time: Mapped[str] = mapped_column(String(5), default="21:00")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    cameras = relationship(
        "CameraConfig",
        back_populates="site",
        passive_deletes=True,
    )
