"""
backend/db/seed_demo.py
=======================
Creates a demo tenant + user if they don't already exist.

Usage:
    python -m backend.db.seed_demo

Credentials created:
    email:    demo@vantag.io
    password: demo1234
    plan:     growth
    country:  IN
    onboarding_step: 6  →  lands directly on /dashboard
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    import bcrypt as _bcrypt
    def _hash(pw: str) -> str:
        return _bcrypt.hashpw(pw.encode(), _bcrypt.gensalt(12)).decode()
except ImportError:
    import hashlib
    def _hash(pw: str) -> str:
        return hashlib.sha256(pw.encode()).hexdigest()

from .database import AsyncSessionLocal, engine, Base, init_db
from .models.tenant import Tenant, TenantUser

DEMO_EMAIL    = "demo@vantag.io"
DEMO_PASSWORD = "demo1234"
DEMO_NAME     = "Vantag Demo Store"
DEMO_COUNTRY  = "IN"
DEMO_PLAN     = "growth"


async def seed() -> None:
    # Ensure tables exist (idempotent)
    await init_db()

    async with AsyncSessionLocal() as session:
        session: AsyncSession

        # ── Check existing user ─────────────────────────────────────────
        result = await session.execute(
            select(TenantUser).where(TenantUser.email == DEMO_EMAIL)
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            print(f"[seed_demo] Demo account already exists → {DEMO_EMAIL}")
            return

        # ── Create tenant ───────────────────────────────────────────────
        tenant_id = str(uuid.uuid4())
        tenant = Tenant(
            id=tenant_id,
            name=DEMO_NAME,
            slug="demo-store",
            email=DEMO_EMAIL,
            phone="+91-9999999999",
            country=DEMO_COUNTRY,
            region="india",
            plan_id=DEMO_PLAN,
            status="active",
            language="en",
            onboarding_step=6,       # skip onboarding → go to dashboard
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # ── Create user ─────────────────────────────────────────────────
        user = TenantUser(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            email=DEMO_EMAIL,
            hashed_password=_hash(DEMO_PASSWORD),
            full_name="Demo User",
            role="owner",
            is_active=True,
            is_email_verified=True,
        )

        session.add(tenant)
        session.add(user)
        await session.commit()

    print("=" * 55)
    print("[seed_demo] Demo account created successfully!")
    print(f"  Email    : {DEMO_EMAIL}")
    print(f"  Password : {DEMO_PASSWORD}")
    print(f"  Plan     : {DEMO_PLAN}")
    print(f"  Country  : {DEMO_COUNTRY}")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(seed())
