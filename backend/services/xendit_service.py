"""
Xendit payment gateway service — Philippines, Singapore, Malaysia.
Xendit docs: https://developers.xendit.co/

ENV vars required (set in VPS .env once Xendit is approved):
  XENDIT_SECRET_KEY_PH=xnd_production_...   (Philippines)
  XENDIT_PUBLIC_KEY_PH=xnd_public_production_...
  XENDIT_WEBHOOK_TOKEN_PH=...

  XENDIT_SECRET_KEY_SG=...                   (Singapore — same account, different sub-account)
  XENDIT_PUBLIC_KEY_SG=...
  XENDIT_WEBHOOK_TOKEN_SG=...

  XENDIT_SECRET_KEY_MY=...                   (Malaysia)
  XENDIT_PUBLIC_KEY_MY=...
  XENDIT_WEBHOOK_TOKEN_MY=...
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import httpx

# ── Xendit base URLs ─────────────────────────────────────────────
XENDIT_API_BASE = "https://api.xendit.co"

# ── Per-country secret keys ──────────────────────────────────────
_SECRET_KEYS: dict[str, str] = {
    "PH": os.getenv("XENDIT_SECRET_KEY_PH", ""),
    "SG": os.getenv("XENDIT_SECRET_KEY_SG", ""),
    "MY": os.getenv("XENDIT_SECRET_KEY_MY", ""),
}

_WEBHOOK_TOKENS: dict[str, str] = {
    "PH": os.getenv("XENDIT_WEBHOOK_TOKEN_PH", ""),
    "SG": os.getenv("XENDIT_WEBHOOK_TOKEN_SG", ""),
    "MY": os.getenv("XENDIT_WEBHOOK_TOKEN_MY", ""),
}


def _secret(country: str) -> str:
    key = _SECRET_KEYS.get(country.upper(), "")
    if not key:
        raise ValueError(f"Xendit secret key not configured for country={country}")
    return key


# ── Create invoice (one-time payment) ───────────────────────────
async def create_invoice(
    *,
    country: str,
    external_id: str,
    amount: int | float,
    currency: str,
    payer_email: str,
    description: str,
    success_redirect_url: str = "",
    failure_redirect_url: str = "",
) -> dict[str, Any]:
    """
    Create a Xendit invoice. Customer pays via GCash / Maya / card / bank transfer.
    Returns Xendit invoice object including `invoice_url` to redirect the customer.

    Xendit docs: https://developers.xendit.co/api-reference/#create-invoice
    """
    payload: dict[str, Any] = {
        "external_id": external_id,
        "amount": amount,
        "currency": currency,
        "payer_email": payer_email,
        "description": description,
    }
    if success_redirect_url:
        payload["success_redirect_url"] = success_redirect_url
    if failure_redirect_url:
        payload["failure_redirect_url"] = failure_redirect_url

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{XENDIT_API_BASE}/v2/invoices",
            auth=(_secret(country), ""),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


# ── Create recurring plan ────────────────────────────────────────
async def create_subscription_plan(
    *,
    country: str,
    reference_id: str,
    interval: str = "MONTH",
    interval_count: int = 1,
    amount: int | float,
    currency: str,
    description: str,
) -> dict[str, Any]:
    """
    Create a Xendit recurring plan for monthly subscriptions.
    Returns plan object including `id` to store in plans.py.

    Xendit docs: https://developers.xendit.co/api-reference/#recurring-plans
    """
    payload: dict[str, Any] = {
        "reference_id": reference_id,
        "interval": interval,
        "interval_count": interval_count,
        "recurring_action": "PAYMENT",
        "currency": currency,
        "amount": amount,
        "description": description,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{XENDIT_API_BASE}/recurring/plans",
            auth=(_secret(country), ""),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


# ── Verify webhook signature ─────────────────────────────────────
def verify_webhook(country: str, callback_token: str) -> bool:
    """
    Xendit webhooks send x-callback-token header.
    Verify it matches the webhook token configured in Xendit dashboard.
    """
    expected = _WEBHOOK_TOKENS.get(country.upper(), "")
    if not expected:
        return False
    return hmac.compare_digest(callback_token.strip(), expected.strip())


# ── Parse webhook event ──────────────────────────────────────────
def parse_webhook_event(payload: dict[str, Any]) -> tuple[str, str, dict]:
    """
    Returns (event_type, external_id, data).

    Common event types:
      invoice.paid         — one-time payment captured
      recurring.payment.created — subscription charge succeeded
      recurring.payment.failed  — subscription charge failed
    """
    event_type = payload.get("event", payload.get("status", "unknown"))
    external_id = (
        payload.get("external_id")
        or payload.get("reference_id")
        or ""
    )
    return event_type, external_id, payload
