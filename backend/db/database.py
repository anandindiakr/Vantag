"""
backend/db/database.py
======================
SQLAlchemy async engine + session factory + base model.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Load .env from project root or backend/ (whichever exists) before reading env vars
try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve()
    for _candidate in (_here.parent.parent.parent / ".env", _here.parent.parent / ".env"):
        if _candidate.exists():
            load_dotenv(_candidate, override=False)
            break
except ImportError:
    pass

# Build async URL: convert postgresql:// → postgresql+asyncpg://
# Accept either DATABASE_URL (preferred) or POSTGRES_URL (legacy)
_raw_url: str = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or "postgresql://vantag:vantag_dev_pass@127.0.0.1:5432/vantag_db"
)
# Normalise scheme to asyncpg
if _raw_url.startswith("postgresql+asyncpg://"):
    DATABASE_URL = _raw_url
elif _raw_url.startswith("postgresql://"):
    DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = _raw_url

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables (used in development; production uses Alembic)."""
    # Import models so they register with Base.metadata before create_all
    from .models import tenant as _tenant  # noqa: F401
    from .models import camera as _camera  # noqa: F401
    from .models import event as _event  # noqa: F401
    from .models import billing as _billing  # noqa: F401
    from .models import admin as _admin  # noqa: F401
    from .models import partner as _partner  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent, additive column migration for auth security fields.
        # Postgres supports ADD COLUMN IF NOT EXISTS; safe to run every boot.
        _stmts = (
            "ALTER TABLE tenant_users ADD COLUMN IF NOT EXISTS otp_code_hash VARCHAR(128)",
            "ALTER TABLE tenant_users ADD COLUMN IF NOT EXISTS otp_expires_at TIMESTAMPTZ",
            "ALTER TABLE tenant_users ADD COLUMN IF NOT EXISTS otp_attempts INTEGER DEFAULT 0",
            "ALTER TABLE tenant_users ADD COLUMN IF NOT EXISTS pw_reset_jti VARCHAR(64)",
            "ALTER TABLE tenant_users ADD COLUMN IF NOT EXISTS pw_reset_expires_at TIMESTAMPTZ",
            "ALTER TABLE tenant_users ADD COLUMN IF NOT EXISTS token_version INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS alert_settings JSONB",
            "ALTER TABLE partners ADD COLUMN IF NOT EXISTS commission_rule_id VARCHAR(36) "
            "REFERENCES commission_rules(id) ON DELETE SET NULL",
        )
        for _sql in _stmts:
            try:
                await conn.exec_driver_sql(_sql)
            except Exception:  # noqa: BLE001
                pass

    # Seed default commission rules (from the Vantag Partner Distribution
    # Playbook) once — admin can edit/replace these from the Partner Admin
    # UI afterwards. Never overwrites existing rules.
    try:
        from .models.partner import CommissionRule
        from sqlalchemy import select as _select
        import uuid as _uuid_mod

        async with AsyncSessionLocal() as _session:
            existing = (await _session.execute(_select(CommissionRule.id).limit(1))).first()
            if not existing:
                defaults = [
                    # Fixed installer/dealer cut — flat 25% of MRP, all regions/plans.
                    dict(rule_type="fixed_pct", tier_name="Field Installer (Protected Cut)",
                         tier_min_streams=0, tier_max_streams=None, rate_pct=25.0),
                    # Distributor volume tiers (by cumulative active referred streams).
                    dict(rule_type="tiered_volume", tier_name="Tier 4 (Standard Base)",
                         tier_min_streams=0, tier_max_streams=999, rate_pct=5.0),
                    dict(rule_type="tiered_volume", tier_name="Tier 3 (Silver Scaler)",
                         tier_min_streams=1000, tier_max_streams=4999, rate_pct=10.0),
                    dict(rule_type="tiered_volume", tier_name="Tier 2 (Gold Volume)",
                         tier_min_streams=5000, tier_max_streams=24999, rate_pct=15.0),
                    dict(rule_type="tiered_volume", tier_name="Tier 1 (Elite Partner)",
                         tier_min_streams=25000, tier_max_streams=None, rate_pct=20.0),
                    # Flat lifetime referral commission (non-camera products / simple referrals).
                    dict(rule_type="flat_referral", tier_name="Strategic Referral Track",
                         tier_min_streams=0, tier_max_streams=None, rate_pct=20.0),
                ]
                for d in defaults:
                    _session.add(CommissionRule(id=str(_uuid_mod.uuid4()), **d))
                await _session.commit()
    except Exception:  # noqa: BLE001
        pass  # Non-fatal — admin can add rules manually if seeding fails
