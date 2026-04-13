"""
backend/services/email_service.py
===================================
Sends transactional emails via SMTP (Gmail, SendGrid SMTP, etc.).

Configure via environment variables:
    VANTAG_SMTP_HOST     default: smtp.gmail.com
    VANTAG_SMTP_PORT     default: 587
    VANTAG_SMTP_USER     your Gmail / SMTP username
    VANTAG_SMTP_PASS     your Gmail app-password or SMTP password
    VANTAG_EMAIL_FROM    display name + address, e.g. "Vantag <noreply@vantag.com>"
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import smtplib
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_SMTP_HOST = os.getenv("VANTAG_SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.getenv("VANTAG_SMTP_PORT", "587"))
_SMTP_USER = os.getenv("VANTAG_SMTP_USER", "")
_SMTP_PASS = os.getenv("VANTAG_SMTP_PASS", "")
_FROM_ADDR = os.getenv("VANTAG_EMAIL_FROM", "Vantag <noreply@vantag.com>")

_DEV_MODE = not _SMTP_USER  # If no SMTP user, log emails instead of sending


def is_dev_mode() -> bool:
    """Return True when SMTP is not configured (no credentials set)."""
    return _DEV_MODE


def generate_otp(length: int = 6) -> str:
    """Return a random numeric OTP string."""
    return "".join(random.choices(string.digits, k=length))


def _send_sync(to: str, subject: str, html: str, text: str) -> None:
    if _DEV_MODE:
        logger.info("📧 [DEV EMAIL] To: %s | Subject: %s\n%s", to, subject, text)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _FROM_ADDR
    msg["To"] = to
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=10) as s:
        s.ehlo()
        s.starttls()
        s.login(_SMTP_USER, _SMTP_PASS)
        s.sendmail(_FROM_ADDR, [to], msg.as_string())
    logger.info("Email sent to %s", to)


async def send_email(to: str, subject: str, html: str, text: str) -> None:
    """Send email in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _send_sync, to, subject, html, text)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)


# ── Templates ──────────────────────────────────────────────────────────────

def _base_html(title: str, body_html: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body style="margin:0;padding:0;background:#0a0a0f;font-family:sans-serif;color:#fff;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:40px 20px;">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#111827;border-radius:16px;border:1px solid rgba(255,255,255,0.08);">
        <tr>
          <td style="padding:32px 40px 0;text-align:center;">
            <div style="display:inline-flex;align-items:center;gap:10px;">
              <div style="width:36px;height:36px;background:linear-gradient(135deg,#7c3aed,#4f46e5);border-radius:10px;"></div>
              <span style="font-size:20px;font-weight:700;">Vantag</span>
            </div>
          </td>
        </tr>
        <tr><td style="padding:32px 40px 40px;">{body_html}</td></tr>
        <tr>
          <td style="padding:0 40px 32px;border-top:1px solid rgba(255,255,255,0.06);margin-top:32px;">
            <p style="color:rgba(255,255,255,0.3);font-size:12px;text-align:center;margin:24px 0 0;">
              Vantag Retail Security · Unsubscribe · Privacy Policy
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


async def send_verification_email(to: str, name: str, otp: str) -> None:
    subject = f"{otp} is your Vantag verification code"
    body = f"""
      <h2 style="font-size:24px;font-weight:700;margin:0 0 8px;">Verify your email</h2>
      <p style="color:rgba(255,255,255,0.5);margin:0 0 32px;">Hi {name}, welcome to Vantag! Enter this code to activate your account.</p>
      <div style="background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.3);border-radius:12px;padding:32px;text-align:center;margin-bottom:32px;">
        <span style="font-size:48px;font-weight:900;letter-spacing:12px;color:#a78bfa;">{otp}</span>
      </div>
      <p style="color:rgba(255,255,255,0.4);font-size:13px;">This code expires in <strong style="color:#fff;">10 minutes</strong>. If you didn't create a Vantag account, ignore this email.</p>
    """
    html = _base_html(subject, body)
    text = f"Your Vantag verification code is: {otp}\n\nExpires in 10 minutes."
    await send_email(to, subject, html, text)


async def send_trial_expiry_reminder(to: str, name: str, days_left: int, plan: str, pay_url: str) -> None:
    subject = f"Your Vantag trial ends in {days_left} day{'s' if days_left != 1 else ''}"
    body = f"""
      <h2 style="font-size:22px;font-weight:700;margin:0 0 8px;">Trial ending soon ⏰</h2>
      <p style="color:rgba(255,255,255,0.5);margin:0 0 24px;">Hi {name}, your {plan} trial ends in <strong style="color:#f59e0b;">{days_left} day{'s' if days_left != 1 else ''}</strong>. Upgrade now to keep your cameras protected.</p>
      <a href="{pay_url}" style="display:inline-block;background:linear-gradient(135deg,#7c3aed,#4f46e5);color:#fff;text-decoration:none;padding:14px 32px;border-radius:12px;font-weight:700;font-size:15px;">
        Upgrade Now →
      </a>
    """
    html = _base_html(subject, body)
    text = f"Your Vantag {plan} trial ends in {days_left} days. Upgrade: {pay_url}"
    await send_email(to, subject, html, text)


async def send_payment_success(to: str, name: str, plan: str, amount: str, invoice_no: str) -> None:
    subject = f"Payment confirmed — {invoice_no}"
    body = f"""
      <h2 style="font-size:22px;font-weight:700;margin:0 0 8px;">Payment confirmed ✅</h2>
      <p style="color:rgba(255,255,255,0.5);margin:0 0 24px;">Hi {name}, your <strong>{plan}</strong> subscription is active.</p>
      <div style="background:rgba(255,255,255,0.04);border-radius:12px;padding:20px;margin-bottom:24px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;"><span style="color:rgba(255,255,255,0.4);">Plan</span><span>{plan}</span></div>
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;"><span style="color:rgba(255,255,255,0.4);">Amount</span><span>{amount}</span></div>
        <div style="display:flex;justify-content:space-between;"><span style="color:rgba(255,255,255,0.4);">Invoice</span><span>{invoice_no}</span></div>
      </div>
    """
    html = _base_html(subject, body)
    text = f"Payment confirmed. Plan: {plan}. Amount: {amount}. Invoice: {invoice_no}."
    await send_email(to, subject, html, text)
