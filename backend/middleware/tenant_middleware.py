"""
Tenant middleware — extracts tenant_id from JWT and injects into request.state.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from jose import JWTError, jwt
except ImportError:
    from jwt import decode as jwt_decode, exceptions as JWTError

# DB imports are safe here — database.py does NOT import from middleware
from ..db.database import AsyncSessionLocal, get_session
from ..db.models.tenant import Tenant, TenantUser

JWT_SECRET = os.getenv("VANTAG_JWT_SECRET", "change-me")
JWT_ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_tenant_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = _decode_token(credentials.credentials)
    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return tenant_id


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = _decode_token(credentials.credentials)
    user_id = payload.get("sub")

    # Session-epoch enforcement: if the token carries a version claim, it must
    # match the user's current token_version in the DB. A password reset bumps
    # token_version, which instantly invalidates every previously issued token.
    token_ver = payload.get("ver")
    if token_ver is not None and user_id:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TenantUser.token_version).where(TenantUser.id == user_id)
            )
            current_ver = result.scalar_one_or_none()
        if current_ver is not None and int(current_ver) != int(token_ver):
            raise HTTPException(
                status_code=401,
                detail="Session expired. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return {
        "user_id": user_id,
        "tenant_id": payload.get("tenant_id"),
        "role": payload.get("role", "viewer"),
        "email": payload.get("email"),
        "is_super_admin": bool(payload.get("is_super_admin", False)),
    }


async def require_admin(user: dict = Depends(get_current_user_id)) -> dict:
    if user.get("role") not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_super_admin(user: dict = Depends(get_current_user_id)) -> dict:
    """Dependency that only allows super-admin users (platform owners)."""
    if not user.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Super-admin access required")
    return user


async def get_optional_tenant_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[str]:
    if not credentials:
        return None
    try:
        payload = _decode_token(credentials.credentials)
        return payload.get("tenant_id")
    except Exception:
        return None


async def require_active_tenant(
    user: dict = Depends(get_current_user_id),
) -> dict:
    """
    Blocks API access when the tenant's subscription is inactive or expired.

    Raises HTTP 402 with detail="subscription_required" when:
    - tenant.status is not "active" or "trial"
    - tenant.status == "trial" AND trial_ends_at is in the past

    Super-admins bypass this check entirely.
    """
    # Super-admins always pass
    if user.get("is_super_admin"):
        return user

    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    now = datetime.now(timezone.utc)

    if tenant.status == "active":
        return user

    if tenant.status == "trial":
        if tenant.trial_ends_at is None:
            # No expiry set — block access; trial_ends_at must always be set
            raise HTTPException(
                status_code=402,
                detail="subscription_required",
                headers={"X-Subscription-Status": "trial_expired"},
            )
        trial_end = tenant.trial_ends_at
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        if trial_end > now:
            return user
        raise HTTPException(
            status_code=402,
            detail="subscription_required",
            headers={"X-Subscription-Status": "trial_expired"},
        )

    # Suspended, cancelled, or any other non-active status
    raise HTTPException(
        status_code=402,
        detail="subscription_required",
        headers={"X-Subscription-Status": tenant.status or "suspended"},
    )
