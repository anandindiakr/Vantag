"""
backend/services/razorpay_service.py
=====================================
Razorpay integration for subscription billing.
Handles order creation, webhook verification, and subscription lifecycle.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from typing import Any

from ..config.plans import get_plan, get_plan_price
from ..config.regions import get_region

try:
    import razorpay
    _RAZORPAY_AVAILABLE = True
except ImportError:
    _RAZORPAY_AVAILABLE = False


def _get_client(country: str):
    if not _RAZORPAY_AVAILABLE:
        return None
    region = get_region(country)
    key_id = region.get("razorpay_key_id", "")
    key_secret = region.get("razorpay_key_secret", "")
    if not key_id or not key_secret:
        return None
    return razorpay.Client(auth=(key_id, key_secret))


def create_order(country: str, plan_id: str, tenant_id: str) -> dict[str, Any]:
    """Create a Razorpay order for a one-time or subscription payment."""
    region = get_region(country)
    currency = region["currency"]
    amount_unit = get_plan_price(plan_id, currency)
    amount_paise = int(amount_unit * 100)  # Razorpay uses smallest currency unit

    client = _get_client(country)
    if not client:
        # Test mode: return mock order
        return {
            "id": f"order_test_{uuid.uuid4().hex[:16]}",
            "amount": amount_paise,
            "currency": currency,
            "receipt": f"rcpt_{tenant_id[:8]}",
            "status": "created",
            "test_mode": True,
        }

    order = client.order.create({
        "amount": amount_paise,
        "currency": currency,
        "receipt": f"rcpt_{tenant_id[:8]}",
        "notes": {"tenant_id": tenant_id, "plan_id": plan_id},
    })
    return dict(order)


def verify_payment_signature(
    order_id: str,
    payment_id: str,
    signature: str,
    country: str,
) -> bool:
    """Verify Razorpay payment signature to prevent tampering."""
    region = get_region(country)
    key_secret = region.get("razorpay_key_secret", "")
    if not key_secret:
        return True  # test mode: skip verification

    body = f"{order_id}|{payment_id}"
    expected = hmac.new(key_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(payload: bytes, signature: str, country: str) -> bool:
    """Verify Razorpay webhook signature."""
    region = get_region(country)
    webhook_secret = os.getenv(f"RAZORPAY_WEBHOOK_SECRET_{country}", "")
    if not webhook_secret:
        return True
    expected = hmac.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


WEBHOOK_EVENT_HANDLERS = {
    "payment.captured": "handle_payment_captured",
    "subscription.activated": "handle_subscription_activated",
    "subscription.cancelled": "handle_subscription_cancelled",
    "payment.failed": "handle_payment_failed",
}
