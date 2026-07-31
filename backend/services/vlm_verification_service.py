"""
backend/services/vlm_verification_service.py
==============================================
Tier 3 false-positive reduction (agent/backend v1.5.1+): cross-check a
detection snapshot against a vision-language model (VLM) before an alert
(SMS/WhatsApp/email/webhook) is dispatched.

Why this exists
----------------
The edge agent's heuristics (proximity-and-dwell for shoplifting, pose
angles for falls, motion-grid dwell for loitering/restricted zones) are
fast enough to run on a shop's CPU laptop in real time, but they cannot
understand a scene the way a human — or a vision-language model — can.
A VLM cross-check has been shown in practice to cut false-positive rates
several-fold (e.g. from ~15% to ~4% in published shoplifting-detection
pipelines) by rejecting detections where the image plainly does not
support the claimed behaviour.

Design principles (honesty first)
----------------------------------
1. FAIL OPEN. If no API key is configured, the call times out, the API
   errors, or the response can't be parsed, this module returns None —
   meaning "could not verify" — and the caller MUST treat that exactly
   like the old behaviour (dispatch the alert). A slow/down/misconfigured
   third-party API must never silently swallow a real theft alert.
2. OPT-IN, per-tenant AND globally. Verification only runs when
   VLM_VERIFICATION_ENABLED=true and OPENAI_API_KEY is set. Existing
   deployments that don't set these env vars see zero behaviour change.
3. ONLY gates alert dispatch, never the incident record. The event is
   always persisted and shown on the dashboard (with the verification
   verdict attached) — verification only decides whether to also fire an
   SMS/WhatsApp/email/webhook, so a shop owner reviewing incidents never
   loses visibility even when verification disagrees.
4. Scoped to event types where a single still frame can plausibly confirm
   or refute the claim (shoplifting, restricted_zone, loitering,
   suspicious_behavior, fall_detected). Not used for count-based events
   (people_count, queue_length, crowding) where a still frame can't
   meaningfully validate a threshold crossing.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Event types where a single snapshot can meaningfully confirm/refute the
# claimed behaviour. Deliberately excludes count/threshold-based events.
VERIFIABLE_EVENT_TYPES = {
    "shoplifting",
    "theft",
    "restricted_zone",
    "loitering",
    "suspicious_behavior",
    "suspicious_behaviour",
    "fall_detected",
}

_PROMPTS: dict[str, str] = {
    "shoplifting": (
        "This still image was flagged by an automated retail-security camera as "
        "possible SHOPLIFTING (a person handling a shelf item in a way that could "
        "indicate concealment or theft). Look carefully at the image. Does it show "
        "a person plausibly concealing, pocketing, or bagging a product without "
        "paying, OR at minimum handling merchandise in a way consistent with that? "
        "Ordinary browsing, picking up and putting back an item, or an unclear/"
        "low-quality frame should be answered as NOT matching."
    ),
    "theft": (
        "This still image was flagged by an automated retail-security camera as "
        "possible THEFT. Does the image plausibly show a person taking or "
        "concealing merchandise without paying? Ordinary browsing or an unclear "
        "frame should be answered as NOT matching."
    ),
    "restricted_zone": (
        "This still image was flagged because a person was detected dwelling in a "
        "RESTRICTED / staff-only zone for an extended period. Does the image show "
        "a person actually present in what looks like a restricted, back-of-store, "
        "or staff-only area? An empty area or a customer in a normal shopping "
        "aisle should be answered as NOT matching."
    ),
    "loitering": (
        "This still image was flagged as possible LOITERING (a person remaining in "
        "one spot for an unusually long time without shopping activity). Does the "
        "image show a person standing/waiting in a way consistent with loitering, "
        "rather than normal browsing, queuing, or being served? An unclear or "
        "empty frame should be answered as NOT matching."
    ),
    "suspicious_behavior": (
        "This still image was flagged as SUSPICIOUS BEHAVIOUR by an automated "
        "retail-security camera. Does the image plausibly show unusual, evasive, "
        "or concerning behaviour (e.g. looking around nervously while handling "
        "items, covering face, erratic movement)? Ordinary shopping or an unclear "
        "frame should be answered as NOT matching."
    ),
    "fall_detected": (
        "This still image was flagged as a possible FALL (a person on the ground "
        "or in a falling posture). Does the image plausibly show a person who has "
        "fallen or is in the process of falling? A standing/sitting/normal posture "
        "or an unclear frame should be answered as NOT matching."
    ),
}
_PROMPTS["suspicious_behaviour"] = _PROMPTS["suspicious_behavior"]

_SYSTEM_PROMPT = (
    "You are a careful, honest visual auditor for a retail security system. "
    "You will be shown one still frame and a claim about what an automated "
    "detector flagged. Judge ONLY what is visible in the image — never assume "
    "intent you cannot see. When genuinely unsure or the image is unclear/dark/"
    "blurry, say so and answer 'matches: false' with a lower confidence rather "
    "than guessing yes. Respond with ONLY a JSON object, no other text: "
    '{"matches": true|false, "confidence": 0.0-1.0, "reasoning": "one short sentence"}'
)

_API_URL = "https://api.openai.com/v1/chat/completions"
_MODEL = os.getenv("VLM_VERIFICATION_MODEL", "gpt-4o-mini")
_TIMEOUT_SEC = 8.0


def is_enabled() -> bool:
    return (
        os.getenv("VLM_VERIFICATION_ENABLED", "false").lower() in ("1", "true", "yes")
        and bool(os.getenv("OPENAI_API_KEY"))
    )


def is_verifiable_event(event_type: str) -> bool:
    return (event_type or "").lower() in VERIFIABLE_EVENT_TYPES


async def verify_incident(event_type: str, snapshot_bytes: bytes) -> Optional[dict]:
    """Ask the VLM whether the snapshot supports the claimed event type.

    Returns None (meaning "could not verify — proceed as before, fail open")
    when verification is disabled, misconfigured, unreachable, or the
    response can't be parsed. Only returns a dict when a genuine verdict was
    obtained: {"matches": bool, "confidence": float, "reasoning": str}.
    """
    if not is_enabled():
        return None

    key = (event_type or "").lower()
    prompt = _PROMPTS.get(key)
    if prompt is None:
        return None  # not a verifiable event type

    api_key = os.getenv("OPENAI_API_KEY")
    b64 = base64.b64encode(snapshot_bytes).decode()

    payload = {
        "model": _MODEL,
        "max_tokens": 150,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as client:
            resp = await client.post(
                _API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        if resp.status_code != 200:
            logger.warning(
                "VLM verification API returned %s for event_type=%s — failing open",
                resp.status_code, event_type,
            )
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        # Models occasionally wrap JSON in a code fence despite instructions.
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:]
        parsed = json.loads(content)
        matches = bool(parsed.get("matches"))
        confidence = float(parsed.get("confidence", 0.5))
        reasoning = str(parsed.get("reasoning", ""))[:300]
        return {"matches": matches, "confidence": confidence, "reasoning": reasoning}
    except Exception:  # noqa: BLE001 — any failure here must fail open
        logger.exception(
            "VLM verification failed for event_type=%s — failing open (alert will still dispatch)",
            event_type,
        )
        return None
