"""
backend/services/tenant_alerts.py
==================================
Per-tenant alert dispatch: SMS / WhatsApp / Email, driven by the
`Tenant.alert_settings` JSONB column. Each shop owner configures their own
provider credentials and recipients directly from the Account > Alert
Dispatch settings page — no server-side YAML editing required.

Multi-provider support (per-channel `provider` field, default "twilio"):

  SMS providers:
    - twilio      : account_sid, auth_token, from_number, to_number
    - msg91       : auth_key, sender_id, to_number          (India)
    - textlocal   : api_key, sender_id, to_number           (India)
    - vonage      : api_key, api_secret, from_number, to_number (global)
    - http        : url, method?, headers?, to_number        (generic gateway;
                    {to} and {message} placeholders in url/body)

  WhatsApp providers:
    - twilio      : account_sid, auth_token, from_number, to_number
    - meta        : phone_number_id, access_token, to_number (WhatsApp Cloud API)
    - gupshup     : api_key, source_number, app_name, to_number (India/global)
    - http        : url, method?, headers?, to_number        (generic gateway)

This complements (does not replace) the global `backend/webhooks/webhook_engine.py`
which is driven by `webhooks.yaml` and is intended for platform-level/ops
subscriptions. `dispatch_tenant_alert()` is fired alongside it whenever an
edge event is ingested.

`alert_settings` JSONB schema (stored on `tenants.alert_settings`):
{
  "min_severity": "MEDIUM",             # LOW | MEDIUM | HIGH | CRITICAL
  "sms":      { "enabled": true, "provider": "twilio", ...provider fields... },
  "whatsapp": { "enabled": true, "provider": "meta",   ...provider fields... },
  "email":    { "enabled": true, "to_email": "owner@shop.com" }
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


async def _http_post_json(url: str, *, headers: dict | None = None, json_body: dict | None = None,
                          data: dict | None = None) -> tuple[int, str]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers, json=json_body, data=data)
    return resp.status_code, resp.text


async def _send_msg91_sms(cfg: dict, body: str) -> tuple[bool, str]:
    """MSG91 (India) — transactional SMS via v2 sendsms API."""
    auth_key = (cfg.get("auth_key") or "").strip()
    sender_id = (cfg.get("sender_id") or "").strip() or "RTLNZR"
    to_number = (cfg.get("to_number") or "").strip().lstrip("+")
    if not all([auth_key, to_number]):
        return False, "Missing MSG91 Auth Key or To number."
    payload = {
        "sender": sender_id[:6],
        "route": "4",
        "country": "0",
        "sms": [{"message": body[:960], "to": [to_number]}],
    }
    try:
        status, text = await _http_post_json(
            "https://api.msg91.com/api/v2/sendsms",
            headers={"authkey": auth_key, "Content-Type": "application/json"},
            json_body=payload,
        )
        if status == 200 and '"type":"success"' in text.replace(" ", ""):
            return True, "SMS sent via MSG91."
        return False, f"MSG91 error ({status}): {text[:300]}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("MSG91 send failed")
        return False, f"Request failed: {exc}"


async def _send_textlocal_sms(cfg: dict, body: str) -> tuple[bool, str]:
    """Textlocal (India) — simple API-key SMS."""
    api_key = (cfg.get("api_key") or "").strip()
    sender_id = (cfg.get("sender_id") or "").strip() or "TXTLCL"
    to_number = (cfg.get("to_number") or "").strip().lstrip("+")
    if not all([api_key, to_number]):
        return False, "Missing Textlocal API Key or To number."
    try:
        status, text = await _http_post_json(
            "https://api.textlocal.in/send/",
            data={"apikey": api_key, "numbers": to_number, "sender": sender_id[:6], "message": body[:750]},
        )
        if status == 200 and '"status":"success"' in text.replace(" ", ""):
            return True, "SMS sent via Textlocal."
        return False, f"Textlocal error ({status}): {text[:300]}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Textlocal send failed")
        return False, f"Request failed: {exc}"


async def _send_vonage_sms(cfg: dict, body: str) -> tuple[bool, str]:
    """Vonage (Nexmo) — global SMS."""
    api_key = (cfg.get("api_key") or "").strip()
    api_secret = (cfg.get("api_secret") or "").strip()
    from_id = (cfg.get("from_number") or "").strip() or "RetailNazar"
    to_number = (cfg.get("to_number") or "").strip().lstrip("+")
    if not all([api_key, api_secret, to_number]):
        return False, "Missing Vonage API Key, API Secret, or To number."
    try:
        status, text = await _http_post_json(
            "https://rest.nexmo.com/sms/json",
            data={"api_key": api_key, "api_secret": api_secret, "from": from_id, "to": to_number, "text": body[:960]},
        )
        if status == 200 and ('"status": "0"' in text or '"status":"0"' in text.replace(" ", "")):
            return True, "SMS sent via Vonage."
        return False, f"Vonage error ({status}): {text[:300]}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Vonage send failed")
        return False, f"Request failed: {exc}"


async def _send_meta_whatsapp(cfg: dict, body: str) -> tuple[bool, str]:
    """WhatsApp Business Cloud API (Meta) — official, no Twilio needed.

    Note: free-form text messages only deliver inside an open 24-hour customer
    session; otherwise an approved template is required. For alerting to your
    own phone, send yourself a message to the business number first to open
    the session, or register a template.
    """
    phone_number_id = (cfg.get("phone_number_id") or "").strip()
    access_token = (cfg.get("access_token") or "").strip()
    to_number = (cfg.get("to_number") or "").strip().lstrip("+")
    if not all([phone_number_id, access_token, to_number]):
        return False, "Missing Meta Phone Number ID, Access Token, or To number."
    try:
        status, text = await _http_post_json(
            f"https://graph.facebook.com/v19.0/{phone_number_id}/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            json_body={
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "text",
                "text": {"body": body[:4000]},
            },
        )
        if status == 200:
            return True, "WhatsApp message sent via Meta Cloud API. (If not received: message your business number once from your phone to open the 24h session, then retry.)"
        return False, f"Meta Cloud API error ({status}): {text[:300]}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Meta WhatsApp send failed")
        return False, f"Request failed: {exc}"


async def _send_gupshup_whatsapp(cfg: dict, body: str) -> tuple[bool, str]:
    """Gupshup WhatsApp API (popular in India)."""
    api_key = (cfg.get("api_key") or "").strip()
    source = (cfg.get("source_number") or "").strip().lstrip("+")
    app_name = (cfg.get("app_name") or "").strip()
    to_number = (cfg.get("to_number") or "").strip().lstrip("+")
    if not all([api_key, source, to_number]):
        return False, "Missing Gupshup API Key, Source number, or To number."
    import json as _json
    try:
        status, text = await _http_post_json(
            "https://api.gupshup.io/wa/api/v1/msg",
            headers={"apikey": api_key},
            data={
                "channel": "whatsapp",
                "source": source,
                "destination": to_number,
                "src.name": app_name or source,
                "message": _json.dumps({"type": "text", "text": body[:4000]}),
            },
        )
        if status in (200, 202):
            return True, "WhatsApp message submitted via Gupshup."
        return False, f"Gupshup error ({status}): {text[:300]}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Gupshup send failed")
        return False, f"Request failed: {exc}"


async def _send_generic_http(cfg: dict, body: str) -> tuple[bool, str]:
    """Generic HTTP gateway — works with almost any local telecom/SMS/WhatsApp
    provider that exposes an HTTP API. Use {to} and {message} placeholders in
    the URL or request body template. Example (GET):
      https://sms.myprovider.com/send?key=XXXX&to={to}&text={message}
    """
    url = (cfg.get("url") or "").strip()
    to_number = (cfg.get("to_number") or "").strip()
    method = (cfg.get("method") or "GET").strip().upper()
    body_template = cfg.get("body_template") or ""
    headers_raw = cfg.get("headers") or {}
    if not url:
        return False, "Missing gateway URL."
    from urllib.parse import quote
    url_final = url.replace("{to}", quote(to_number)).replace("{message}", quote(body[:960]))
    headers = headers_raw if isinstance(headers_raw, dict) else {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if method == "POST":
                content = body_template.replace("{to}", to_number).replace("{message}", body[:960])
                if content.lstrip().startswith("{"):
                    headers.setdefault("Content-Type", "application/json")
                resp = await client.post(url_final, content=content or None, headers=headers)
            else:
                resp = await client.get(url_final, headers=headers)
        if 200 <= resp.status_code < 300:
            return True, f"Gateway accepted the message (HTTP {resp.status_code})."
        return False, f"Gateway error ({resp.status_code}): {resp.text[:300]}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Generic HTTP gateway send failed")
        return False, f"Request failed: {exc}"


async def _send_sms(cfg: dict, body: str) -> tuple[bool, str]:
    provider = str(cfg.get("provider") or "twilio").lower()
    if provider == "twilio":
        return await _send_twilio(cfg, body, whatsapp=False)
    if provider == "msg91":
        return await _send_msg91_sms(cfg, body)
    if provider == "textlocal":
        return await _send_textlocal_sms(cfg, body)
    if provider == "vonage":
        return await _send_vonage_sms(cfg, body)
    if provider == "http":
        return await _send_generic_http(cfg, body)
    return False, f"Unknown SMS provider: {provider}"


async def _send_whatsapp(cfg: dict, body: str) -> tuple[bool, str]:
    provider = str(cfg.get("provider") or "twilio").lower()
    if provider == "twilio":
        return await _send_twilio(cfg, body, whatsapp=True)
    if provider == "meta":
        return await _send_meta_whatsapp(cfg, body)
    if provider == "gupshup":
        return await _send_gupshup_whatsapp(cfg, body)
    if provider == "http":
        return await _send_generic_http(cfg, body)
    return False, f"Unknown WhatsApp provider: {provider}"


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
        if channel == "sms":
            ok, msg = await _send_sms(cfg, body)
        else:
            ok, msg = await _send_whatsapp(cfg, body)
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
            ok, msg = await _send_sms(sms_cfg, body)
            if not ok:
                logger.warning("Tenant SMS alert failed: %s", msg)
        except Exception:  # noqa: BLE001
            logger.exception("Tenant SMS alert dispatch error")

    wa_cfg = alert_settings.get("whatsapp") or {}
    if wa_cfg.get("enabled"):
        try:
            ok, msg = await _send_whatsapp(wa_cfg, body)
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
