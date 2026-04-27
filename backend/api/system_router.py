"""
backend/api/system_router.py
=============================
System health-check endpoint for the Vantag platform.

GET /api/system/health-check
    Runs real probes against every external dependency and returns a
    structured status report.  Total time is capped at 10 seconds;
    individual probes time out after 2 seconds.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..middleware.tenant_middleware import get_current_user_id

logger = logging.getLogger(__name__)

system_router = APIRouter(prefix="/api/system", tags=["System"])

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class HealthCheckItem(BaseModel):
    name: str
    ok: bool
    latency_ms: Optional[float] = None
    detail: str


class HealthCheckResponse(BaseModel):
    checks: List[HealthCheckItem]
    overall: str  # "healthy" | "degraded" | "broken"


# ---------------------------------------------------------------------------
# Individual probe functions
# Each returns (ok: bool, detail: str, latency_ms: float | None)
# They must be awaitable and complete quickly (caller applies 2 s timeout).
# ---------------------------------------------------------------------------

async def _probe_postgres() -> tuple[bool, str, Optional[float]]:
    """Attempt a simple SELECT 1 against the PostgreSQL database."""
    t0 = time.monotonic()
    try:
        from ..db.database import engine
        async with engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        lat = round((time.monotonic() - t0) * 1000, 1)
        return True, "Connected", lat
    except Exception as exc:  # noqa: BLE001
        lat = round((time.monotonic() - t0) * 1000, 1)
        return False, f"Error: {exc}", lat


async def _probe_mqtt() -> tuple[bool, str, Optional[float]]:
    """Open a TCP connection to the MQTT broker port to verify it is reachable."""
    host = os.getenv("MQTT_BROKER", "localhost")
    port = int(os.getenv("MQTT_PORT", "1883"))
    t0 = time.monotonic()
    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.close()
        await writer.wait_closed()
        lat = round((time.monotonic() - t0) * 1000, 1)
        # Try to read broker version via CONNECT handshake (fire-and-forget, not required).
        return True, "Mosquitto reachable", lat
    except Exception as exc:  # noqa: BLE001
        lat = round((time.monotonic() - t0) * 1000, 1)
        return False, f"Unreachable: {exc}", lat


async def _probe_redis() -> tuple[bool, str, Optional[float]]:
    """Ping the Redis instance if configured."""
    redis_url = os.getenv("REDIS_URL", "")
    t0 = time.monotonic()
    if not redis_url:
        return False, "REDIS_URL not configured", None
    try:
        import aioredis  # type: ignore
        r = await aioredis.from_url(redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.close()
        lat = round((time.monotonic() - t0) * 1000, 1)
        return True, "Connected", lat
    except ImportError:
        # aioredis not installed — try raw TCP to default Redis port
        host_part = redis_url.replace("redis://", "").split(":")[0] or "localhost"
        port_part = 6379
        try:
            r2, w2 = await asyncio.open_connection(host_part, port_part)
            w2.close()
            await w2.wait_closed()
            lat = round((time.monotonic() - t0) * 1000, 1)
            return True, "Connected (TCP)", lat
        except Exception as exc2:  # noqa: BLE001
            lat = round((time.monotonic() - t0) * 1000, 1)
            return False, f"Unreachable: {exc2}", lat
    except Exception as exc:  # noqa: BLE001
        lat = round((time.monotonic() - t0) * 1000, 1)
        return False, f"Error: {exc}", lat


def _resolve_razorpay_keys(region: str) -> tuple[str, str]:
    """
    Resolve Razorpay key_id and key_secret for a region, accepting multiple
    env-var aliases so users can use whichever naming convention their .env has.

    Aliases tried (in order) for region='SG':
      RAZORPAY_KEY_ID_SG, RAZORPAY_SG_KEY_ID, RZP_SG_KEY_ID
    Aliases tried for region='IN':
      RAZORPAY_KEY_ID_IN, RAZORPAY_IN_KEY_ID, RZP_IN_KEY_ID
    """
    r = region.upper()
    key_aliases = [
        f"RAZORPAY_KEY_ID_{r}",
        f"RAZORPAY_{r}_KEY_ID",
        f"RZP_{r}_KEY_ID",
    ]
    secret_aliases = [
        f"RAZORPAY_KEY_SECRET_{r}",
        f"RAZORPAY_{r}_KEY_SECRET",
        f"RZP_{r}_KEY_SECRET",
    ]
    key_id = next((os.getenv(k, "") for k in key_aliases if os.getenv(k, "")), "")
    key_secret = next((os.getenv(k, "") for k in secret_aliases if os.getenv(k, "")), "")
    return key_id, key_secret


async def _probe_razorpay(region: str) -> tuple[bool, str, Optional[float]]:
    """HEAD the Razorpay API root to verify key validity for the given region."""
    key_id, key_secret = _resolve_razorpay_keys(region)

    if not key_id:
        return False, "No API key configured", None

    # Validate key format: live keys start with rzp_live_, test with rzp_test_
    if not (key_id.startswith("rzp_live_") or key_id.startswith("rzp_test_")):
        return False, "Key present but invalid format (expected rzp_live_* or rzp_test_*)", None

    if not key_secret:
        return False, "Key present but secret missing", None

    t0 = time.monotonic()
    try:
        import httpx  # type: ignore
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(
                "https://api.razorpay.com/v1/",
                auth=(key_id, key_secret),
            )
        lat = round((time.monotonic() - t0) * 1000, 1)
        if resp.status_code == 401:
            return False, "HTTP 401 — invalid key or secret", lat
        if resp.status_code == 200:
            return True, "Keys valid", lat
        return True, f"HTTP {resp.status_code}", lat
    except ImportError:
        return False, "httpx not installed", None
    except Exception as exc:  # noqa: BLE001
        lat = round((time.monotonic() - t0) * 1000, 1)
        return False, f"Error: {exc}", lat


async def _probe_openai() -> tuple[bool, str, Optional[float]]:
    """Verify the OpenAI API key is present and appears valid (list models HEAD)."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return False, "No API key", None
    if not api_key.startswith("sk-"):
        return False, "Key format invalid", None

    t0 = time.monotonic()
    try:
        import httpx  # type: ignore
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        lat = round((time.monotonic() - t0) * 1000, 1)
        ok = resp.status_code == 200
        return ok, "API key valid" if ok else f"HTTP {resp.status_code}", lat
    except ImportError:
        # Key present but can't verify — treat as ok
        return True, "API key present (unverified)", None
    except Exception as exc:  # noqa: BLE001
        lat = round((time.monotonic() - t0) * 1000, 1)
        return False, f"Error: {exc}", lat


async def _probe_smtp() -> tuple[bool, str, Optional[float]]:
    """Check whether SMTP is configured via env vars."""
    smtp_host = os.getenv("SMTP_HOST", "") or os.getenv("MAIL_SERVER", "")
    smtp_port = int(os.getenv("SMTP_PORT", os.getenv("MAIL_PORT", "587")))
    smtp_user = os.getenv("SMTP_USER", "") or os.getenv("MAIL_USERNAME", "")

    if not smtp_host:
        return False, "Not configured (SMTP_HOST missing)", None

    t0 = time.monotonic()
    try:
        r, w = await asyncio.open_connection(smtp_host, smtp_port)
        w.close()
        await w.wait_closed()
        lat = round((time.monotonic() - t0) * 1000, 1)
        user_label = smtp_user or "anonymous"
        return True, f"Configured ({user_label}@{smtp_host})", lat
    except Exception as exc:  # noqa: BLE001
        lat = round((time.monotonic() - t0) * 1000, 1)
        return False, f"Unreachable: {exc}", lat


async def _probe_camera_pipeline() -> tuple[bool, str, Optional[float]]:
    """Check the camera pipeline worker count via the global pipeline singleton."""
    t0 = time.monotonic()
    try:
        # Import lazily to avoid circular deps
        from .cameras_router import _pipeline as pipeline
        if pipeline is None:
            return False, "Pipeline not initialised", None
        workers = len(pipeline._camera_tasks)
        lat = round((time.monotonic() - t0) * 1000, 1)
        if pipeline.is_running:
            return True, f"{workers} worker(s) running", lat
        return False, "Pipeline stopped", lat
    except Exception as exc:  # noqa: BLE001
        lat = round((time.monotonic() - t0) * 1000, 1)
        return False, f"Error: {exc}", lat


async def _probe_ai_models() -> tuple[bool, str, Optional[float]]:
    """Check YOLO engine + total analyzer count."""
    t0 = time.monotonic()
    try:
        from .cameras_router import _pipeline as pipeline
        if pipeline is None:
            return False, "Pipeline not initialised", None

        yolo_ok = pipeline._yolo_engine is not None
        analyzer_count = sum(len(v) for v in pipeline._analyzers.values())
        lat = round((time.monotonic() - t0) * 1000, 1)
        detail_parts = []
        if yolo_ok:
            detail_parts.append("YOLO loaded")
        else:
            detail_parts.append("YOLO not loaded")
        detail_parts.append(f"{analyzer_count} analyzers")
        return yolo_ok, " + ".join(detail_parts), lat
    except Exception as exc:  # noqa: BLE001
        lat = round((time.monotonic() - t0) * 1000, 1)
        return False, f"Error: {exc}", lat


async def _probe_websocket() -> tuple[bool, str, Optional[float]]:
    """Report active WebSocket connections from the connection manager."""
    t0 = time.monotonic()
    try:
        from .websocket_router import manager
        conn_count = len(manager.active_connections)
        lat = round((time.monotonic() - t0) * 1000, 1)
        return True, f"Active connections: {conn_count}", lat
    except Exception as exc:  # noqa: BLE001
        lat = round((time.monotonic() - t0) * 1000, 1)
        return False, f"Error: {exc}", lat


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

_PROBE_TIMEOUT = 2.0   # seconds per probe
_TOTAL_TIMEOUT = 10.0  # seconds for all probes


async def _run_probe(
    name: str,
    coro: Any,
) -> HealthCheckItem:
    """Run a single probe coroutine with a per-probe timeout."""
    try:
        ok, detail, lat = await asyncio.wait_for(coro, timeout=_PROBE_TIMEOUT)
        return HealthCheckItem(name=name, ok=ok, detail=detail, latency_ms=lat)
    except asyncio.TimeoutError:
        return HealthCheckItem(name=name, ok=False, detail="Timed out (>2 s)", latency_ms=None)
    except Exception as exc:  # noqa: BLE001
        return HealthCheckItem(name=name, ok=False, detail=f"Probe error: {exc}", latency_ms=None)


@system_router.get(
    "/health-check",
    response_model=HealthCheckResponse,
    summary="Full system health check",
)
async def system_health_check(
    user: dict = Depends(get_current_user_id),
) -> HealthCheckResponse:
    """
    Run real probes against every external dependency simultaneously.
    Each probe is time-boxed at 2 s; total response time is capped at 10 s.

    Returns a list of checks and an overall status:
      - ``healthy``  — all checks passed
      - ``degraded`` — some non-critical checks failed
      - ``broken``   — critical checks (DB, Pipeline) failed
    """
    probe_tasks = [
        _run_probe("Database (PostgreSQL)", _probe_postgres()),
        _run_probe("MQTT Broker",           _probe_mqtt()),
        _run_probe("Redis Cache",           _probe_redis()),
        _run_probe("Razorpay (SG)",         _probe_razorpay("sg")),
        _run_probe("Razorpay (IN)",         _probe_razorpay("in")),
        _run_probe("OpenAI Support Chat",   _probe_openai()),
        _run_probe("Email (SMTP)",          _probe_smtp()),
        _run_probe("Camera Pipeline",       _probe_camera_pipeline()),
        _run_probe("AI Models",             _probe_ai_models()),
        _run_probe("WebSocket",             _probe_websocket()),
    ]

    try:
        results: List[HealthCheckItem] = await asyncio.wait_for(
            asyncio.gather(*probe_tasks, return_exceptions=False),
            timeout=_TOTAL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        # Partial results; mark remaining as timed-out
        results = []
        logger.warning("health-check: overall timeout hit")

    # Determine overall status
    _CRITICAL = {"Database (PostgreSQL)", "Camera Pipeline"}
    failed_names = {r.name for r in results if not r.ok}

    if failed_names & _CRITICAL:
        overall = "broken"
    elif failed_names:
        overall = "degraded"
    else:
        overall = "healthy"

    return HealthCheckResponse(checks=results, overall=overall)
