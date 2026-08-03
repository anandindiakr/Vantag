"""System health tracking + administrator fault alerting.

Purpose
-------
Historically, backend faults degraded *silently*: the AI Assistant caught
``ModuleNotFoundError`` and answered "I'm currently running in limited mode",
and the Edge Agent fell back from YOLO26 to YOLOv8 with only a local console
warning. In both cases the product kept "working" while a core capability was
dead, and nobody was told. The administrator only found out by manually
testing the feature and complaining.

This module is the single place that records a fault and notifies the
administrator by email.

Design notes
------------
* **SQLite-backed, not in-process.** The backend runs ``uvicorn --workers 2``,
  so a module-level dict would be per-process and the admin panel would show
  random/stale data (the same defect that made People Count read 0). State
  lives in ``backend/db/system_health_store.py``.
* **Deduplicated with a cooldown.** A failing component is usually hit
  repeatedly (every chat message, every 30s heartbeat). Emailing per
  occurrence would bury the signal, so each ``component`` emails at most once
  per ``ALERT_COOLDOWN_MIN``. Occurrences are still counted, and the counter
  appears in the email so severity is visible.
* **Never raises.** Every entry point swallows its own errors. Alerting about
  a fault must not itself become a fault.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..db import system_health_store as _store

logger = logging.getLogger("vantag.system_health")

# Administrator address. Overridable via env so it is not hardcoded to one
# person forever, but defaults to the platform owner so alerting works even if
# the variable was never set on the VPS.
ADMIN_ALERT_EMAIL = (
    os.getenv("ADMIN_ALERT_EMAIL", "").strip() or "anandindiakr@gmail.com"
)

ALERT_COOLDOWN_MIN = int(os.getenv("ADMIN_ALERT_COOLDOWN_MIN", "60"))
_COOLDOWN_SEC = ALERT_COOLDOWN_MIN * 60

# Human-readable impact so the email explains consequence, not just an error
# string. Keys must match the ``component`` passed to report_fault().
COMPONENT_IMPACT = {
    "ai_assistant": (
        "The in-app AI Assistant cannot answer questions. Users see a "
        "'limited mode' message and are redirected to email support."
    ),
    "model_fallback": (
        "An Edge Agent is NOT running the intended YOLO26 detector and has "
        "fallen back to the older YOLOv8 path. Detection accuracy and "
        "people-count precision are reduced."
    ),
    "vlm_verification": (
        "AI verification of inventory/theft events is unavailable, so events "
        "are recorded without second-stage confirmation."
    ),
    "email_dispatch": (
        "Outbound email is failing. Password resets and alert emails may not "
        "be delivered."
    ),
}


async def report_fault(
    component: str,
    summary: str,
    detail: str = "",
    tenant_id: Optional[str] = None,
) -> None:
    """Record a fault and email the administrator (at most once per cooldown).

    Safe to call from anywhere, including inside an ``except`` block — it never
    raises.
    """
    try:
        rec = _store.record_fault(component, summary, detail, tenant_id)
        occurrences = rec.get("occurrences", 1)
        last_alert = rec.get("last_alert_ts")

        if last_alert and (time.time() - float(last_alert)) < _COOLDOWN_SEC:
            logger.warning(
                "Fault in %s (occurrence #%s, admin already notified): %s",
                component, occurrences, summary,
            )
            return

        _store.mark_alerted(component)
        logger.error("Fault in %s — notifying admin: %s", component, summary)
        await _email_admin(component, rec)
    except Exception:  # noqa: BLE001 — alerting must never propagate
        logger.exception("report_fault(%s) failed", component)


def clear_fault(component: str) -> None:
    """Mark a component healthy again. Safe if it was never faulty."""
    try:
        _store.resolve_fault(component)
    except Exception:  # noqa: BLE001
        logger.exception("clear_fault(%s) failed", component)


def snapshot(tenant_id: Optional[str] = None) -> dict[str, Any]:
    """Return current health for the admin panel.

    ``degraded`` lists components with an unresolved fault. This is derived
    from real recorded faults only — it never reports healthy-by-default for a
    component that has never been exercised, so the panel cannot claim
    something works when it has simply never been tested.
    """
    try:
        faults = [_fmt_fault(r) for r in _store.list_faults()]
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read fault store")
        faults = []
    try:
        agents = _store.list_agent_model_status(tenant_id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read agent model status")
        agents = []

    degraded = [f for f in faults if not f["resolved_at"]]

    # An agent running the fallback detector is a degraded state even if no
    # explicit fault row was written (e.g. the fault predates this build).
    fallback_agents = [
        a for a in agents
        if not a.get("stale") and a.get("status", {}).get("is_preferred") is False
    ]

    return {
        "healthy": not degraded and not fallback_agents,
        "degraded_count": len(degraded) + len(fallback_agents),
        "degraded": degraded,
        "faults": faults,
        "agents": agents,
        "fallback_agent_count": len(fallback_agents),
        "admin_alert_email": ADMIN_ALERT_EMAIL,
        "alert_cooldown_minutes": ALERT_COOLDOWN_MIN,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _fmt_fault(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "component": r.get("component"),
        "summary": r.get("summary"),
        "detail": r.get("detail"),
        "tenant_id": r.get("tenant_id"),
        "occurrences": r.get("occurrences", 0),
        "first_seen": _iso(r.get("first_seen_ts")),
        "last_seen": _iso(r.get("last_seen_ts")),
        "last_alert_at": _iso(r.get("last_alert_ts")),
        "resolved_at": _iso(r.get("resolved_ts")),
        "impact": COMPONENT_IMPACT.get(r.get("component") or "", ""),
    }


def _iso(ts: Any) -> Optional[str]:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return None


async def _email_admin(component: str, rec: dict[str, Any]) -> None:
    """Send the fault notification. Failures are logged, never raised."""
    try:
        from .email_service import send_email, _base_html
    except Exception:  # noqa: BLE001
        logger.exception("email_service unavailable — cannot alert admin")
        return

    impact = COMPONENT_IMPACT.get(component, "")
    summary = rec.get("summary") or component
    detail = (rec.get("detail") or "").replace("<", "&lt;").replace(">", "&gt;")

    detail_block = (
        f'<pre style="background:rgba(255,255,255,0.06);padding:12px;'
        f'border-radius:8px;white-space:pre-wrap;font-size:12px;'
        f'color:#e5e7eb">{detail}</pre>'
        if detail else ""
    )
    impact_block = (
        f'<p style="color:#fca5a5"><strong>Impact:</strong> {impact}</p>'
        if impact else ""
    )

    body = f"""
      <p><strong>Component:</strong> {component}</p>
      <p><strong>Problem:</strong> {summary}</p>
      {impact_block}
      <p><strong>First seen:</strong> {_iso(rec.get('first_seen_ts'))}<br/>
         <strong>Occurrences so far:</strong> {rec.get('occurrences')}</p>
      {detail_block}
      <p style="color:#9ca3af;font-size:12px">
        You are receiving this because you are the platform administrator.
        Repeats of this same fault are suppressed for {ALERT_COOLDOWN_MIN}
        minutes to avoid inbox flooding — the occurrence counter above keeps
        incrementing, and the live state is on the Admin &rarr; System Health
        page.
      </p>
    """

    try:
        await send_email(
            to=ADMIN_ALERT_EMAIL,
            subject=f"[Vantag] System fault: {summary}",
            html=_base_html("System fault detected", body),
            text=f"{component}: {summary}\n\n{rec.get('detail') or ''}",
        )
        logger.info("Admin fault alert emailed to %s", ADMIN_ALERT_EMAIL)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to email admin fault alert")
