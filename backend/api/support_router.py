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

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

support_router = APIRouter(prefix="/api/support", tags=["support"])

logger = logging.getLogger("vantag.support")

SUPPORT_EMAIL = "support@retail-vantag.com"

_bearer = HTTPBearer(auto_error=False)

# ─── Vantag Knowledge Base (burned into the system prompt) ─────────────────
VANTAG_SYSTEM_PROMPT = """You are Vantag Assistant — the official AI support agent for Vantag
(also branded as "Retail Nazar" in India, "JagaJaga" in Malaysia, "Retail Bantay" in the
Philippines, and "RetailPantau" in Indonesia).

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
- Philippines: Starter ₱1,299/mo (2 cam), Growth ₱2,999/mo (10 cam), Pro ₱5,999/mo (30 cam)
- Indonesia: Starter Rp450.000/mo (2 cam), Growth Rp1.200.000/mo (10 cam), Pro Rp2.500.000/mo (30 cam)
- Payment: Razorpay (India), Xendit (Singapore, Malaysia, Philippines, Indonesia — supports GCash, Maya, GrabPay, OVO, DANA)

# Domains & branding
- India: retailnazar.com, retailnazar.in, retailnazar.info (brand: "Retail Nazar")
- Singapore: retail-vantag.com (brand: "Vantag — Retail Intelligence")
- Malaysia: retailjagajaga.com, jagajaga.my (brand: "JagaJaga")
- Philippines: retailbantay.com (brand: "Retail Bantay")
- Indonesia: retailpantau.com (brand: "RetailPantau")

# Setup (Plug & Play, under 30 minutes)
1. Register on the web portal or mobile (email, phone, store name, country)
2. Pick a plan; pay via Razorpay/Xendit
3. From dashboard, click "Install Edge Agent" → download for Windows/Linux/Mac
4. Run install.ps1 (Win) or install.sh (Linux/Mac) on a local PC/Pi
5. Paste Cloud URL + Tenant ID (shown in dashboard)
6. Agent auto-scans LAN for RTSP cameras (192.168.x.x port 554)
7. Confirm cameras in dashboard, draw zones (drag boxes on snapshot)
8. Wait ~2 minutes for the agent to finish loading its AI libraries and
   connect each camera — live alerts start flowing after that

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

# NVR / DVR limitations (important — answer honestly, do not overstate)
- Cameras and NVR/DVR channels connect via RTSP the same way individual IP
  cameras do. Hikvision NVR channel URL pattern:
  rtsp://user:pass@NVR-IP:554/Streaming/Channels/101 (channel 1, main stream)
  or /102 for channel 1 sub-stream. Dahua/CP Plus pattern:
  rtsp://user:pass@NVR-IP:554/cam/realmonitor?channel=1&subtype=0
  (subtype=0 main, subtype=1 sub).
- If the camera/NVR password contains special characters (# @ % : / etc.)
  they MUST be URL-encoded in the RTSP string (e.g. # becomes %23, @ becomes
  %40) or the connection will silently fail.
- Pulling many simultaneous RTSP streams from one NVR is CPU/bandwidth
  limited — both on the NVR itself and on the PC running the Edge Agent.
  Symptom: some cameras load fine, others go blank or "offline" after a
  minute. Fix: use the NVR's SUB-stream (lower resolution) for live preview
  channels instead of the main stream, and make sure the Edge Agent PC has
  a wired (not WiFi) connection to the NVR when running many channels.
- Some older NVR firmware only allows a limited number of concurrent RTSP
  client connections (commonly 4–8) system-wide across ALL apps/viewers
  combined — if VLC or another NVR viewer app is also open at the same time,
  it competes for that same limited slot pool.
- H.265 (HEVC) streams may not decode on older Edge Agent versions — if a
  channel won't load, try switching that channel's encoding to H.264 in the
  NVR's video settings, or use the sub-stream (usually H.264 by default).
- Running MORE than 6–8 cameras: recommend (in order) 1) switch all
  live-preview channels to the NVR SUB-stream (~1/10th the bandwidth/CPU of
  main stream, makes 16+ channels practical), 2) split cameras across two or
  more Edge Agent PCs (e.g. cams 1–8 on PC A, 9–16 on PC B — both report to
  the same dashboard), 3) one Edge Agent per NVR if multiple NVRs exist,
  4) wired gigabit connection between Edge Agent PC and NVR (never WiFi for
  6+ streams), 5) for 16+ cameras use a dedicated 4-core/8GB+ PC and enable
  AI analysis only on the cameras that need it (entrances, billing counters,
  high-value shelves).

# Alert delivery (WhatsApp / SMS / Email) — SELF-SERVICE
- Vantag can push real-time alerts via SMS, WhatsApp, and Email whenever an
  event at or above a chosen severity threshold is detected (theft/sweeping,
  tamper, fall, restricted-zone entry, watchlist match, accident).
- This is fully self-service: go to Account → Alert Dispatch tab in the
  dashboard. Each channel (SMS, WhatsApp, Email) has its own enable toggle,
  a "Min. severity" threshold selector (LOW/MEDIUM/HIGH/CRITICAL), and a
  "Test" button to verify the configuration before relying on it.
- SMS and WhatsApp support MULTIPLE providers (chosen via a provider dropdown
  wizard in the Alert Dispatch tab — user is NOT forced to use Twilio):
    SMS: Twilio (global), MSG91 (India), Textlocal (India), Vonage (global),
         or a Generic HTTP Gateway for any local telecom that exposes an HTTP
         API (use {to} and {message} placeholders in the URL/body).
    WhatsApp: Twilio, Meta WhatsApp Business Cloud API (official, free tier),
         Gupshup (India), or the same Generic HTTP Gateway.
  Each provider shows step-by-step setup instructions in the dashboard wizard
  with exactly the credential fields that provider needs. Free Twilio trial
  accounts and Meta Cloud API test numbers work for testing.
- Meta WhatsApp Cloud API note: free-form messages only deliver within an
  open 24-hour session — the user should message their own business number
  once from their phone before testing, or register a template.
- Email alerts only need a "To email" address — no extra credentials
  required, it uses the platform's own email sending.
- Click "Test" on any channel to fire an instant test alert without waiting
  for a real incident — the result (success or the exact error, e.g. wrong
  Twilio credentials) is shown immediately in the dashboard.
- WhatsApp alerts require the recipient number to have joined the Twilio
  WhatsApp sandbox (or use an approved WhatsApp Business sender in
  production) before messages will deliver.
- If a user says "I detected an event but got no alert", the likely causes
  are: (1) the channel toggle isn't enabled, (2) the event's severity was
  below the configured "Min. severity" threshold, (3) Twilio credentials are
  wrong/expired — use the Test button to confirm, or (4) for WhatsApp, the
  recipient hasn't joined the sandbox yet.
- This is a newer capability than the old "email support to enable alerts"
  process — if a user has an older impression that alerts require emailing
  support, correct them: it's now self-service from Account → Alert Dispatch.

# Common installation mistakes (mention proactively when relevant)
1. Edge Agent PC and cameras on DIFFERENT networks/WiFi — the #1 cause of
   "cameras not found" or "offline" issues. Both must be on the exact same
   router/LAN, not just "the same building."
2. Using the WiFi guest network — guest networks isolate devices from each
   other by design, so the Edge Agent PC won't be able to see the cameras
   even though both show as "connected to WiFi."
3. Closing the Edge Agent terminal/window — the agent must keep running in
   the background for cameras to stay online and stream.
4. Not waiting long enough after starting the Edge Agent — after launch, the
   agent needs about 1–2 minutes to initialize, load its AI libraries, and
   connect to each configured camera one by one. Cameras will appear
   "connecting" then flip to "online" individually — this is normal, not a
   bug. Always advise users to wait ~2 minutes before assuming something
   is broken.
5. Windows Firewall or antivirus silently blocking the agent's network
   access — if cameras never come online despite being on the same network,
   check Windows Defender Firewall settings and allow the Edge Agent /
   python.exe through.
6. Running two copies of the Edge Agent at once (e.g. after a restart the
   old process wasn't closed) — causes port conflicts and flaky camera
   status.
7. Changing camera video settings (resolution/codec) without power-cycling
   the camera afterward — some cameras need a reboot for new settings to
   take effect.

# When to escalate
If the user's question is outside your knowledge, or they need account-specific
action (refund, password reset via a human, custom integration, enterprise
pricing, enabling WhatsApp/SMS/Slack alerts), direct them to email
support@retail-vantag.com.

# Tone & grounding rules (critical)
- Be concise, friendly, confident, and technical where needed.
- NEVER invent features, prices, timelines, or behavior that isn't described
  in this knowledge base. If you don't know something, say so plainly and
  point to the support email instead of guessing.
- Stay strictly on the topic the user actually asked about — do not pad
  answers with unrelated information "just in case."
- If a user's message is ambiguous, ask a short clarifying question rather
  than assuming and answering the wrong thing.
- When troubleshooting camera/network issues, always ask or check: (a) is
  the Edge Agent PC on the exact same network as the cameras, (b) has the
  user waited ~2 minutes after starting the agent, (c) is the RTSP
  URL/credentials correct. These three cover the majority of real issues.
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


class FeedbackRequest(BaseModel):
    page: str
    helpful: bool
    topic: str = "Not specified"
    message: str = ""


class FeedbackResponse(BaseModel):
    received: bool = True


async def _optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[dict]:
    """Best-effort auth: feedback should never fail just because the token
    is missing or expired — we still want to capture anonymous feedback."""
    if not credentials:
        return None
    try:
        from ..middleware.tenant_middleware import _decode_token  # lazy import

        return _decode_token(credentials.credentials)
    except HTTPException:
        return None


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
        "• Philippines: ₱1,299–₱5,999/mo\n"
        "• Indonesia: Rp450.000–Rp2.500.000/mo\n"
        "Each plan tier covers more cameras. See our Pricing section for details."
    ),
    "setup": (
        "Setup takes ~30 minutes:\n"
        "1. Register → pick plan → pay\n"
        "2. Download Edge Agent from dashboard\n"
        "3. Run installer on local PC/Pi\n"
        "4. Paste Cloud URL + Tenant ID\n"
        "5. Agent auto-scans your LAN for cameras\n"
        "6. Confirm in dashboard and draw zones\n"
        "7. Wait ~2 minutes for the agent to finish loading before checking live feed"
    ),
    "camera": (
        "Vantag works with any IP camera that speaks RTSP (port 554). "
        "The Edge Agent auto-discovers cameras on your LAN. "
        "If cameras show offline, check they're powered, on the SAME LAN as the "
        "Edge Agent PC (not a guest WiFi network), and reachable at rtsp://ip:554."
    ),
    "nvr": (
        "NVR/DVR channels work over RTSP too. Hikvision pattern: "
        "rtsp://user:pass@NVR-IP:554/Streaming/Channels/101. Dahua/CP Plus: "
        "rtsp://user:pass@NVR-IP:554/cam/realmonitor?channel=1&subtype=0. "
        "If several channels drop out, use the NVR's sub-stream instead of "
        "main stream, and use a wired connection for the Edge Agent PC. "
        "For more than 6-8 cameras: switch to sub-streams, split cameras "
        "across two Edge Agent PCs (both report to the same dashboard), and "
        "enable AI analysis only on the cameras that need it."
    ),
    "alert": (
        "Vantag sends SMS, WhatsApp, and Email alerts on theft, tamper, fall, "
        "and restricted-zone events. Configure them yourself: go to Account → "
        "Alert Dispatch tab, enable each channel, enter your Twilio credentials "
        "(for SMS/WhatsApp) or a To-email address, set the minimum severity, "
        "then press the Test button on each channel to verify delivery."
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
        # Call the OpenAI REST API directly with httpx rather than the
        # `openai` SDK. The SDK was never listed in requirements.txt, so it
        # was absent from the deployed container and every request raised
        # ModuleNotFoundError — which the handler below swallowed into a
        # friendly "limited mode" message, so the assistant appeared to
        # "work" while being permanently dead and nobody was told.
        # httpx is already a hard dependency and is the same transport
        # services/vlm_verification_service.py uses successfully.
        import httpx

        lang_hint = f"\n\nRespond in the user's language: {req.language}." if req.language != "en" else ""

        openai_messages = [
            {"role": "system", "content": VANTAG_SYSTEM_PROMPT + lang_hint},
        ]
        for m in req.messages[-10:]:  # keep last 10 turns
            openai_messages.append({"role": m.role, "content": m.content})

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": openai_messages,
                    "max_tokens": 500,
                    "temperature": 0.3,
                },
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenAI HTTP {resp.status_code}: {resp.text[:200]}"
            )
        reply = (
            (resp.json().get("choices") or [{}])[0]
            .get("message", {})
            .get("content")
            or ""
        )
        if not reply.strip():
            raise RuntimeError("OpenAI returned an empty completion")

        # Heuristic: if the reply suggests escalation, flag it
        escalate = any(
            phrase in reply.lower()
            for phrase in ["contact support", "email support", SUPPORT_EMAIL]
        )
        return ChatResponse(reply=reply.strip(), escalate_to_email=escalate)

    except Exception as exc:
        # Degrade gracefully for the user, but NEVER silently: log with a
        # stack trace and raise a deduplicated admin alert, so a dead
        # assistant is visible instead of hiding behind "limited mode".
        logger.exception("AI assistant call failed: %s", exc)
        try:
            from ..services.system_health import report_fault

            await report_fault(
                component="ai_assistant",
                summary=f"AI Assistant failing: {type(exc).__name__}",
                detail=str(exc)[:1000],
            )
        except Exception:  # noqa: BLE001 — alerting must never break the reply
            logger.exception("Failed to raise admin alert for AI assistant fault")
        return ChatResponse(
            reply=(
                f"{_fallback_reply(last_user)}\n\n"
                f"(AI service temporarily unavailable: {type(exc).__name__})"
            ),
            escalate_to_email=True,
        )


@support_router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    user: Optional[dict] = Depends(_optional_user),
) -> FeedbackResponse:
    """Accepts help-page feedback ("was this helpful?"). Best-effort: logs
    the feedback for review — does not require an active subscription or
    even a valid token, since users hitting subscription/auth errors are
    exactly the ones who may need to leave feedback."""
    logger.info(
        "support_feedback page=%s helpful=%s topic=%s tenant_id=%s user_id=%s message=%s",
        body.page,
        body.helpful,
        body.topic,
        (user or {}).get("tenant_id"),
        (user or {}).get("sub"),
        body.message[:500],
    )
    return FeedbackResponse(received=True)


@support_router.get("/faq")
async def get_faq() -> dict:
    """Categorized FAQ content served from backend (easy to update without
    rebuild). Each category may include a `diagram` image path (served from
    frontend/public/images/faq/) that the UI can render alongside the items."""
    return {
        "categories": [
            {
                "id": "getting-started",
                "title": "Getting Started",
                "icon": "Rocket",
                "diagram": "/images/faq/edge-agent-install-flow.png",
                "items": [
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
                        "a": "Under 30 minutes for most retailers: register → pay → download "
                             "Edge Agent → run installer → auto-scan cameras → confirm zones. "
                             "After the agent starts, allow about 2 minutes for it to finish "
                             "loading its AI libraries and connect each camera before checking "
                             "the live feed.",
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
                ],
            },
            {
                "id": "network-camera",
                "title": "Finding Your Camera & Network Setup",
                "icon": "Wifi",
                "diagram": "/images/faq/network-same-lan.png",
                "items": [
                    {
                        "q": "Does my PC (the one running the Edge Agent) need to be on the same WiFi as the cameras?",
                        "a": "Yes — the PC running the Edge Agent must be connected to the same "
                             "network (WiFi or LAN cable) as your cameras. The cameras and the "
                             "PC need to be able to \"talk\" to each other directly inside your "
                             "store's network. A cloud VPS can never reach camera IPs like "
                             "192.168.x.x directly — that's basic IP routing, not a bug.",
                    },
                    {
                        "q": "I don't know the IP address of my camera. How do I find it?",
                        "a": "The easiest way is to log into your WiFi router (usually by typing "
                             "192.168.1.1 or 192.168.0.1 into your browser). Look for a section "
                             "called \"Connected Devices\", \"DHCP Clients\", or \"Device List\" — "
                             "your camera will appear there with its IP address. It usually looks "
                             "like 192.168.1.xx.",
                    },
                    {
                        "q": "Can I find my camera's IP address from the camera's own app?",
                        "a": "Yes! Most camera brands have a phone app (Hikvision uses iVMS-4500, "
                             "Dahua uses DMSS). Open the app, go to your camera's settings, and "
                             "look for \"Network Settings\" or \"Device Info\" — the IP address is "
                             "listed there.",
                    },
                    {
                        "q": "My camera came with a CD or a tool — can I use that to find the IP?",
                        "a": "Absolutely. Most brands include a \"search tool\" or \"IP scanner\" "
                             "on their CD or available for free download (e.g. Hikvision's \"SADP "
                             "Tool\", Dahua's \"ConfigTool\"). Install it on any Windows PC on the "
                             "same network, run it, and it will automatically find all cameras and "
                             "display their IP addresses.",
                    },
                    {
                        "q": "I don't have a router login. Can I still find my camera's IP?",
                        "a": "Yes. Download a free app called \"Fing\" on your phone (iOS or "
                             "Android). Connect your phone to the same WiFi as your cameras, open "
                             "Fing, and tap \"Scan Network.\" It lists every device connected to "
                             "your network, including cameras, along with their IP addresses.",
                    },
                    {
                        "q": "What is an RTSP link and where do I get it?",
                        "a": "RTSP is just the address your camera uses to share its video. It "
                             "looks like: rtsp://username:password@192.168.1.64:554/stream. The IP "
                             "address part (192.168.1.64) is your camera's IP. The username and "
                             "password are your camera's login. The /stream part varies by brand.",
                    },
                    {
                        "q": "I don't know the username and password for my camera. What should I try?",
                        "a": "Most cameras come with default credentials. Common ones are: admin / "
                             "admin, admin / 12345, admin / (blank). Check the sticker on the back "
                             "or bottom of your camera — it often shows the default login. If "
                             "someone changed it and you don't know it, you can factory reset the "
                             "camera (usually a small reset button held for 10 seconds).",
                    },
                    {
                        "q": "My RTSP link isn't working. What could be wrong?",
                        "a": "The three most common reasons are: (1) wrong IP address — double-check "
                             "it with the steps above, (2) wrong username/password — try the "
                             "defaults listed above, (3) the camera and your PC are on different "
                             "networks — they must both be connected to the same router. If the "
                             "password contains special characters (# @ % etc.) they must be "
                             "URL-encoded (# → %23, @ → %40) or the connection will silently fail.",
                    },
                    {
                        "q": "Can I use wireless (WiFi) cameras, or do they need to be wired?",
                        "a": "Both work fine. WiFi cameras and wired (PoE/LAN) cameras are both "
                             "supported, as long as they support the RTSP protocol. Wired cameras "
                             "tend to be more reliable and are recommended for stores with 4+ cameras.",
                    },
                    {
                        "q": "Do I need a fast internet connection?",
                        "a": "The Edge Agent processes video locally on your PC — it does NOT "
                             "upload video to the internet. You only need internet to send small "
                             "alert snapshots and event data to the cloud. A basic 10 Mbps upload "
                             "connection is more than enough even for 10+ cameras.",
                    },
                    {
                        "q": "What happens if my internet goes down?",
                        "a": "Your cameras keep recording and the Edge Agent keeps detecting "
                             "incidents locally. Events are stored on your PC and automatically "
                             "sync to the cloud once the internet comes back. You won't lose any "
                             "detections.",
                    },
                    {
                        "q": "Does my PC need to be on 24 hours a day?",
                        "a": "Yes — for continuous monitoring, the PC running the Edge Agent "
                             "should stay on. You can set Windows to never sleep (Control Panel → "
                             "Power Options → \"Never\" sleep). Many stores use a small, "
                             "low-power mini-PC for this purpose.",
                    },
                ],
            },
            {
                "id": "nvr",
                "title": "NVR / DVR Compatibility & Limitations",
                "icon": "HardDrive",
                "items": [
                    {
                        "q": "I have a DVR/NVR. Can I connect it instead of individual cameras?",
                        "a": "Yes. Most modern DVRs and NVRs (Hikvision, Dahua, CP Plus) support "
                             "RTSP streaming per channel. Point the Edge Agent to the NVR's IP "
                             "with a channel-specific RTSP URL instead of each camera's own IP. "
                             "Hikvision: rtsp://user:pass@NVR-IP:554/Streaming/Channels/101 "
                             "(channel 1 main stream, 102 = sub-stream). Dahua/CP Plus: "
                             "rtsp://user:pass@NVR-IP:554/cam/realmonitor?channel=1&subtype=0.",
                    },
                    {
                        "q": "Some NVR channels load fine but others go blank or offline after a minute. Why?",
                        "a": "This is almost always an NVR/network bandwidth limitation, not a "
                             "software bug — pulling many simultaneous main-stream RTSP feeds from "
                             "one NVR is CPU and bandwidth heavy. Fix: switch the affected "
                             "channels to the NVR's SUB-stream (lower resolution) for live "
                             "preview, and use a wired (not WiFi) connection between the Edge "
                             "Agent PC and the NVR.",
                    },
                    {
                        "q": "Is there a limit on how many concurrent RTSP connections an NVR allows?",
                        "a": "Yes — many NVR models, especially older firmware, cap concurrent "
                             "RTSP client connections (commonly 4–8) across ALL apps combined. If "
                             "you have VLC or another viewer open at the same time as the Edge "
                             "Agent, they compete for that same limited pool. Close other viewers "
                             "before testing.",
                    },
                    {
                        "q": "A channel won't load at all even though others work. What should I check?",
                        "a": "Check if that channel is set to H.265 (HEVC) — older Edge Agent "
                             "versions may not decode H.265. Switch that channel's encoding to "
                             "H.264 in the NVR's video settings, or use the sub-stream (usually "
                             "H.264 by default).",
                    },
                    {
                        "q": "My NVR password has special characters like # or @ — the RTSP link fails.",
                        "a": "Special characters in the password must be URL-encoded in the RTSP "
                             "string or the connection silently fails. Common encodings: # → %23, "
                             "@ → %40, % → %25. Example: a password Pass#1 becomes Pass%231 in the "
                             "RTSP URL.",
                    },
                    {
                        "q": "I need to run MORE than 6–8 cameras. What is the recommended setup?",
                        "a": "Beyond 6–8 simultaneous streams you will typically hit one of three "
                             "limits: the NVR's concurrent RTSP connection cap, the network "
                             "bandwidth, or the CPU of the PC running the Edge Agent. Recommended "
                             "solutions, in order: (1) Switch ALL live-preview channels to the "
                             "NVR's SUB-stream — a sub-stream uses roughly 1/10th the bandwidth "
                             "and CPU of the main stream, so 16+ channels become practical on one "
                             "PC. (2) Split cameras across TWO or more Edge Agent PCs — e.g. "
                             "cameras 1–8 on PC A and 9–16 on PC B; both agents report to the "
                             "same dashboard, so you still see everything in one place. (3) If "
                             "the cameras are spread across two NVRs, run one Edge Agent per NVR "
                             "on the same or separate PCs. (4) Use a wired gigabit connection "
                             "between the Edge Agent PC and the NVR — never WiFi for 6+ streams. "
                             "(5) For 16+ cameras, use a dedicated PC with at least a modern "
                             "4-core CPU and 8 GB RAM for the Edge Agent, and enable AI analysis "
                             "only on the cameras that actually need it (entrances, billing "
                             "counters, high-value shelves) rather than every channel.",
                    },
                ],
            },
            {
                "id": "alerts",
                "title": "Setting Up Alerts (WhatsApp, SMS, Email)",
                "icon": "Bell",
                "diagram": "/images/faq/alert-setup-flow.png",
                "items": [
                    {
                        "q": "Can I get an alert via SMS, WhatsApp, or email when theft is detected?",
                        "a": "Yes. Vantag can push real-time alerts via SMS, WhatsApp, or Email "
                             "whenever an event at or above your chosen severity fires — "
                             "theft/sweeping, camera tampering, a fall, someone entering a "
                             "restricted zone, or a watchlist match. You configure this yourself "
                             "in the dashboard under Account → Alert Dispatch.",
                    },
                    {
                        "q": "How do I turn on WhatsApp or SMS alerts for my store?",
                        "a": "Go to Account → Alert Dispatch in the dashboard. Enable the SMS or "
                             "WhatsApp channel and pick a provider from the dropdown — you are "
                             "NOT limited to Twilio. A built-in step-by-step wizard shows exactly "
                             "how to get credentials for the provider you pick, and the form only "
                             "shows the fields that provider needs. Enter the To-number in "
                             "international format (e.g. +91XXXXXXXXXX), pick a minimum severity "
                             "(most stores use HIGH to avoid alert fatigue), press Send Test to "
                             "confirm it works, then Save.",
                    },
                    {
                        "q": "Which SMS and WhatsApp providers are supported? I don't want to use Twilio.",
                        "a": "SMS: Twilio (global), MSG91 (India), Textlocal (India), Vonage "
                             "(global), or a Generic HTTP Gateway that works with almost any "
                             "local telecom exposing an HTTP send API. WhatsApp: Twilio, Meta "
                             "WhatsApp Business Cloud API (the official Meta option — free tier "
                             "available), Gupshup (popular in India), or the Generic HTTP "
                             "Gateway. For the HTTP Gateway, paste your provider's send URL and "
                             "use {to} and {message} placeholders — e.g. "
                             "https://sms.myprovider.com/send?key=XXX&to={to}&text={message}.",
                    },
                    {
                        "q": "How do I use my own local telecom / SMS provider that isn't listed?",
                        "a": "Choose \"Generic HTTP Gateway\" as the provider. Ask your provider "
                             "for their HTTP send API URL (almost all have one), paste it into "
                             "the Gateway URL field using {to} and {message} placeholders where "
                             "the phone number and text go, set the method (GET or POST), add "
                             "any required headers or body template, then press Send Test. This "
                             "works with virtually any SMS or WhatsApp gateway in any country.",
                    },
                    {
                        "q": "How do I set up Email alerts?",
                        "a": "Email is the simplest channel: in Account → Alert Dispatch, enable "
                             "the Email toggle, enter the To-email address, choose a minimum "
                             "severity, save, and press Test. No Twilio or other credentials are "
                             "needed — it uses the platform's own email sending.",
                    },
                    {
                        "q": "I detected an event but didn't get an alert. Why?",
                        "a": "Check these in order: (1) the channel toggle in Account → Alert "
                             "Dispatch is actually enabled, (2) the event's severity was at or "
                             "above your configured minimum severity (e.g. a MEDIUM event won't "
                             "trigger a HIGH-only route), (3) your Twilio credentials are correct "
                             "— press the Test button, which shows the exact error if they're "
                             "wrong or expired, and (4) for WhatsApp specifically, the recipient "
                             "number must have joined the Twilio WhatsApp sandbox (or use an "
                             "approved business sender).",
                    },
                    {
                        "q": "Do I need to do anything special to receive WhatsApp alerts?",
                        "a": "Depends on the provider. Twilio: the recipient's WhatsApp number "
                             "must join the Twilio sandbox (or use an approved business sender). "
                             "Meta Cloud API: free-form messages only deliver within a 24-hour "
                             "session — send one message from your phone to your business number "
                             "first, or register a message template. Gupshup/HTTP Gateway: follow "
                             "your provider's opt-in rules. If Send Test reports success but no "
                             "message arrives, this opt-in/session rule is the first thing to "
                             "check.",
                    },
                    {
                        "q": "What does the Test button do?",
                        "a": "It fires an instant test alert through that channel using your "
                             "saved settings — no real incident needed. The result appears "
                             "immediately in the dashboard: a success confirmation, or the exact "
                             "error (e.g. invalid Twilio credentials, unverified number) so you "
                             "can troubleshoot before relying on the channel.",
                    },
                    {
                        "q": "Can I also connect alerts to Slack or Microsoft Teams?",
                        "a": f"Slack and Microsoft Teams webhook routes are supported at the "
                             f"platform level but are not yet self-service in the dashboard. "
                             f"Email {SUPPORT_EMAIL} with your webhook URL to enable them.",
                    },
                ],
            },
            {
                "id": "install-mistakes",
                "title": "Mistakes to Avoid During Installation",
                "icon": "AlertTriangle",
                "items": [
                    {
                        "q": "What is the #1 mistake people make when installing the Edge Agent?",
                        "a": "Running the Edge Agent PC on a DIFFERENT network/WiFi than the "
                             "cameras. Both must be connected to the exact same router/LAN — not "
                             "just \"the same building\" or \"the same office WiFi name\" if that "
                             "name maps to two different networks (e.g. a guest network).",
                    },
                    {
                        "q": "I connected to the WiFi guest network — is that a problem?",
                        "a": "Yes. Guest WiFi networks isolate devices from each other by design, "
                             "so even though the Edge Agent PC and cameras both show \"Connected\" "
                             "to WiFi, they can't actually see each other. Always use the main "
                             "(non-guest) network for both the PC and the cameras.",
                    },
                    {
                        "q": "How long should I wait after starting the Edge Agent before checking the live feed?",
                        "a": "Please wait about 2 minutes. After launch, the agent needs time to "
                             "initialize, load its AI libraries, and connect to each configured "
                             "camera one at a time. Cameras will show \"connecting\" and then flip "
                             "to \"online\" individually — this is expected behavior, not a fault.",
                    },
                    {
                        "q": "Can I close the Edge Agent window after it starts?",
                        "a": "No — the Edge Agent must keep running in the background the entire "
                             "time you want cameras online. Closing its terminal/window stops all "
                             "camera connections immediately.",
                    },
                    {
                        "q": "Cameras are on the same network but still won't connect. What else could block it?",
                        "a": "Check Windows Firewall or antivirus — they can silently block the "
                             "Edge Agent's network access even when everything else is correct. "
                             "Allow the Edge Agent (python.exe) through Windows Defender Firewall.",
                    },
                    {
                        "q": "I restarted the Edge Agent but camera status looks inconsistent/flaky.",
                        "a": "Make sure only ONE copy of the Edge Agent is running. If the old "
                             "process wasn't fully closed before restarting, you can end up with "
                             "two instances competing for the same ports, causing flaky status.",
                    },
                    {
                        "q": "I changed my camera's resolution/codec setting but nothing changed.",
                        "a": "Some cameras require a power cycle (unplug and replug, or reboot "
                             "from their web interface) before new video settings take effect.",
                    },
                ],
            },
            {
                "id": "ai-features",
                "title": "AI Detection Features & Accuracy",
                "icon": "Brain",
                "items": [
                    {
                        "q": "What cameras are supported?",
                        "a": "Any IP camera with RTSP support: Dahua, Hikvision, CP Plus, "
                             "Reolink, Uniview, TP-Link Tapo, and hundreds of generic brands. It "
                             "does NOT work with old analog CCTV cameras unless you have a "
                             "DVR/NVR that supports RTSP output.",
                    },
                    {
                        "q": "Is my video uploaded to the cloud?",
                        "a": "No. Video processing happens locally on your Edge Agent. Only "
                             "events (e.g., 'theft detected at 14:32') and evidence snapshots "
                             "are uploaded — saving bandwidth and keeping video private.",
                    },
                    {
                        "q": "How accurate is the AI?",
                        "a": "Typical accuracy: 92–95% on theft/sweeping, 88% on loitering, "
                             "95%+ on empty shelves. Accuracy improves as you tune zones.",
                    },
                    {
                        "q": "I bought cameras from a local shop with no brand name. Will they work?",
                        "a": "Likely yes — most generic IP cameras sold locally use standard "
                             "RTSP. Try the RTSP URL format: rtsp://admin:admin@[camera-IP]:554/"
                             "stream1. If that doesn't work, check the camera's web interface "
                             "(open the camera IP in a browser) and look for \"Video Stream\" or "
                             "\"RTSP\" settings.",
                    },
                    {
                        "q": "The app says \"Connection Failed\" for my camera. What do I do?",
                        "a": "Check these in order: (1) Can you open the camera's IP in a browser "
                             "from the same PC? If not, the camera and PC are not on the same "
                             "network. (2) Is the username/password correct? (3) Try pinging the "
                             "camera: open Command Prompt and type ping 192.168.1.xx (replace "
                             "with your camera's IP). If it says \"Request timed out,\" the camera "
                             "is not reachable.",
                    },
                    {
                        "q": "I can see my camera but the video is blurry or choppy.",
                        "a": "This usually means the camera is set to a high resolution that the "
                             "network can't handle smoothly. Log into your camera's web interface, "
                             "go to Video Settings, and lower the main stream resolution to 1080p "
                             "or 720p, and the bitrate to 2048–4096 Kbps. This gives a clear "
                             "picture without overloading the network.",
                    },
                    {
                        "q": "I want to monitor my store remotely from my phone. Do I need extra setup?",
                        "a": "No extra setup needed. The Edge Agent automatically sends live "
                             "previews and alerts to the cloud, which you can view from the "
                             "dashboard on any phone or browser. You do not need to set up port "
                             "forwarding or expose your cameras to the internet.",
                    },
                ],
            },
            {
                "id": "billing",
                "title": "Billing & Plans",
                "icon": "CreditCard",
                "items": [
                    {
                        "q": "How much does Vantag cost?",
                        "a": "Pricing varies by region and camera count:\n"
                             "• India: ₹999–₹4,999/mo\n"
                             "• Singapore: S$29–S$129/mo\n"
                             "• Malaysia: RM49–RM249/mo\n"
                             "• Philippines: ₱1,299–₱5,999/mo\n"
                             "• Indonesia: Rp450.000–Rp2.500.000/mo",
                    },
                    {
                        "q": "Can I cancel anytime?",
                        "a": "Yes. Month-to-month, cancel in one click from the billing page.",
                    },
                    {
                        "q": "What payment methods are supported?",
                        "a": "Razorpay for India. Xendit for Singapore, Malaysia, Philippines, "
                             "and Indonesia — supporting GCash, Maya, GrabPay, OVO, and DANA in "
                             "addition to cards.",
                    },
                ],
            },
            {
                "id": "security",
                "title": "Security & Privacy",
                "icon": "Shield",
                "items": [
                    {
                        "q": "Is my video uploaded anywhere?",
                        "a": "No. Video processing happens entirely on your local Edge Agent. "
                             "Only event metadata and evidence snapshots (small images) are sent "
                             "to the cloud — saving bandwidth and keeping full video private to "
                             "your store.",
                    },
                    {
                        "q": "How is my data secured?",
                        "a": "All traffic uses TLS 1.2+ (auto-renewed Let's Encrypt certificates), "
                             "passwords are hashed with bcrypt, and every tenant's data is "
                             "isolated at the database row level (tenant_id) so one store can "
                             "never see another's data.",
                    },
                    {
                        "q": "Does my camera footage ever leave my network?",
                        "a": "No — full video stays on-premise on your Edge Agent PC. Only "
                             "compressed event snapshots and metadata leave your local network "
                             "when an alert fires.",
                    },
                ],
            },
        ]
    }
