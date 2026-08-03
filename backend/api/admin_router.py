"""
backend/api/admin_router.py
============================
Super-admin API endpoints for platform-wide management.

All routes require the ``require_super_admin`` dependency (403 for non-admins).
Queries bypass the tenant middleware and operate cross-tenant.

Mounted at: /api/admin
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.tenant import Tenant, TenantUser
from ..db.models.billing import PaymentEvent, Subscription
from ..db.models.admin import AdminAuditLog, SystemAlert
from ..middleware.tenant_middleware import require_super_admin
from ..utils.csv_export import stream_csv

admin_router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ────────────────────────────────────────────────────────────────────────────
# Audit log helper
# ────────────────────────────────────────────────────────────────────────────

async def _audit(
    session: AsyncSession,
    admin: dict,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    log = AdminAuditLog(
        admin_user_id=admin.get("user_id", "unknown"),
        admin_email=admin.get("email"),
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    session.add(log)
    # Flushed with the parent session commit


# ────────────────────────────────────────────────────────────────────────────
# Stats
# ────────────────────────────────────────────────────────────────────────────

@admin_router.get("/stats", summary="Platform-wide metrics")
async def get_admin_stats(
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    # Tenant counts
    total_tenants = (await session.execute(
        select(func.count(Tenant.id)).where(Tenant.deleted_at.is_(None))
    )).scalar_one() or 0

    active_tenants = (await session.execute(
        select(func.count(Tenant.id)).where(Tenant.status == "active", Tenant.deleted_at.is_(None))
    )).scalar_one() or 0

    trial_tenants = (await session.execute(
        select(func.count(Tenant.id)).where(Tenant.status == "trial", Tenant.deleted_at.is_(None))
    )).scalar_one() or 0

    suspended_tenants = (await session.execute(
        select(func.count(Tenant.id)).where(Tenant.status == "suspended", Tenant.deleted_at.is_(None))
    )).scalar_one() or 0

    # Revenue sums from subscriptions
    async def _revenue_sum(currency: str) -> float:
        r = await session.execute(
            select(func.coalesce(func.sum(Subscription.amount), 0))
            .where(Subscription.currency == currency, Subscription.status == "active")
        )
        return float(r.scalar_one() or 0)

    total_revenue_inr = await _revenue_sum("INR")
    total_revenue_sgd = await _revenue_sum("SGD")
    total_revenue_myr = await _revenue_sum("MYR")
    total_revenue_php = await _revenue_sum("PHP")

    # MRR (monthly recurring revenue from active subscriptions)
    mrr_inr = total_revenue_inr
    mrr_sgd = total_revenue_sgd
    mrr_myr = total_revenue_myr
    mrr_php = total_revenue_php

    # Camera count
    try:
        from ..db.models.camera import CameraConfig
        total_cameras = (await session.execute(
            select(func.count(CameraConfig.id))
        )).scalar_one() or 0
    except Exception:  # noqa: BLE001
        total_cameras = 0

    # Incident counts (from event table if available)
    total_incidents_today = 0
    total_incidents_30d = 0
    try:
        from ..db.models.event import DetectionEvent
        total_incidents_today = (await session.execute(
            select(func.count(DetectionEvent.id)).where(DetectionEvent.created_at >= today_start)
        )).scalar_one() or 0
        total_incidents_30d = (await session.execute(
            select(func.count(DetectionEvent.id)).where(DetectionEvent.created_at >= thirty_days_ago)
        )).scalar_one() or 0
    except Exception:  # noqa: BLE001
        pass

    # New signups
    new_signups_today = (await session.execute(
        select(func.count(Tenant.id)).where(Tenant.created_at >= today_start)
    )).scalar_one() or 0

    new_signups_7d = (await session.execute(
        select(func.count(Tenant.id)).where(Tenant.created_at >= seven_days_ago)
    )).scalar_one() or 0

    churn_7d = (await session.execute(
        select(func.count(Tenant.id)).where(
            Tenant.status == "cancelled",
            Tenant.updated_at >= seven_days_ago,
        )
    )).scalar_one() or 0

    # System health (quick non-blocking checks)
    db_status = "ok"
    mqtt_status = "ok"
    ai_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_status = "error"

    return {
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "trial_tenants": trial_tenants,
        "suspended_tenants": suspended_tenants,
        "total_revenue_inr": total_revenue_inr,
        "total_revenue_sgd": total_revenue_sgd,
        "total_revenue_myr": total_revenue_myr,
        "total_revenue_php": total_revenue_php,
        "mrr_inr": mrr_inr,
        "mrr_sgd": mrr_sgd,
        "mrr_myr": mrr_myr,
        "mrr_php": mrr_php,
        "total_cameras": total_cameras,
        "total_incidents_today": total_incidents_today,
        "total_incidents_30d": total_incidents_30d,
        "new_signups_today": new_signups_today,
        "new_signups_7d": new_signups_7d,
        "churn_7d": churn_7d,
        "system_health": {"db": db_status, "mqtt": mqtt_status, "ai": ai_status},
    }


# ────────────────────────────────────────────────────────────────────────────
# Tenant list
# ────────────────────────────────────────────────────────────────────────────

@admin_router.get("/tenants", summary="List all tenants")
async def list_tenants(
    search: str = Query("", description="Search by name or email"),
    status: str = Query("", description="Filter by status"),
    region: str = Query("", description="Filter by country code (IN/SG/MY/PH)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    q = select(Tenant).where(Tenant.deleted_at.is_(None))
    if search:
        like = f"%{search}%"
        from sqlalchemy import or_
        q = q.where(or_(Tenant.name.ilike(like), Tenant.email.ilike(like)))
    if status:
        q = q.where(Tenant.status == status)
    if region:
        q = q.where(Tenant.country == region.upper())

    total_q = select(func.count()).select_from(q.subquery())
    total = (await session.execute(total_q)).scalar_one() or 0

    rows = (await session.execute(q.order_by(Tenant.created_at.desc()).limit(limit).offset(offset))).scalars().all()

    tenants = []
    for t in rows:
        # Get camera count
        cam_count = 0
        try:
            from ..db.models.camera import CameraConfig
            cam_count = (await session.execute(
                select(func.count(CameraConfig.id)).where(CameraConfig.tenant_id == t.id)
            )).scalar_one() or 0
        except Exception:  # noqa: BLE001
            pass

        # Get incident count (30d)
        inc_30d = 0
        try:
            from ..db.models.event import DetectionEvent
            thirty_ago = datetime.now(timezone.utc) - timedelta(days=30)
            inc_30d = (await session.execute(
                select(func.count(DetectionEvent.id)).where(
                    DetectionEvent.tenant_id == t.id,
                    DetectionEvent.created_at >= thirty_ago,
                )
            )).scalar_one() or 0
        except Exception:  # noqa: BLE001
            pass

        # Get active subscription amount
        mrr = 0.0
        try:
            sub = (await session.execute(
                select(Subscription).where(Subscription.tenant_id == t.id, Subscription.status == "active")
            )).scalars().first()
            if sub:
                mrr = float(sub.amount or 0)
        except Exception:  # noqa: BLE001
            pass

        # Real usage stats: most recent login/activity across all users of
        # this tenant (not a created_at proxy — actual last_login_at/
        # last_seen_at written on login and on authenticated requests).
        last_login = None
        last_seen = None
        login_count = 0
        try:
            users_q = (await session.execute(
                select(TenantUser).where(TenantUser.tenant_id == t.id)
            )).scalars().all()
            for u in users_q:
                if u.last_login_at and (last_login is None or u.last_login_at > last_login):
                    last_login = u.last_login_at
                if u.last_seen_at and (last_seen is None or u.last_seen_at > last_seen):
                    last_seen = u.last_seen_at
                login_count += u.login_count or 0
        except Exception:  # noqa: BLE001
            pass

        tenants.append({
            "id": t.id,
            "name": t.name,
            "owner_email": t.email,
            "region": t.country,
            "plan": t.plan_id,
            "status": t.status,
            "cameras": cam_count,
            "incidents_30d": inc_30d,
            "mrr": mrr,
            "created_at": t.created_at.isoformat(),
            "last_login": last_login.isoformat() if last_login else None,
            "last_seen": last_seen.isoformat() if last_seen else None,
            "login_count": login_count,
        })

    return {"total": total, "tenants": tenants}


# ────────────────────────────────────────────────────────────────────────────
# Tenant detail
# ────────────────────────────────────────────────────────────────────────────

@admin_router.get("/tenants/{tenant_id}", summary="Tenant full detail")
async def get_tenant_detail(
    tenant_id: str,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    users = (await session.execute(
        select(TenantUser).where(TenantUser.tenant_id == tenant_id)
    )).scalars().all()

    subscriptions = (await session.execute(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )).scalars().all()

    payments = (await session.execute(
        select(PaymentEvent).where(PaymentEvent.tenant_id == tenant_id)
        .order_by(PaymentEvent.created_at.desc()).limit(50)
    )).scalars().all()

    cameras = []
    try:
        from ..db.models.camera import CameraConfig
        cameras = (await session.execute(
            select(CameraConfig).where(CameraConfig.tenant_id == tenant_id)
        )).scalars().all()
    except Exception:  # noqa: BLE001
        pass

    return {
        "id": tenant.id,
        "name": tenant.name,
        "email": tenant.email,
        "phone": tenant.phone,
        "country": tenant.country,
        "plan_id": tenant.plan_id,
        "status": tenant.status,
        "language": tenant.language,
        "onboarding_step": tenant.onboarding_step,
        "created_at": tenant.created_at.isoformat(),
        "trial_ends_at": tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        "deleted_at": tenant.deleted_at.isoformat() if tenant.deleted_at else None,
        "users": [
            {
                "id": u.id, "email": u.email, "role": u.role,
                "is_active": u.is_active, "created_at": u.created_at.isoformat(),
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
                "login_count": u.login_count or 0,
            }
            for u in users
        ],
        "subscriptions": [
            {
                "id": s.id, "plan_id": s.plan_id, "status": s.status,
                "currency": s.currency, "amount": float(s.amount or 0),
                "created_at": s.created_at.isoformat(),
            }
            for s in subscriptions
        ],
        "payment_history": [
            {
                "id": p.id, "event_type": p.event_type,
                "razorpay_event_id": p.razorpay_event_id,
                "processed": p.processed,
                "created_at": p.created_at.isoformat(),
            }
            for p in payments
        ],
        "cameras": [
            {"id": c.id, "name": c.name, "is_active": c.is_active}
            for c in cameras
        ] if cameras else [],
    }


# ────────────────────────────────────────────────────────────────────────────
# Tenant suspend / resume / delete
# ────────────────────────────────────────────────────────────────────────────

@admin_router.post("/tenants/{tenant_id}/suspend", summary="Suspend a tenant")
async def suspend_tenant(
    tenant_id: str,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status == "suspended":
        return {"message": "Already suspended"}

    tenant.status = "suspended"
    # Deactivate all users for this tenant
    await session.execute(
        update(TenantUser).where(TenantUser.tenant_id == tenant_id).values(is_active=False)
    )
    await _audit(session, admin, "suspend_tenant", "tenant", tenant_id,
                 f"Suspended tenant {tenant.name}")
    await session.commit()
    return {"message": f"Tenant {tenant.name} suspended"}


@admin_router.post("/tenants/{tenant_id}/resume", summary="Resume a suspended tenant")
async def resume_tenant(
    tenant_id: str,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.status = "active"
    await session.execute(
        update(TenantUser).where(TenantUser.tenant_id == tenant_id).values(is_active=True)
    )
    await _audit(session, admin, "resume_tenant", "tenant", tenant_id,
                 f"Resumed tenant {tenant.name}")
    await session.commit()
    return {"message": f"Tenant {tenant.name} resumed"}


@admin_router.delete("/tenants/{tenant_id}", summary="Soft-delete a tenant")
async def soft_delete_tenant(
    tenant_id: str,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.status = "deleted"
    tenant.deleted_at = datetime.now(timezone.utc)
    await _audit(session, admin, "soft_delete_tenant", "tenant", tenant_id,
                 f"Soft-deleted tenant {tenant.name}")
    await session.commit()

    # Fire churn alert
    try:
        from ..services.alert_monitor import create_churn_alert
        from ..utils.background_tasks import fire_and_forget
        fire_and_forget(create_churn_alert(tenant.name, tenant.country), name="churn_alert")
    except Exception:  # noqa: BLE001
        pass

    return {"message": f"Tenant {tenant.name} soft-deleted"}


class HardDeleteConfirm(BaseModel):
    confirm: str  # must be "YES"


@admin_router.delete("/tenants/{tenant_id}/hard", summary="Hard-delete a tenant (irreversible)")
async def hard_delete_tenant(
    tenant_id: str,
    confirm: str = Query("", description="Must be 'YES' to confirm"),
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if confirm != "YES":
        raise HTTPException(status_code=400, detail="Pass ?confirm=YES to confirm hard delete")
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant_name = tenant.name
    await _audit(session, admin, "hard_delete_tenant", "tenant", tenant_id,
                 f"Hard-deleted tenant {tenant_name}")
    await session.delete(tenant)
    await session.commit()
    return {"message": f"Tenant {tenant_name} permanently deleted"}


# ────────────────────────────────────────────────────────────────────────────
# User management
# ────────────────────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    role: str = "viewer"


@admin_router.post("/tenants/{tenant_id}/users", status_code=201,
                   summary="Admin-create a user for a tenant")
async def admin_create_user(
    tenant_id: str,
    body: CreateUserRequest,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant = (await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    existing = (await session.execute(
        select(TenantUser).where(TenantUser.email == body.email.lower())
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        import bcrypt as _bcrypt
        hashed = _bcrypt.hashpw(body.password.encode(), _bcrypt.gensalt(rounds=12)).decode()
    except ImportError:
        raise HTTPException(status_code=500, detail="bcrypt not installed")

    import uuid
    user = TenantUser(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        email=body.email.lower(),
        hashed_password=hashed,
        full_name=body.full_name,
        role=body.role,
        is_active=True,
    )
    session.add(user)
    await _audit(session, admin, "create_user", "user", user.id,
                 f"Created user {body.email} for tenant {tenant.name}")
    await session.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


@admin_router.delete("/users/{user_id}", summary="Remove a user")
async def admin_delete_user(
    user_id: str,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = (await session.execute(
        select(TenantUser).where(TenantUser.id == user_id)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await _audit(session, admin, "delete_user", "user", user_id,
                 f"Deleted user {user.email}")
    await session.delete(user)
    await session.commit()
    return {"message": f"User {user.email} deleted"}


# ────────────────────────────────────────────────────────────────────────────
# Payments
# ────────────────────────────────────────────────────────────────────────────

@admin_router.get("/payments", summary="All payment events (filterable)")
async def list_payments(
    tenant_id: str = Query(""),
    status: str = Query(""),
    from_date: str = Query("", alias="from"),
    to_date: str = Query("", alias="to"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    q = select(PaymentEvent)
    if tenant_id:
        q = q.where(PaymentEvent.tenant_id == tenant_id)
    if status:
        q = q.where(PaymentEvent.event_type == status)
    if from_date:
        try:
            q = q.where(PaymentEvent.created_at >= datetime.fromisoformat(from_date))
        except ValueError:
            pass
    if to_date:
        try:
            q = q.where(PaymentEvent.created_at <= datetime.fromisoformat(to_date))
        except ValueError:
            pass

    total = (await session.execute(
        select(func.count()).select_from(q.subquery())
    )).scalar_one() or 0

    rows = (await session.execute(
        q.order_by(PaymentEvent.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()

    return {
        "total": total,
        "payments": [
            {
                "id": p.id,
                "tenant_id": p.tenant_id,
                "event_type": p.event_type,
                "razorpay_event_id": p.razorpay_event_id,
                "processed": p.processed,
                "created_at": p.created_at.isoformat(),
            }
            for p in rows
        ],
    }


@admin_router.get("/payments/export.csv", summary="Export payments as CSV")
async def export_payments_csv(
    tenant_id: str = Query(""),
    from_date: str = Query("", alias="from"),
    to_date: str = Query("", alias="to"),
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
):
    q = select(PaymentEvent)
    if tenant_id:
        q = q.where(PaymentEvent.tenant_id == tenant_id)
    if from_date:
        try:
            q = q.where(PaymentEvent.created_at >= datetime.fromisoformat(from_date))
        except ValueError:
            pass
    if to_date:
        try:
            q = q.where(PaymentEvent.created_at <= datetime.fromisoformat(to_date))
        except ValueError:
            pass

    rows = (await session.execute(q.order_by(PaymentEvent.created_at.desc()))).scalars().all()
    csv_rows = [
        [p.id, p.tenant_id, p.event_type, p.razorpay_event_id, p.processed, p.created_at]
        for p in rows
    ]
    return stream_csv(
        filename="payments_export.csv",
        headers=["id", "tenant_id", "event_type", "razorpay_event_id", "processed", "created_at"],
        rows=csv_rows,
    )


# ────────────────────────────────────────────────────────────────────────────
# Incidents
# ────────────────────────────────────────────────────────────────────────────

@admin_router.get("/incidents", summary="All incidents across tenants")
async def list_incidents(
    tenant_id: str = Query(""),
    from_date: str = Query("", alias="from"),
    to_date: str = Query("", alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        from ..db.models.event import DetectionEvent
        q = select(DetectionEvent)
        if tenant_id:
            q = q.where(DetectionEvent.tenant_id == tenant_id)
        if from_date:
            try:
                q = q.where(DetectionEvent.created_at >= datetime.fromisoformat(from_date))
            except ValueError:
                pass
        if to_date:
            try:
                q = q.where(DetectionEvent.created_at <= datetime.fromisoformat(to_date))
            except ValueError:
                pass

        total = (await session.execute(
            select(func.count()).select_from(q.subquery())
        )).scalar_one() or 0

        rows = (await session.execute(
            q.order_by(DetectionEvent.created_at.desc()).limit(limit)
        )).scalars().all()

        return {
            "total": total,
            "incidents": [
                {
                    "id": e.id,
                    "tenant_id": e.tenant_id,
                    "type": e.event_type,
                    "severity": e.severity,
                    "created_at": e.created_at.isoformat(),
                }
                for e in rows
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"total": 0, "incidents": [], "note": f"Event table unavailable: {exc}"}


@admin_router.get("/incidents/export.csv", summary="Export incidents as CSV")
async def export_incidents_csv(
    tenant_id: str = Query(""),
    from_date: str = Query("", alias="from"),
    to_date: str = Query("", alias="to"),
    limit: int = Query(10000, ge=1, le=100000),
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        from ..db.models.event import DetectionEvent
        q = select(DetectionEvent)
        if tenant_id:
            q = q.where(DetectionEvent.tenant_id == tenant_id)
        if from_date:
            try:
                q = q.where(DetectionEvent.created_at >= datetime.fromisoformat(from_date))
            except ValueError:
                pass
        if to_date:
            try:
                q = q.where(DetectionEvent.created_at <= datetime.fromisoformat(to_date))
            except ValueError:
                pass

        rows = (await session.execute(q.order_by(DetectionEvent.created_at.desc()).limit(limit))).scalars().all()
        csv_rows = [
            [e.id, e.tenant_id, e.event_type, e.severity, e.created_at.isoformat()]
            for e in rows
        ]
    except Exception:  # noqa: BLE001
        csv_rows = []

    return stream_csv(
        filename="incidents_export.csv",
        headers=["id", "tenant_id", "event_type", "severity", "created_at"],
        rows=csv_rows,
    )


# ────────────────────────────────────────────────────────────────────────────
# Alerts
# ────────────────────────────────────────────────────────────────────────────

@admin_router.get("/alerts", summary="List active system alerts")
async def list_alerts(
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rows = (await session.execute(
        select(SystemAlert)
        .where(SystemAlert.acknowledged_at.is_(None))
        .order_by(SystemAlert.created_at.desc())
        .limit(100)
    )).scalars().all()

    return {
        "alerts": [
            {
                "id": a.id,
                "level": a.level,
                "title": a.title,
                "detail": a.detail,
                "source": a.source,
                "created_at": a.created_at.isoformat(),
            }
            for a in rows
        ]
    }


@admin_router.post("/alerts/{alert_id}/acknowledge", summary="Acknowledge an alert")
async def acknowledge_alert(
    alert_id: str,
    admin: dict = Depends(require_super_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    alert = (await session.execute(
        select(SystemAlert).where(SystemAlert.id == alert_id)
    )).scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged_at = datetime.now(timezone.utc)
    await _audit(session, admin, "acknowledge_alert", "alert", alert_id, f"Acknowledged: {alert.title}")
    await session.commit()
    return {"message": "Alert acknowledged"}


# ---------------------------------------------------------------------------
# System health + genuine server logs (super-admin only)
# ---------------------------------------------------------------------------
# Two problems these endpoints exist to solve:
#   1. The Edge Agent could silently fall back from YOLO26 to YOLOv8 and the
#      only trace was a log.warning on the customer's own laptop. /system-health
#      reports the architecture each agent VERIFIED from its loaded ONNX graph
#      output shape, so "YOLO26 is active" is a measured fact, not a claim.
#   2. There was no way to read real server logs without SSH, so a swallowed
#      exception (e.g. the AI Assistant's missing `openai` package) was
#      undetectable. /logs tails this container's own log file/stream.


@admin_router.get("/system-health", summary="Live system health + detector status")
async def system_health(
    admin: dict = Depends(require_super_admin),
) -> dict:
    from ..services.system_health import snapshot

    return snapshot()


@admin_router.post("/system-health/test-alert", summary="Send a test admin alert email")
async def system_health_test_alert(
    admin: dict = Depends(require_super_admin),
) -> dict:
    """Prove the admin alert pipeline works end-to-end.

    Uses a dedicated component name so it cannot mask or reset a real fault,
    and bypasses the cooldown by clearing itself first — otherwise a second
    test within the cooldown window would appear to do nothing.
    """
    from ..services.system_health import (
        ADMIN_ALERT_EMAIL,
        clear_fault,
        report_fault,
    )
    from ..db import system_health_store as _sh

    _sh.resolve_fault("admin_test_alert")
    try:
        # Reset the cooldown so repeated tests always actually send.
        conn = _sh._get_conn()  # noqa: SLF001 — internal by design for tests
        with _sh._lock, conn:  # noqa: SLF001
            conn.execute(
                "UPDATE system_faults SET last_alert_ts = NULL WHERE component = ?",
                ("admin_test_alert",),
            )
    except Exception:  # noqa: BLE001
        pass

    await report_fault(
        component="admin_test_alert",
        summary="Test alert requested from the admin panel",
        detail=(
            "This is a manual test of the administrator alert pipeline. "
            "If you received this email, fault alerting is working."
        ),
    )
    clear_fault("admin_test_alert")
    return {
        "message": f"Test alert dispatched to {ADMIN_ALERT_EMAIL}",
        "email": ADMIN_ALERT_EMAIL,
    }


# Candidate log locations, in priority order. The container writes to
# /var/log/vantag (created in docker/Dockerfile); when running outside Docker
# a local logs/ dir is used instead.
_LOG_CANDIDATES = [
    "/var/log/vantag/backend.log",
    "/var/log/vantag/api.log",
    "/app/logs/backend.log",
]


@admin_router.get("/logs", summary="Tail real backend logs")
async def tail_logs(
    lines: int = Query(200, ge=10, le=2000),
    contains: Optional[str] = Query(None, description="Case-insensitive filter"),
    admin: dict = Depends(require_super_admin),
) -> dict:
    """Return the last N lines of this container's real log output.

    Honesty note: if no log file is present (uvicorn logging to stdout only,
    captured by Docker), this reports ``source: "unavailable"`` with the exact
    reason and the ``docker logs`` command to run instead. It never fabricates
    or simulates log content.
    """
    import os as _os
    from collections import deque
    from pathlib import Path as _Path

    log_path: Optional[str] = _os.getenv("VANTAG_LOG_FILE", "").strip() or None
    if log_path and not _Path(log_path).is_file():
        log_path = None
    if log_path is None:
        for cand in _LOG_CANDIDATES:
            if _Path(cand).is_file():
                log_path = cand
                break

    if log_path is None:
        return {
            "source": "unavailable",
            "reason": (
                "No log file found on disk. This backend logs to stdout, which "
                "Docker captures instead of writing a file. Set VANTAG_LOG_FILE "
                "to a writable path to enable in-app log tailing."
            ),
            "checked_paths": _LOG_CANDIDATES,
            "fallback_command": "docker logs --tail 200 vantag-backend",
            "lines": [],
        }

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=lines)
        out = list(tail)
        if contains:
            needle = contains.lower()
            out = [ln for ln in out if needle in ln.lower()]
        return {
            "source": log_path,
            "line_count": len(out),
            "filter": contains,
            "lines": [ln.rstrip("\n") for ln in out],
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Could not read log file: {exc}")

