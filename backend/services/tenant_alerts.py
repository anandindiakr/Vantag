"""
backend/services/tenant_alerts.py
==================================
Per-tenant alert dispatch: SMS / WhatsApp (Twilio) and Email, driven by the
`Tenant.alert_settings` JSONB column. This lets each shop owner configure
their own Twilio credentials and recipients directly from the Account >
Alert Dispatch settings page — no server-side YAML editing required.

This complements (does not replace) the global `backend/webhooks/webhook_engine.py`
which is driven by `webhooks.yaml` and is intended for platform-level/ops
subscriptions. `dispatch_tenant_alert()` is fired alongside it whenever an
edge event is ingested.

`alert_settings` JSONB schema (stored on `tenants.alert_settings`):
{
  "min_severity": "MEDIUM",             # LOW | MEDIUM | HIGH | CRITICAL
  "sms": {
      "enabled": true,
      "account_sid": "AC...",
      "auth_token": "...",
      "from_number": "+1XXXXXXXXXX",
      "to_number": "+91XXXXXXXXXX"
  },
  "whatsapp": {
      "enabled": true,
      "account_sid": "AC...",
      "auth_token": "...",
      "from_number": "+14155238886",     # Twilio WhatsApp sandbox/number
      "to_number": "+91XXXXXXXXXX"
  },
  "email": {
      "enabled": true,
      "to_email": "owner@shop.com"
  }
}
"""
from __future__ import annotations

import logging
from base64 import b64encode
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _rank(sev: str | None) -> int:
    return _SEVERITY_RANK.get(str(sev or "MEDIUM").upper(), 1)


def _format_body(incident: dict) -> str:
    event_type = str(incident.get("type") or incident.get("event_type") or "event").replace("_", " ").title()
    severity = str(incident.get("severity", "UNKNOWN")).upper()
    store_id = str(incident.get("store_id", "N/A"))
    camera_id = incident.get("camera_id", "N/A")
    timestamp = str(incident.get("timestamp") or datetime.now(tz=timezone.utc).isoformat())[:19].replace("T", " ")
    description = incident.get("description", "")
    return (
        f"[Retail Nazar - {severity}] {event_type}\n"
        f"Store: {store_id}\n"
        f"Camera: {camera_id}\n"
        f"Time: {timestamp} UTC\n"
        f"{description}"
    )[:1500]


async def _send_twilio(cfg: dict, body: str, whatsapp: bool) -> tuple[bool, str]:
    account_sid = (cfg.get("account_sid") or "").strip()
    auth_token = (cfg.get("auth_token") or "").strip()
    from_number = (cfg.get("from_number") or "").strip()
    to_number = (cfg.get("to_number") or "").strip()
    if not all([account_sid, auth_token, from_number, to_number]):
        return False, "Missing Twilio Account SID, Auth Token, From number, or To number."

    if whatsapp:
        if not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    credentials = b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    headers = {"Authorization": f"Basic {credentials}"}
    data = {"From": from_number, "To": to_number, "Body": body}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data=data, headers=headers)
        if resp.status_code in (200, 201):
            return True, "Message sent successfully."
        try:
            detail = resp.json().get("message", resp.text)
        except Exception:  # noqa: BLE001
            detail = resp.text
        return False, f"Twilio error ({resp.status_code}): {detail}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Twilio send failed")
        return False, f"Request failed: {exc}"


async def _send_alert_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    if not to_email:
        return False, "No recipient email configured."
    try:
        from . import email_service

        html = email_service._base_html(
            subject,
            f"<pre style='white-space:pre-wrap;font-family:monospace;color:#fff;font-size:14px;'>{body}</pre>",
        )
        await email_service.send_email(to_email, subject, html, body)
        if email_service.is_dev_mode():
            return True, (
                f"Email logged (SMTP not configured on server — check server logs). "
                f"Set VANTAG_SMTP_* env vars to actually deliver mail to {to_email}."
            )
        return True, f"Email sent to {to_email}."
    except Exception as exc:  # noqa: BLE001
        logger.exception("Alert email failed")
        return False, f"Failed to send email: {exc}"


async def send_test_alert(alert_settings: dict | None, channel: str) -> dict[str, Any]:
    """Send a one-off test alert for the given channel using tenant alert_settings.

    channel: "sms" | "whatsapp" | "email"
    Returns {"ok": bool, "message": str}
    """
    alert_settings = alert_settings or {}
    body = _format_body(
        {
            "type": "test_alert",
            "severity": "LOW",
            "store_id": "test-store",
            "camera_id": "test-camera",
            "description": "This is a test alert from your Retail Nazar Alert Dispatch settings. If you received this, your configuration is working correctly.",
        }
    )

    if channel in ("sms", "whatsapp"):
        cfg = alert_settings.get(channel) or {}
        ok, msg = await _send_twilio(cfg, body, whatsapp=(channel == "whatsapp"))
        return {"ok": ok, "message": msg}
    if channel == "email":
        cfg = alert_settings.get("email") or {}
        ok, msg = await _send_alert_email(cfg.get("to_email", ""), "Retail Nazar — Test Alert", body)
        return {"ok": ok, "message": msg}
    return {"ok": False, "message": f"Unknown channel: {channel}"}


async def dispatch_tenant_alert(alert_settings: dict | None, incident: dict) -> None:
    """Fire-and-forget dispatch of a live incident to the tenant's configured
    SMS / WhatsApp / Email channels, respecting per-tenant min_severity gating.
    Safe no-op when alert_settings is empty/None or no channel is enabled.
    """
    if not alert_settings:
        return
    min_sev = _rank(alert_settings.get("min_severity", "MEDIUM"))
    if _rank(incident.get("severity")) < min_sev:
        return

    body = _format_body(incident)

    sms_cfg = alert_settings.get("sms") or {}
    if sms_cfg.get("enabled"):
        try:
            ok, msg = await _send_twilio(sms_cfg, body, whatsapp=False)
            if not ok:
                logger.warning("Tenant SMS alert failed: %s", msg)
        except Exception:  # noqa: BLE001
            logger.exception("Tenant SMS alert dispatch error")

    wa_cfg = alert_settings.get("whatsapp") or {}
    if wa_cfg.get("enabled"):
        try:
            ok, msg = await _send_twilio(wa_cfg, body, whatsapp=True)
            if not ok:
                logger.warning("Tenant WhatsApp alert failed: %s", msg)
        except Exception:  # noqa: BLE001
            logger.exception("Tenant WhatsApp alert dispatch error")

    email_cfg = alert_settings.get("email") or {}
    if email_cfg.get("enabled") and email_cfg.get("to_email"):
        try:
            ok, msg = await _send_alert_email(
                email_cfg["to_email"], f"Retail Nazar Alert — {incident.get('type', 'event')}", body
            )
            if not ok:
                logger.warning("Tenant email alert failed: %s", msg)
        except Exception:  # noqa: BLE001
            logger.exception("Tenant email alert dispatch error")
