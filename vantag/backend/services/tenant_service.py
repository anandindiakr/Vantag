"""Tenant creation, plan management, and provisioning logic."""
from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.tenant import EdgeAgent, Tenant, TenantUser
from ..config.plans import get_plan


def _slugify(name: str) -> str:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:50]


def _make_api_key() -> str:
    alphabet = string.ascii_letters + string.digits
    return "vantag_" + "".join(secrets.choice(alphabet) for _ in range(40))


async def create_tenant(
    session: AsyncSession,
    *,
    name: str,
    email: str,
    hashed_password: str,
    country: str,
    phone: str | None = None,
    language: str = "en",
    plan_id: str = "starter",
) -> tuple[Tenant, TenantUser, str]:
    """
    Create a new tenant + owner user.
    Returns (tenant, user, onboarding_token).
    """
    slug_base = _slugify(name)
    # Ensure unique slug
    slug = slug_base
    counter = 1
    while True:
        existing = await session.execute(select(Tenant).where(Tenant.slug == slug))
        if not existing.scalar_one_or_none():
            break
        slug = f"{slug_base}-{counter}"
        counter += 1

    country_map = {"IN": "india", "SG": "singapore", "MY": "malaysia"}
    region = country_map.get(country.upper(), "india")

    plan = get_plan(plan_id)
    trial_days = plan["trial_days"] if plan else 14

    onboarding_token = secrets.token_urlsafe(32)

    tenant = Tenant(
        id=str(uuid.uuid4()),
        name=name,
        slug=slug,
        email=email,
        phone=phone,
        country=country.upper(),
        region=region,
        plan_id=plan_id,
        status="trial",
        language=language,
        onboarding_step=1,
        onboarding_token=onboarding_token,
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=trial_days),
    )
    session.add(tenant)
    await session.flush()  # get tenant.id

    user = TenantUser(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        email=email,
        hashed_password=hashed_password,
        role="owner",
        is_active=True,
    )
    session.add(user)
    await session.flush()

    return tenant, user, onboarding_token


async def provision_edge_agent(
    session: AsyncSession,
    tenant_id: str,
    device_type: str = "android",
    device_name: str | None = None,
) -> EdgeAgent:
    """Create and return a new edge agent with a fresh API key."""
    agent = EdgeAgent(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        device_type=device_type,
        device_name=device_name,
        api_key=_make_api_key(),
        status="offline",
    )
    session.add(agent)
    await session.flush()
    return agent


async def get_tenant_by_id(session: AsyncSession, tenant_id: str) -> Tenant | None:
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def get_tenant_cameras(session: AsyncSession, tenant_id: str) -> list:
    from ..db.models.camera import CameraConfig
    result = await session.execute(
        select(CameraConfig).where(CameraConfig.tenant_id == tenant_id)
    )
    return list(result.scalars().all())
