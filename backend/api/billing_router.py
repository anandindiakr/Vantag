"""
backend/api/billing_router.py
==============================
Billing endpoints: create order, webhook handler, invoice listing.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.billing import Invoice, PaymentEvent, Subscription
from ..db.models.tenant import Tenant
from ..middleware.tenant_middleware import get_current_user_id
from ..services.razorpay_service import create_order, verify_payment_signature, verify_webhook_signature

billing_router = APIRouter(prefix="/api/billing", tags=["billing"])


class CreateOrderRequest(BaseModel):
    plan_id: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@billing_router.post("/order")
async def create_payment_order(
    body: CreateOrderRequest,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a Razorpay order for the selected plan."""
    tenant_result = await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    order = create_order(tenant.country, body.plan_id, tenant.id)

    # Record pending invoice
    inv = Invoice(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        razorpay_order_id=order.get("id"),
        amount=order.get("amount", 0) / 100,
        currency=order.get("currency", "INR"),
        status="pending",
        invoice_number=f"INV-{uuid.uuid4().hex[:8].upper()}",
    )
    session.add(inv)
    await session.commit()

    return {**order, "invoice_id": inv.id}


@billing_router.post("/verify")
async def verify_payment(
    body: VerifyPaymentRequest,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Verify Razorpay signature and activate subscription."""
    tenant_result = await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    valid = verify_payment_signature(
        body.razorpay_order_id,
        body.razorpay_payment_id,
        body.razorpay_signature,
        tenant.country,
    )
    if not valid:
        raise HTTPException(status_code=400, detail="Payment verification failed")

    # Activate tenant
    await session.execute(
        update(Tenant).where(Tenant.id == tenant.id).values(status="active")
    )
    await session.execute(
        update(Invoice)
        .where(Invoice.razorpay_order_id == body.razorpay_order_id)
        .values(status="paid", razorpay_payment_id=body.razorpay_payment_id)
    )
    await session.commit()

    return {"success": True, "status": "active"}


@billing_router.post("/webhook/{country}")
async def razorpay_webhook(
    country: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_razorpay_signature: str = Header(None, alias="X-Razorpay-Signature"),
) -> dict:
    """Razorpay webhook handler for all payment events (idempotent)."""
    body = await request.body()

    if not verify_webhook_signature(body, x_razorpay_signature or "", country.upper()):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    import json
    payload = json.loads(body)
    event_type = payload.get("event", "unknown")

    # Extract idempotency key from Razorpay payload
    event_id = payload.get("id") or payload.get("payload", {}).get("id")

    # Check for duplicate event before inserting
    if event_id:
        existing = await session.execute(
            select(PaymentEvent).where(PaymentEvent.razorpay_event_id == event_id)
        )
        if existing.scalar_one_or_none():
            return {"status": "duplicate_ignored", "event": event_type}

    pe = PaymentEvent(
        id=str(uuid.uuid4()),
        event_type=event_type,
        razorpay_event_id=event_id,
        payload=payload,
        processed=False,
    )
    session.add(pe)
    try:
        await session.commit()
    except IntegrityError:
        # Race condition: another worker inserted the same event_id simultaneously
        await session.rollback()
        return {"status": "duplicate_ignored", "event": event_type}

    return {"received": True, "event": event_type}


@billing_router.get("/invoices")
async def list_invoices(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Invoice)
        .where(Invoice.tenant_id == user["tenant_id"])
        .order_by(Invoice.created_at.desc())
    )
    invoices = result.scalars().all()
    return {
        "invoices": [
            {
                "id": i.id,
                "amount": float(i.amount),
                "currency": i.currency,
                "status": i.status,
                "invoice_number": i.invoice_number,
                "created_at": i.created_at.isoformat(),
            }
            for i in invoices
        ]
    }
