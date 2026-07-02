"""
backend/api/billing_router.py
==============================
Billing endpoints: create order, webhook handler, invoice listing.
"""
from __future__ import annotations

import json
import logging
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
from ..services import xendit_service
from ..config.plans import get_plan, get_plan_price
from ..config.regions import get_region

billing_router = APIRouter(prefix="/api/billing", tags=["billing"])
logger = logging.getLogger("vantag.billing")


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


async def _process_webhook_event(
    event_type: str,
    payload: dict,
    pe_id: str,
    session: AsyncSession,
) -> None:
    """Process a Razorpay webhook event and update tenant/invoice state."""
    data = payload.get("payload", {})

    try:
        # ── Payment captured / authorized → activate tenant + mark invoice paid ──
        if event_type in ("payment.captured", "payment.authorized"):
            payment = data.get("payment", {}).get("entity", {})
            order_id = payment.get("order_id")
            payment_id = payment.get("id")
            if order_id:
                inv_result = await session.execute(
                    select(Invoice).where(Invoice.razorpay_order_id == order_id)
                )
                inv = inv_result.scalar_one_or_none()
                if inv:
                    await session.execute(
                        update(Invoice)
                        .where(Invoice.id == inv.id)
                        .values(status="paid", razorpay_payment_id=payment_id)
                    )
                    await session.execute(
                        update(Tenant)
                        .where(Tenant.id == inv.tenant_id)
                        .values(status="active")
                    )
                    logger.info(
                        "Webhook payment.captured: activated tenant=%s order=%s",
                        inv.tenant_id, order_id,
                    )

        # ── Subscription renewed ──────────────────────────────────────────────
        elif event_type == "subscription.charged":
            sub_data = data.get("subscription", {}).get("entity", {})
            sub_id = sub_data.get("id")
            if sub_id:
                sub_result = await session.execute(
                    select(Subscription).where(Subscription.id == sub_id)
                )
                sub = sub_result.scalar_one_or_none()
                if sub:
                    await session.execute(
                        update(Tenant)
                        .where(Tenant.id == sub.tenant_id)
                        .values(status="active")
                    )

        # ── Subscription cancelled → suspend tenant ───────────────────────────
        elif event_type in ("subscription.cancelled", "subscription.completed"):
            sub_data = data.get("subscription", {}).get("entity", {})
            sub_id = sub_data.get("id")
            if sub_id:
                sub_result = await session.execute(
                    select(Subscription).where(Subscription.id == sub_id)
                )
                sub = sub_result.scalar_one_or_none()
                if sub:
                    await session.execute(
                        update(Tenant)
                        .where(Tenant.id == sub.tenant_id)
                        .values(status="suspended")
                    )
                    logger.info(
                        "Webhook %s: suspended tenant=%s", event_type, sub.tenant_id
                    )

        # ── Payment failed → mark invoice, log (don't immediately suspend) ────
        elif event_type == "payment.failed":
            payment = data.get("payment", {}).get("entity", {})
            order_id = payment.get("order_id")
            if order_id:
                await session.execute(
                    update(Invoice)
                    .where(Invoice.razorpay_order_id == order_id)
                    .values(status="failed")
                )
                logger.warning("Webhook payment.failed: order=%s", order_id)

        # Mark event as processed
        await session.execute(
            update(PaymentEvent).where(PaymentEvent.id == pe_id).values(processed=True)
        )
        await session.commit()

    except Exception as exc:
        logger.error("Webhook processing error for %s: %s", event_type, exc, exc_info=True)
        await session.rollback()


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

    payload = json.loads(body)
    event_type = payload.get("event", "unknown")
    event_id = payload.get("id") or payload.get("payload", {}).get("id")

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
        await session.rollback()
        return {"status": "duplicate_ignored", "event": event_type}

    # Process the event — update tenant/invoice state
    await _process_webhook_event(event_type, payload, pe.id, session)

    return {"received": True, "event": event_type}


class XenditOrderRequest(BaseModel):
    plan_id: str


@billing_router.post("/xendit-order")
async def create_xendit_order(
    body: XenditOrderRequest,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a Xendit invoice for the selected plan (PH/SG/MY)."""
    tenant_result = await session.execute(select(Tenant).where(Tenant.id == user["tenant_id"]))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    region = get_region(tenant.country)
    currency = region["currency"]
    amount = get_plan_price(body.plan_id, currency)
    if not amount:
        raise HTTPException(status_code=400, detail=f"Plan '{body.plan_id}' not available in {currency}")

    plan = get_plan(body.plan_id)
    external_id = f"vantag-{tenant.id}-{uuid.uuid4().hex[:8]}"
    base_domain = region.get("domain", "retail-vantag.com")

    result = await xendit_service.create_invoice(
        country=tenant.country,
        external_id=external_id,
        amount=amount,
        currency=currency,
        payer_email=user.get("email", ""),
        description=f"Vantag {plan['name']} — {region['name']}",
        success_redirect_url=f"https://{base_domain}/dashboard?payment=success",
        failure_redirect_url=f"https://{base_domain}/onboarding?payment=failed",
    )

    inv = Invoice(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        razorpay_order_id=external_id,  # reusing field as external_id for Xendit
        amount=amount,
        currency=currency,
        status="pending",
        invoice_number=f"INV-{uuid.uuid4().hex[:8].upper()}",
    )
    session.add(inv)
    await session.commit()

    return {**result, "invoice_id": inv.id}


@billing_router.post("/xendit-webhook/{country}")
async def xendit_webhook(
    country: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_callback_token: str = Header(None, alias="x-callback-token"),
) -> dict:
    """Xendit webhook handler for payment events (idempotent)."""
    body = await request.body()

    if not xendit_service.verify_webhook(country.upper(), x_callback_token or ""):
        raise HTTPException(status_code=400, detail="Invalid webhook token")

    payload = json.loads(body)
    event_type, event_id, _ = xendit_service.parse_webhook_event(payload)

    if event_id:
        existing = await session.execute(
            select(PaymentEvent).where(PaymentEvent.razorpay_event_id == event_id)
        )
        if existing.scalar_one_or_none():
            return {"status": "duplicate_ignored", "event": event_type}

    pe = PaymentEvent(
        id=str(uuid.uuid4()),
        event_type=f"xendit.{event_type}",
        razorpay_event_id=event_id,
        payload=payload,
        processed=False,
    )
    session.add(pe)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return {"status": "duplicate_ignored", "event": event_type}

    # Activate tenant on successful payment
    if event_type in ("PAID", "SETTLED"):
        external_id = payload.get("external_id") or payload.get("id")
        if external_id:
            inv_result = await session.execute(
                select(Invoice).where(Invoice.razorpay_order_id == external_id)
            )
            inv = inv_result.scalar_one_or_none()
            if inv:
                await session.execute(
                    update(Invoice).where(Invoice.id == inv.id).values(status="paid")
                )
                await session.execute(
                    update(Tenant).where(Tenant.id == inv.tenant_id).values(status="active")
                )
                logger.info("Xendit %s: activated tenant=%s", event_type, inv.tenant_id)

    await session.execute(
        update(PaymentEvent).where(PaymentEvent.id == pe.id).values(processed=True)
    )
    await session.commit()

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
