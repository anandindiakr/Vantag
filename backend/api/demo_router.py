"""
backend/api/demo_router.py
===========================
Demo & test endpoints — inject synthetic incidents into the live pipeline
so operators can demonstrate any detection type on demand.

All injected events appear immediately in:
  - /api/stores/{store_id}/incidents   (Incidents page)
  - /api/stores/{store_id}/risk        (Dashboard risk scores)
  - WebSocket broadcast                (Live alert feed)
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..middleware.tenant_middleware import get_current_user_id as get_current_user

# Populated by main.py via set_pipeline()
_pipeline = None   # type: ignore[assignment]

# Snapshot storage (same root that main.py already mounts as /snapshots/*)
_SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent / "snapshots"
_DEMO_SNAPS_DIR = _SNAPSHOTS_DIR / "demo"


def set_pipeline(p) -> None:  # type: ignore[no-untyped-def]
    global _pipeline  # noqa: PLW0603
    _pipeline = p


router = APIRouter(prefix="/api/demo", tags=["Demo"])

# ── Event weights ─────────────────────────────────────────────────────────────
_EVENT_WEIGHTS: dict[str, int] = {
    "face_match":         40,
    "shoplifting":        30,
    "tamper":             25,
    "fall_detected":      25,
    "restricted_zone":    20,
    "loitering":          15,
    "inventory_movement": 10,
    "queue_breach":       10,
}

# ── Camera → store mapping ────────────────────────────────────────────────────
_CAM_TO_STORE: dict[str, str] = {
    "cam-01": "zone_a",
    "cam-02": "zone_b",
    "cam-03": "zone_c",
    "cam-04": "zone_d",
}
_STORE_NAMES: dict[str, str] = {
    "zone_a": "Zone A",
    "zone_b": "Zone B",
    "zone_c": "Zone C",
    "zone_d": "Zone D",
}

# ── Generic fallback descriptions (no zone context) ───────────────────────────
# Honest — no hardcoded counts, percentages, or durations.
_DESCRIPTIONS: dict[str, str] = {
    "shoplifting":        "Rapid product removal activity detected near shelf area. Review footage.",
    "fall_detected":      "Person-down event detected. Pose analysis indicates possible fall. Immediate attention required.",
    "restricted_zone":    "Unauthorised zone entry detected. No access permission on record for this time window.",
    "inventory_movement": "Item count change detected in monitored shelf zone. No authorised staff present in vicinity.",
    "queue_breach":       "Queue length exceeded configured threshold. Checkout assistance may be required.",
    "loitering":          "Individual stationary beyond configured dwell threshold in monitored zone.",
    "face_match":         "Positive watchlist match detected. Elevated alert level — review immediately.",
    "tamper":             "Camera tamper event detected: sudden scene change or possible occlusion of lens.",
}


def _zone_description(event_type: str, zone_name: str, zone_label: str, camera_id: str, bbox: list) -> str:
    """
    Generate a zone-specific, honest description.
    No hardcoded counts, durations, or confidence scores —
    only facts the system actually knows at trigger time.
    """
    cam   = camera_id
    coord = f"[{', '.join(str(v) for v in bbox)}]" if bbox else "N/A"
    now_t = datetime.now().strftime("%H:%M:%S")

    if event_type == "inventory_movement":
        return (
            f"Item count change detected in {zone_label} zone \"{zone_name}\" on {cam} at {now_t}. "
            f"No authorised staff detected in vicinity at time of event. "
            f"Zone coordinates: {coord}."
        )
    if event_type == "shoplifting":
        return (
            f"Rapid product removal activity detected near {zone_label} zone \"{zone_name}\" "
            f"on {cam} at {now_t}. Suspect last seen at zone boundary. "
            f"Zone coordinates: {coord}."
        )
    if event_type == "restricted_zone":
        return (
            f"Unauthorised entry into restricted area \"{zone_name}\" on {cam} at {now_t}. "
            f"Person detected inside zone. No access permission on record for this time window. "
            f"Zone coordinates: {coord}."
        )
    if event_type == "queue_breach":
        return (
            f"Queue length exceeded configured threshold in \"{zone_name}\" on {cam} at {now_t}. "
            f"Checkout assistance may be required. "
            f"Zone coordinates: {coord}."
        )
    if event_type == "loitering":
        return (
            f"Individual stationary beyond configured dwell threshold in "
            f"\"{zone_name}\" ({zone_label}) on {cam} at {now_t}. "
            f"Zone coordinates: {coord}."
        )
    if event_type == "fall_detected":
        return (
            f"Person-down event detected near \"{zone_name}\" zone on {cam} at {now_t}. "
            f"Pose analysis indicates possible fall. Immediate attention required. "
            f"Zone coordinates: {coord}."
        )
    if event_type == "face_match":
        return (
            f"Positive watchlist match detected near \"{zone_name}\" zone on {cam} at {now_t}. "
            f"Elevated alert level — review evidence immediately. "
            f"Zone coordinates: {coord}."
        )
    if event_type == "tamper":
        return (
            f"Camera tamper detected on {cam} at {now_t} — zone \"{zone_name}\" may be unmonitored. "
            f"Sudden scene change or physical occlusion of lens. "
            f"Zone coordinates: {coord}."
        )
    return (
        f"Event \"{event_type}\" detected in zone \"{zone_name}\" ({zone_label}) on {cam} at {now_t}. "
        f"Zone coordinates: {coord}."
    )


class TriggerRequest(BaseModel):
    event_type:   str            # one of _EVENT_WEIGHTS keys
    camera_id:    str  = "cam-03"
    severity:     str  = "high"
    # Zone context (optional — supplied by Zone Editor "Test Event" button)
    zone_name:    str        = ""
    zone_label:   str        = ""
    zone_bbox:    List[int]  = []
    snapshot_b64: str        = ""  # base64 data-URL of canvas JPEG


class TriggerResponse(BaseModel):
    incident_id:  str
    store_id:     str
    event_type:   str
    severity:     str
    description:  str
    occurred_at:  str
    snapshot_url: Optional[str] = None


def _save_snapshot(incident_id: str, snapshot_b64: str) -> Optional[str]:
    """Decode base64 canvas image and save to disk. Returns static URL or None."""
    if not snapshot_b64:
        return None
    try:
        _DEMO_SNAPS_DIR.mkdir(parents=True, exist_ok=True)
        raw       = snapshot_b64.split(",", 1)[-1]
        img_bytes = base64.b64decode(raw)
        img_path  = _DEMO_SNAPS_DIR / f"{incident_id}.jpg"
        img_path.write_bytes(img_bytes)
        return f"/snapshots/demo/{incident_id}.jpg"
    except Exception:  # noqa: BLE001
        return None


def _build_event(req: TriggerRequest, incident_id: str, snapshot_url: Optional[str] = None) -> dict:
    """
    Build a canonical event dict.

    KEY NAMES match the real AI pipeline's schema:
      "type"      — event type  (NOT "event_type")
      "timestamp" — ISO-8601    (NOT "occurred_at")

    stores_router.list_incidents() reads these keys. Using consistent names
    ensures demo events appear correctly in the Incidents page.
    """
    event_type  = req.event_type.lower()
    camera_id   = req.camera_id
    store_id    = _CAM_TO_STORE.get(camera_id, "zone_c")
    severity    = req.severity.lower()
    now_iso     = datetime.now(timezone.utc).isoformat()

    if req.zone_name:
        description = _zone_description(
            event_type, req.zone_name,
            req.zone_label or "Zone",
            camera_id, req.zone_bbox
        )
    else:
        description = _DESCRIPTIONS.get(event_type, f"Demo event: {event_type}")

    return {
        # ── canonical keys (match real pipeline) ──
        "incident_id":  incident_id,
        "type":         event_type,         # ← was "event_type"
        "timestamp":    now_iso,            # ← was "occurred_at"
        # ── additional fields ──
        "store_id":     store_id,
        "store_name":   _STORE_NAMES.get(store_id, store_id),
        "camera_id":    camera_id,
        "camera_name":  f"Camera — {_STORE_NAMES.get(store_id, store_id)} (Demo)",
        "severity":     severity,
        "risk_score":   _EVENT_WEIGHTS.get(event_type, 10) * 2,
        "description":  description,
        "acknowledged": False,
        "is_demo":      True,
        "snapshot_url": snapshot_url,
        "metadata":     {
            "zone_name":  req.zone_name,
            "zone_label": req.zone_label,
            "zone_bbox":  req.zone_bbox,
        } if req.zone_name else {},
    }


async def _inject(event: dict) -> None:
    """Push event into pipeline state + broadcast over WebSocket + persist to SQLite."""
    if _pipeline is None:
        return

    store_id   = event["store_id"]
    event_type = event["type"]              # canonical key
    weight     = _EVENT_WEIGHTS.get(event_type, 10)

    # 1. Append to recent_events (read by /incidents endpoint)
    _pipeline.recent_events[store_id].appendleft(event)

    # 2. Push into risk-score buffer
    async with _pipeline._event_buffer_lock:
        _pipeline._event_buffer[store_id].append(
            (event_type, weight, time.monotonic())
        )

    # 3. Persist to SQLite (fire-and-forget; import lazily to avoid circular)
    try:
        from ..db import incident_store as _istore  # type: ignore[import]
        await asyncio.to_thread(_istore.insert_incident, event)
    except Exception:  # noqa: BLE001
        pass  # persistence is best-effort — never block the event pipeline

    # 4. Broadcast to WebSocket clients
    if _pipeline._ws_broadcast:
        try:
            await _pipeline._ws_broadcast({
                "type":         "incident",
                "incident_id":  event["incident_id"],
                "store_id":     store_id,
                "camera_id":    event["camera_id"],
                "event_type":   event_type,
                "severity":     event["severity"],
                "description":  event["description"],
                "occurred_at":  event["timestamp"],
                "snapshot_url": event.get("snapshot_url"),
                "is_demo":      True,
            })
        except Exception:  # noqa: BLE001
            pass


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/trigger",
    response_model=TriggerResponse,
    summary="Fire a single demo incident",
)
async def trigger_event(
    req: TriggerRequest,
    _: dict = Depends(get_current_user),
) -> TriggerResponse:
    if req.event_type not in _EVENT_WEIGHTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown event_type '{req.event_type}'. "
                   f"Valid types: {list(_EVENT_WEIGHTS.keys())}",
        )

    incident_id  = f"demo-{uuid.uuid4().hex[:8]}"
    snapshot_url = _save_snapshot(incident_id, req.snapshot_b64)
    event        = _build_event(req, incident_id, snapshot_url)

    await _inject(event)
    return TriggerResponse(
        incident_id  = event["incident_id"],
        store_id     = event["store_id"],
        event_type   = event["type"],
        severity     = event["severity"],
        description  = event["description"],
        occurred_at  = event["timestamp"],
        snapshot_url = event.get("snapshot_url"),
    )


@router.post(
    "/trigger-sequence",
    summary="Fire ALL demo incidents in sequence",
)
async def trigger_sequence(
    _: dict = Depends(get_current_user),
) -> dict:
    sequence = [
        TriggerRequest(event_type="shoplifting",        camera_id="cam-03", severity="high"),
        TriggerRequest(event_type="fall_detected",      camera_id="cam-04", severity="critical"),
        TriggerRequest(event_type="restricted_zone",    camera_id="cam-01", severity="high"),
        TriggerRequest(event_type="inventory_movement", camera_id="cam-03", severity="medium"),
        TriggerRequest(event_type="queue_breach",       camera_id="cam-04", severity="medium"),
        TriggerRequest(event_type="loitering",          camera_id="cam-01", severity="medium"),
        TriggerRequest(event_type="face_match",         camera_id="cam-03", severity="critical"),
        TriggerRequest(event_type="tamper",             camera_id="cam-04", severity="high"),
    ]

    fired = []
    for req in sequence:
        incident_id = f"demo-{uuid.uuid4().hex[:8]}"
        event       = _build_event(req, incident_id)
        await _inject(event)
        fired.append({
            "event_type":  event["type"],
            "camera_id":   event["camera_id"],
            "store_id":    event["store_id"],
            "severity":    event["severity"],
            "incident_id": event["incident_id"],
        })
        await asyncio.sleep(0.3)

    return {"fired": len(fired), "events": fired}


@router.delete(
    "/clear",
    summary="Clear all demo incidents",
)
async def clear_demo_events(
    _: dict = Depends(get_current_user),
) -> dict:
    if _pipeline is None:
        return {"cleared": 0}

    total = 0
    for store_id, dq in _pipeline.recent_events.items():
        before   = len(dq)
        to_keep  = [e for e in dq if not e.get("is_demo", False)]
        dq.clear()
        for e in to_keep:
            dq.append(e)
        total += before - len(dq)

    return {"cleared": total, "message": "Demo incidents removed. Real incidents preserved."}


@router.get("/event-types", summary="List all demo-able event types")
async def list_event_types() -> dict:
    return {
        "event_types": [
            {
                "key":              k,
                "weight":           w,
                "description":      _DESCRIPTIONS[k],
                "severity_default": "critical" if w >= 25 else "high" if w >= 20 else "medium",
            }
            for k, w in _EVENT_WEIGHTS.items()
        ]
    }
