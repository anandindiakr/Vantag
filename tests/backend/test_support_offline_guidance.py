import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.api.support_router import (
    OFFLINE_GUIDANCE,
    VANTAG_SYSTEM_PROMPT,
    _fallback_reply,
    support_router,
)


@pytest.mark.parametrize("question", [
    "offline",
    "Can I configure cameras without internet?",
    "No internet at the exhibition",
    "How does the local console work?",
    "Offline demo licence for my team",
])
def test_offline_fallback_precedes_generic_camera_and_setup_answers(question):
    reply = _fallback_reply(question)
    assert OFFLINE_GUIDANCE in reply
    for required in (
        "same PC", "under validation", "seven days", "saved records",
        "permanent device-bound", "do not automatically sync", "subscription/payment dates",
    ):
        assert required in reply


def test_camera_offline_status_is_not_confused_with_offline_operating_mode():
    reply = _fallback_reply("My camera is offline")
    assert "SAME LAN" in reply
    assert OFFLINE_GUIDANCE not in reply


def test_ai_support_knows_current_online_and_offline_workflows():
    assert OFFLINE_GUIDANCE in VANTAG_SYSTEM_PROMPT
    assert "no separate Python install" in VANTAG_SYSTEM_PROMPT
    assert "run install.ps1" not in VANTAG_SYSTEM_PROMPT
    assert "enter the original password literally" in VANTAG_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_public_faq_and_limited_chat_serve_matching_offline_guidance(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = FastAPI()
    app.include_router(support_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        faq = await client.get("/api/support/faq")
        assert faq.status_code == 200
        categories = faq.json()["categories"]
        offline = categories[0]
        assert offline["id"] == "offline-site-console"
        assert offline["items"][0]["a"] == OFFLINE_GUIDANCE
        assert len(offline["items"]) == 5
        answers = " ".join(item["a"] for category in categories for item in category["items"])
        assert "You won't lose any detections" not in answers
        assert "enter the original password including #" in answers
        reply = await client.post("/api/support/chat", json={
            "messages": [{"role": "user", "content": "Camera setup without internet"}],
        })
        assert reply.status_code == 200
        assert OFFLINE_GUIDANCE in reply.json()["reply"]
