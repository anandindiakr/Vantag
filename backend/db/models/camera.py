"""CameraConfig ORM model — replaces cameras.yaml for SaaS tenants."""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def _get_fernet():
    """Return a Fernet instance if VANTAG_ENCRYPTION_KEY is configured."""
    key = (
        os.getenv("VANTAG_ENCRYPTION_KEY")
        or os.getenv("FACE_ENCRYPTION_KEY")
        or os.getenv("VANTAG_FACE_KEY")
        or ""
    )
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:  # noqa: BLE001
        return None


_FERNET_PREFIX = "fernet:"


class CameraConfig(Base):
    __tablename__ = "camera_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    camera_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    # rtsp_url stores the encrypted value (fernet: prefix) when a key is configured.
    # Use .get_rtsp_url() to retrieve the decrypted plaintext.
    rtsp_url: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(50))
    brand: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(200))
    # Real store/branch this camera belongs to. NULLABLE on purpose: existing
    # installs have no sites, and those cameras keep falling back to the legacy
    # store_id derived from `location`. Nothing breaks until a tenant opts in.
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolution_width: Mapped[int] = mapped_column(Integer, default=1920)
    resolution_height: Mapped[int] = mapped_column(Integer, default=1080)
    fps_target: Mapped[int] = mapped_column(Integer, default=15)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    low_light_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    analyzer_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    conn_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/online/offline
    probe_result: Mapped[dict | None] = mapped_column(JSONB)
    staff_zone_colors: Mapped[dict | None] = mapped_column(JSONB)
    zones: Mapped[dict | None] = mapped_column(JSONB)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="cameras")
    # lazy="selectin" is deliberate: effective_store_id below is read from many
    # request handlers, and under async SQLAlchemy a lazy relationship access
    # raises MissingGreenlet. Eager-loading it here means every caller gets a
    # correct store id without having to remember .options(selectinload(...)),
    # which is exactly the kind of easy-to-forget detail that produced the
    # original inconsistent-store_id bug. Cost is one small extra SELECT.
    site = relationship("Site", back_populates="cameras", lazy="selectin")

    @property
    def effective_store_id(self) -> str:
        """The store id to report for this camera.

        Prefers the real Site slug. Falls back to the legacy location-prefix
        slug so tenants who have not created sites see exactly what they saw
        before. This is the ONLY place the choice is made — callers must not
        re-derive it, which is what caused the two-competing-slug bug.
        """
        from .site import derive_legacy_store_id

        # Fast path: no site assigned -> never touch the relationship at all,
        # so this stays safe even on a detached/expired instance.
        if not self.site_id:
            return derive_legacy_store_id(self.location)
        try:
            site = self.site
        except Exception:  # noqa: BLE001  (not loaded / detached)
            site = None
        if site is not None and getattr(site, "slug", None):
            return site.slug
        return derive_legacy_store_id(self.location)

    # ------------------------------------------------------------------
    # RTSP URL encryption helpers
    # ------------------------------------------------------------------

    def set_rtsp_url(self, plaintext_url: str) -> None:
        """Encrypt *plaintext_url* and store in self.rtsp_url."""
        fernet = _get_fernet()
        if fernet is None:
            self.rtsp_url = plaintext_url
            return
        if plaintext_url.startswith(_FERNET_PREFIX):
            self.rtsp_url = plaintext_url  # already encrypted
            return
        token = fernet.encrypt(plaintext_url.encode()).decode()
        self.rtsp_url = f"{_FERNET_PREFIX}{token}"

    def get_rtsp_url(self) -> str | None:
        """Return the decrypted plaintext RTSP URL, or None if not set."""
        if self.rtsp_url is None:
            return None
        if not self.rtsp_url.startswith(_FERNET_PREFIX):
            return self.rtsp_url  # plaintext (legacy / no key)
        fernet = _get_fernet()
        if fernet is None:
            return self.rtsp_url  # cannot decrypt
        try:
            return fernet.decrypt(self.rtsp_url[len(_FERNET_PREFIX):].encode()).decode()
        except Exception:  # noqa: BLE001
            return self.rtsp_url

    @staticmethod
    def mask_rtsp(url: str | None) -> str | None:
        """Return a masked RTSP URL safe for API responses (hides credentials)."""
        if not url:
            return url
        # Redact user:pass@ portion
        return re.sub(r"(rtsp://)([^@]+@)", r"\1***@", url)
