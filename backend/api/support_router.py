"""
support_router.py
=================
Smart AI support chat endpoint backed by OpenAI GPT-4o.

- Reads OPENAI_API_KEY from env (set in .env on VPS)
- If key is missing or OpenAI fails, returns a graceful fallback pointing
  to support@retail-vantag.com
- System prompt teaches the AI everything about Vantag (product, features,
  pricing, protocols, networking, CCTV, security)
"""
from __future__ import annotations

import os
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

support_router = APIRouter(prefix="/api/support", tags=["support"])

SUPPORT_EMAIL = "support@retail-vantag.com"

# ─── Vantag Knowledge Base (burned into the system prompt) ─────────────────
VANTAG_SYSTEM_PROMPT = """You are Vantag Assistant — the official AI support agent for Vantag
(also branded as "Retail Nazar" in India and "JagaJaga" in Malaysia).

# What Vantag is
Vantag is a hardware-agnostic Retail Security & Predictive Analytics SaaS platform
for small-to-mid retailers (2–30 cameras per store). It connects to generic
IP cameras over RTSP, runs AI on a local Edge Agent, and sends events +
snapshots to the Vantag cloud dashboard.

# Core features
- Product Sweeping (theft) detection
- Anomalous Dwell Time (loitering)
- Empty Shelf Detection (inventory visibility)
- Fall Detection
- Queue Length monitoring
- Camera Tampering detection
- Inventory Movement tracking
- No-Entry Zone alerts
- One-Tap Door Lock via MQTT
- Real-time zone risk scores
- Evidence snapshots for every incident
- 15–30 day history retention

# Architecture
- Cloud: FastAPI + PostgreSQL + Mosquitto MQTT on a VPS (Hostinger)
- Frontend: React + Vite + TailwindCSS + i18n (12 languages)
- Edge Agent: lightweight Python app installed on retailer's PC/tablet/Pi
  that scans LAN for cameras (RTSP port 554) and relays events to cloud
- Video never leaves the customer LAN — only events + snapshots are uploaded

# Pricing (suggested, market-appropriate)
- India: Starter ₹999/mo (2 cam), Growth ₹2,499/mo (10 cam), Pro ₹4,999/mo (30 cam)
- Singapore: Starter S$29/mo, Growth S$69/mo, Pro S$129/mo
- Malaysia: Starter RM49/mo, Growth RM129/mo, Pro RM249/mo
- Payment: Razorpay (all 3 regions support local currency)

# Domains & branding
- India: retailnazar.com, retailnazar.in, retailnazar.info (brand: "Retail Nazar")
- Singapore: retail-vantag.com (brand: "Vantag — Retail Intelligence")
- Malaysia: retailjagajaga.com, jagajaga.my (brand: "JagaJaga")

# Setup (Plug & Play, under 30 minutes)
1. Register on the web portal or mobile (email, phone, store name, country)
2. Pick a plan; pay via Razorpay
3. From dashboard, click "Install Edge Agent" → download for Windows/Linux/Mac
4. Run install.ps1 (Win) or install.sh (Linux/Mac) on a local PC/Pi
5. Paste Cloud URL + Tenant ID (shown in dashboard)
6. Agent auto-scans LAN for RTSP cameras (192.168.x.x port 554)
7. Confirm cameras in dashboard, draw zones (drag boxes on snapshot)
8. Live alerts start flowing

# CCTV & networking knowledge
- Most IP cameras speak RTSP on port 554. URL pattern: rtsp://user:pass@ip:554/stream1
- ONVIF is a discovery/control standard many cams support
- Dahua, Hikvision, CP Plus, Reolink, Uniview are popular brands
- Cameras must be on the SAME LAN as the Edge Agent — a public VPS cannot
  reach 192.168.x.x addresses (that's basic IP routing, not a Vantag bug)
- For remote cloud-only deployment, use port-forwarding or a VPN (not recommended)
- H.264 is the dominant codec; H.265 (HEVC) is supported on modern Edge Agents

# Protocols used
- RTSP (camera video ingest)
- MQTT (door lock commands, edge telemetry; Mosquitto broker on port 1883)
- HTTPS/WSS (dashboard, API, realtime events)
- JWT bearer tokens (auth)

# Security
- All traffic over TLS 1.2+ (Let's Encrypt certs, auto-renewed)
- bcrypt for password hashing
- Video stays on-premise; only events leave the LAN
- Multi-tenant isolation at DB row level (tenant_id)

# When to escalate
If the user's question is outside your knowledge, or they need account-specific
action (refund, password reset via a human, custom integration, enterprise
pricing), direct them to email support@retail-vantag.com.

# Tone
Be concise, friendly, confident, and technical where needed. Never make up
features that don't exist. If unsure, say so and point to support email.
"""


# ─── Request/response models ───────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    language: str = "en"  # user's preferred language (ISO code)


class ChatResponse(BaseModel):
    reply: str
    escalate_to_email: bool = False


# ─── Fallback canned answers (if OpenAI is not configured) ─────────────────
_FALLBACK_INTRO = (
    "Hi! I'm Vantag Assistant. I can help with setup, features, pricing, "
    "camera connection issues, and technical questions. What do you need?"
)

_FALLBACK_KEYWORDS = {
    "price": (
        "Pricing varies by region:\n"
        "• India: ₹999–₹4,999/mo\n"
        "• Singapore: S$29–S$129/mo\n"
        "• Malaysia: RM49–RM249/mo\n"
        "Each plan tier covers more cameras. See our Pricing section for details."
    ),
    "setup": (
        "Setup takes ~30 minutes:\n"
        "1. Register → pick plan → pay\n"
        "2. Download Edge Agent from dashboard\n"
        "3. Run installer on local PC/Pi\n"
        "4. Paste Cloud URL + Tenant ID\n"
        "5. Agent auto-scans your LAN for cameras\n"
        "6. Confirm in dashboard and draw zones"
    ),
    "camera": (
        "Vantag works with any IP camera that speaks RTSP (port 554). "
        "The Edge Agent auto-discovers cameras on your LAN. "
        "If cameras show offline, check they're powered, on the same LAN as the "
        "Edge Agent, and reachable at rtsp://ip:554."
    ),
    "mqtt": (
        "MQTT is used for door-lock commands and edge telemetry. "
        "Our broker is Mosquitto on port 1883 inside the Vantag cloud. "
        "If MQTT shows OFF, the Edge Agent can't reach the broker — check firewall."
    ),
    "security": (
        "Your video never leaves your LAN — only events and snapshot evidence "
        "are uploaded. We use TLS 1.2+ on all connections, bcrypt for passwords, "
        "and strict tenant isolation at the database level."
    ),
}


def _fallback_reply(user_text: str) -> str:
    low = user_text.lower()
    for key, answer in _FALLBACK_KEYWORDS.items():
        if key in low:
            return answer + f"\n\nNeed more help? Email {SUPPORT_EMAIL}"
    return (
        f"I'm currently running in limited mode. For detailed help, please "
        f"email {SUPPORT_EMAIL} — a human will respond within 24 hours."
    )


# ─── Endpoint ──────────────────────────────────────────────────────────────
@support_router.post("/chat", response_model=ChatResponse)
async def support_chat(req: ChatRequest) -> ChatResponse:
    if not req.messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    last_user = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), ""
    )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return ChatResponse(reply=_fallback_reply(last_user), escalate_to_email=True)

    try:
        # Lazy import so the backend doesn't require openai package unless used
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=api_key)

        lang_hint = f"\n\nRespond in the user's language: {req.language}." if req.language != "en" else ""

        openai_messages = [
            {"role": "system", "content": VANTAG_SYSTEM_PROMPT + lang_hint},
        ]
        for m in req.messages[-10:]:  # keep last 10 turns
            openai_messages.append({"role": m.role, "content": m.content})

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=openai_messages,
            max_tokens=500,
            temperature=0.3,
        )
        reply = completion.choices[0].message.content or ""

        # Heuristic: if the reply suggests escalation, flag it
        escalate = any(
            phrase in reply.lower()
            for phrase in ["contact support", "email support", SUPPORT_EMAIL]
        )
        return ChatResponse(reply=reply.strip(), escalate_to_email=escalate)

    except Exception as exc:
        # OpenAI unreachable or errored — fall back gracefully
        return ChatResponse(
            reply=(
                f"{_fallback_reply(last_user)}\n\n"
                f"(AI service temporarily unavailable: {type(exc).__name__})"
            ),
            escalate_to_email=True,
        )


@support_router.get("/faq")
async def get_faq() -> dict:
    """Static FAQ content served from backend (easy to update without rebuild)."""
    return {
        "faqs": [
            {
                "q": "What is Vantag?",
                "a": "Vantag is a SaaS retail security platform that uses AI on any IP "
                     "camera to detect theft, loitering, empty shelves, falls, and more.",
            },
            {
                "q": "Do I need special hardware?",
                "a": "No. Vantag works with any generic IP camera that supports RTSP. "
                     "You only need a PC, tablet, or Raspberry Pi to run the Edge Agent.",
            },
            {
                "q": "How long does setup take?",
                "a": "Under 30 minutes for most retailers. Register → pay → download "
                     "Edge Agent → auto-scan cameras → confirm zones. Done.",
            },
            {
                "q": "Is my video uploaded to the cloud?",
                "a": "No. Video processing happens locally on your Edge Agent. Only "
                     "events (e.g., 'theft detected at 14:32') and evidence snapshots "
                     "are uploaded — saving bandwidth and keeping video private.",
            },
            {
                "q": "What cameras are supported?",
                "a": "Any IP camera with RTSP support: Dahua, Hikvision, CP Plus, "
                     "Reolink, Uniview, TP-Link Tapo, and hundreds of generic brands.",
            },
            {
                "q": "What if I don't have a PC?",
                "a": "A Raspberry Pi 4 or an old Android tablet runs the Edge Agent "
                     "fine. We also sell a pre-configured Vantag Edge Box.",
            },
            {
                "q": "Can I cancel anytime?",
                "a": "Yes. Month-to-month, cancel in one click from the billing page.",
            },
            {
                "q": "Do you support my language?",
                "a": "We support 12 languages: English, Hindi, Tamil, Telugu, Kannada, "
                     "Malayalam, Marathi, Gujarati, Bengali, Punjabi, Malay, and "
                     "Mandarin. Switch from the top-right language picker.",
            },
            {
                "q": "What happens if internet goes down?",
                "a": "The Edge Agent continues detecting events locally and queues "
                     "them. When connectivity returns, queued events sync to the cloud.",
            },
            {
                "q": "How accurate is the AI?",
                "a": "Typical accuracy: 92–95% on theft/sweeping, 88% on loitering, "
                     "95%+ on empty shelves. Accuracy improves as you tune zones.",
            },
        ]
    }
