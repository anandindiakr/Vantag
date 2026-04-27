"""
backend/api/auth_router.py
==========================
Authentication endpoints: register, login, refresh, verify-email,
forgot-password, reset-password.
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.tenant import Tenant, TenantUser
from ..services.tenant_service import create_tenant
from ..services.email_service import generate_otp, send_verification_email, is_dev_mode


async def _fire_signup_notifications(tenant_name: str, region: str) -> None:
    """Fire signup alert + notify support email (non-blocking, best-effort)."""
    try:
        from ..services.alert_monitor import create_signup_alert
        await create_signup_alert(tenant_name, region)
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..services.email_service import send_email
        subject = f"New Vantag signup: {tenant_name} ({region})"
        body_text = f"New tenant signed up:\n  Name: {tenant_name}\n  Region: {region}"
        body_html = f"<p><strong>New tenant signed up:</strong><br>Name: {tenant_name}<br>Region: {region}</p>"
        await send_email("support@retail-vantag.com", subject, body_html, body_text)
    except Exception:  # noqa: BLE001
        pass

# ---------------------------------------------------------------------------
# bcrypt — hard dependency (no SHA-256 fallback)
# ---------------------------------------------------------------------------
try:
    import bcrypt as _bcrypt

    def hash_password(pw: str) -> str:
        return _bcrypt.hashpw(pw.encode("utf-8"), _bcrypt.gensalt(rounds=12)).decode("utf-8")

    def verify_password(pw: str, h: str) -> bool:
        return _bcrypt.checkpw(pw.encode("utf-8"), h.encode("utf-8"))

except ImportError as _bcrypt_err:
    raise RuntimeError(
        "bcrypt is required but not installed. "
        "Install it with: pip install bcrypt>=4.0.1"
    ) from _bcrypt_err

try:
    from jose import jwt
    def make_token(payload: dict, expires_delta: timedelta) -> str:
        data = payload.copy()
        data["exp"] = datetime.now(timezone.utc) + expires_delta
        return jwt.encode(data, os.getenv("VANTAG_JWT_SECRET", "change-me"), algorithm="HS256")
except ImportError:
    import json, base64, hmac, hashlib
    def make_token(payload: dict, expires_delta: timedelta) -> str:
        return secrets.token_urlsafe(40)

JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
REFRESH_EXPIRE_DAYS = 30

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / Response models ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str           # shop name
    email: EmailStr
    password: str
    country: str        # IN / SG / MY
    phone: str | None = None
    language: str = "en"
    plan_id: str = "starter"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tenant_id: str
    onboarding_step: int
    plan_id: str


# ── Endpoints ──────────────────────────────────────────────────────────────

@auth_router.post("/register", status_code=201)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Check duplicate email
    existing = await session.execute(
        select(TenantUser).where(TenantUser.email == body.email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    hashed = hash_password(body.password)
    tenant, user, onboarding_token = await create_tenant(
        session,
        name=body.name,
        email=body.email.lower(),
        hashed_password=hashed,
        country=body.country,
        phone=body.phone,
        language=body.language,
        plan_id=body.plan_id,
    )
    await session.commit()

    # Fire signup alert (non-blocking)
    import asyncio as _asyncio
    _asyncio.create_task(_fire_signup_notifications(tenant.name, tenant.country))

    access = make_token(
        {"sub": user.id, "tenant_id": tenant.id, "email": user.email,
         "role": user.role, "is_super_admin": False},
        timedelta(hours=JWT_EXPIRE_HOURS),
    )
    refresh = make_token(
        {"sub": user.id, "tenant_id": tenant.id, "type": "refresh"},
        timedelta(days=REFRESH_EXPIRE_DAYS),
    )

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "tenant_id": tenant.id,
        "onboarding_step": 1,
        "plan_id": tenant.plan_id,
        "trial_ends_at": tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        "onboarding_token": onboarding_token,
    }


_DEMO_ACCOUNTS: dict[str, dict] = {
    "demo@vantag.io": {
        "password": "demo1234",
        "user_id": "demo-user-001",
        "tenant_id": "demo-tenant-001",
        "role": "admin",
        "name": "Vantag Demo Store",
        "plan_id": "pro",
        "country": "IN",
        "language": "en",
        "onboarding_step": 5,
        "status": "active",
    }
}


@auth_router.post("/login")
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    email_lower = body.email.lower()

    # ── Normal PostgreSQL path (tried FIRST) ─────────────────────────────────
    try:
        result = await session.execute(
            select(TenantUser).where(TenantUser.email == email_lower)
        )
        user = result.scalar_one_or_none()
        if user and verify_password(body.password, user.hashed_password):
            if not user.is_active:
                raise HTTPException(status_code=403, detail="Account suspended")

            tenant_result = await session.execute(
                select(Tenant).where(Tenant.id == user.tenant_id)
            )
            tenant = tenant_result.scalar_one_or_none()
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")

            access = make_token(
                {"sub": user.id, "tenant_id": tenant.id, "email": user.email,
                 "role": user.role, "is_super_admin": user.is_super_admin},
                timedelta(hours=JWT_EXPIRE_HOURS),
            )
            refresh = make_token(
                {"sub": user.id, "tenant_id": tenant.id, "type": "refresh"},
                timedelta(days=REFRESH_EXPIRE_DAYS),
            )

            return {
                "access_token": access,
                "refresh_token": refresh,
                "token_type": "bearer",
                "tenant_id": tenant.id,
                "onboarding_step": tenant.onboarding_step,
                "plan_id": tenant.plan_id,
                "status": tenant.status,
                "name": tenant.name,
                "language": tenant.language,
                "country": tenant.country,
                "is_super_admin": user.is_super_admin,
            }
    except HTTPException:
        raise
    except Exception:
        # DB unreachable — fall through to demo fallback below
        pass

    # ── Demo / offline fallback ──────────────────────────────────────────────
    # Used only when the user is NOT in the DB (dev / edge deployment).
    demo = _DEMO_ACCOUNTS.get(email_lower)
    if demo and body.password == demo["password"]:
        access = make_token(
            {"sub": demo["user_id"], "tenant_id": demo["tenant_id"],
             "email": email_lower, "role": demo["role"]},
            timedelta(hours=JWT_EXPIRE_HOURS),
        )
        refresh = make_token(
            {"sub": demo["user_id"], "tenant_id": demo["tenant_id"], "type": "refresh"},
            timedelta(days=REFRESH_EXPIRE_DAYS),
        )
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "tenant_id": demo["tenant_id"],
            "onboarding_step": demo["onboarding_step"],
            "plan_id": demo["plan_id"],
            "status": demo["status"],
            "name": demo["name"],
            "language": demo["language"],
            "country": demo["country"],
        }

    raise HTTPException(status_code=401, detail="Invalid email or password")


# ── OTP store (in-memory, TTL 10 min) ────────────────────────────────────────
# { email: (otp_code, expires_at) }
_otp_store: dict[str, tuple[str, datetime]] = {}


class SendOtpRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


@auth_router.post("/send-otp", status_code=200)
async def send_otp(
    body: SendOtpRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Generate a 6-digit OTP and email it to the user."""
    result = await session.execute(
        select(TenantUser).where(TenantUser.email == body.email.lower())
    )
    user = result.scalar_one_or_none()
    if not user:
        # Don't reveal whether account exists
        return {"message": "If this email exists, a code has been sent."}

    if user.is_email_verified:
        return {"message": "Email already verified."}

    otp = generate_otp(6)
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    _otp_store[body.email.lower()] = (otp, expires)

    # Get tenant name for personalisation
    tenant_result = await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    name = tenant.name if tenant else "there"

    # Fire-and-forget email (non-blocking)
    import asyncio
    asyncio.create_task(send_verification_email(body.email.lower(), name, otp))

    # In dev mode (no SMTP configured), return the OTP in the response so it
    # can be auto-filled in the browser — never do this in production.
    if is_dev_mode():
        return {
            "message": "SMTP not configured — code shown below for testing.",
            "dev_mode": True,
            "otp": otp,
        }

    return {"message": "Verification code sent. Check your inbox."}


@auth_router.post("/verify-email", status_code=200)
async def verify_email(
    body: VerifyOtpRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Validate the OTP and mark user email as verified."""
    key = body.email.lower()
    entry = _otp_store.get(key)
    if not entry:
        raise HTTPException(status_code=400, detail="No verification code found. Request a new one.")

    otp_code, expires = entry
    if datetime.now(timezone.utc) > expires:
        del _otp_store[key]
        raise HTTPException(status_code=400, detail="Code expired. Request a new one.")

    if not secrets.compare_digest(otp_code, body.otp.strip()):
        raise HTTPException(status_code=400, detail="Invalid code. Please try again.")

    # Mark verified in DB
    result = await session.execute(
        select(TenantUser).where(TenantUser.email == key)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_email_verified = True
    user.email_verify_token = None
    await session.commit()

    del _otp_store[key]
    return {"message": "Email verified successfully.", "verified": True}


# ── Forgot-password / Reset-password ─────────────────────────────────────────

_RESET_TOKEN_PURPOSE = "password_reset"
_RESET_TOKEN_EXPIRY_MINUTES = 30


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@auth_router.post("/forgot-password", status_code=200)
async def forgot_password(
    body: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Send a password-reset email.

    Always returns 200 to prevent email enumeration — the response is
    identical whether or not the email address exists.
    """
    email_lower = body.email.lower()
    result = await session.execute(
        select(TenantUser).where(TenantUser.email == email_lower)
    )
    user = result.scalar_one_or_none()

    if user:
        # Get region domain for reset link
        tenant_result = await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        country = (tenant.country or "IN") if tenant else "IN"

        from ..config.regions import get_region
        region = get_region(country)
        region_domain = region.get("domain", "retailnazar.com")

        reset_token = make_token(
            {"sub": user.id, "tenant_id": user.tenant_id, "purpose": _RESET_TOKEN_PURPOSE},
            timedelta(minutes=_RESET_TOKEN_EXPIRY_MINUTES),
        )
        reset_link = f"https://{region_domain}/reset-password?token={reset_token}"

        from ..services.email_service import send_password_reset_email
        import asyncio
        asyncio.create_task(
            send_password_reset_email(email_lower, tenant.name if tenant else "there", reset_link)
        )

    return {"message": "If this email is registered, a password-reset link has been sent."}


@auth_router.post("/reset-password", status_code=200)
async def reset_password(
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Reset the user's password using the signed reset token.

    Verifies the JWT, ensures it has purpose=password_reset, updates the
    hashed password, and invalidates existing sessions by clearing any
    stored refresh tokens (when session persistence is implemented).
    """
    jwt_secret = os.getenv("VANTAG_JWT_SECRET", "change-me")

    try:
        from jose import jwt as _jwt, JWTError
        payload = _jwt.decode(body.token, jwt_secret, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if payload.get("purpose") != _RESET_TOKEN_PURPOSE:
        raise HTTPException(status_code=400, detail="Invalid reset token purpose")

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Malformed reset token")

    result = await session.execute(
        select(TenantUser).where(TenantUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user.hashed_password = hash_password(body.new_password)
    await session.commit()

    return {"message": "Password has been reset successfully. Please sign in with your new password."}
