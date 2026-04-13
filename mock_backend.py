"""
Vantag Mock Backend — Demo server with simulated live data.
Runs on port 8000. No ML or camera dependencies required.

Start with:
    python mock_backend.py
"""

import asyncio
import json
import math
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Vantag Mock API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static demo data ──────────────────────────────────────────────────────────

STORES = [
    {"id": "store-001", "name": "Nazar Flagship — Dubai Mall", "location": "Dubai, UAE",
     "address": "Dubai Mall, Financial Centre Rd, Dubai", "cameraCount": 8,
     "active": True, "timezone": "Asia/Dubai", "openHours": {"open": "10:00", "close": "22:00"}},
    {"id": "store-002", "name": "Nazar Marina Walk", "location": "Dubai Marina, UAE",
     "address": "Marina Walk, Dubai Marina, Dubai", "cameraCount": 4,
     "active": True, "timezone": "Asia/Dubai", "openHours": {"open": "09:00", "close": "23:00"}},
    {"id": "store-003", "name": "Nazar Abu Dhabi", "location": "Abu Dhabi, UAE",
     "address": "Yas Island, Abu Dhabi", "cameraCount": 6,
     "active": True, "timezone": "Asia/Dubai", "openHours": {"open": "10:00", "close": "22:00"}},
    {"id": "store-004", "name": "Nazar JBR", "location": "JBR, Dubai, UAE",
     "address": "Jumeirah Beach Residence, Dubai", "cameraCount": 5,
     "active": True, "timezone": "Asia/Dubai", "openHours": {"open": "10:00", "close": "23:00"}},
]

CAMERAS = [
    {"id": "cam-001", "storeId": "store-001", "name": "Entrance Cam A", "location": "Main Entrance",
     "streamUrl": "rtsp://192.168.1.10:554/stream1", "online": True, "fps": 30,
     "resolution": "1920x1080", "zones": [
         {"id": "z1", "name": "Entry Zone", "points": [{"x": 0, "y": 0}, {"x": 320, "y": 0}, {"x": 320, "y": 240}, {"x": 0, "y": 240}], "type": "entry"}]},
    {"id": "cam-002", "storeId": "store-001", "name": "Jewellery Aisle", "location": "Aisle B",
     "streamUrl": "rtsp://192.168.1.11:554/stream1", "online": True, "fps": 25,
     "resolution": "1920x1080", "zones": [
         {"id": "z2", "name": "High-Value Shelf", "points": [{"x": 100, "y": 100}, {"x": 500, "y": 100}, {"x": 500, "y": 400}, {"x": 100, "y": 400}], "type": "shelf"}]},
    {"id": "cam-003", "storeId": "store-001", "name": "Checkout Counter", "location": "POS Area",
     "streamUrl": "rtsp://192.168.1.12:554/stream1", "online": True, "fps": 30,
     "resolution": "1280x720", "zones": [
         {"id": "z3", "name": "Checkout Zone", "points": [{"x": 0, "y": 200}, {"x": 640, "y": 200}, {"x": 640, "y": 480}, {"x": 0, "y": 480}], "type": "checkout"}]},
    {"id": "cam-004", "storeId": "store-001", "name": "Stock Room Door", "location": "Back Room",
     "streamUrl": "rtsp://192.168.1.13:554/stream1", "online": False, "fps": 0,
     "resolution": "1280x720", "zones": [
         {"id": "z4", "name": "Restricted Area", "points": [{"x": 0, "y": 0}, {"x": 640, "y": 0}, {"x": 640, "y": 480}, {"x": 0, "y": 480}], "type": "restricted"}]},
    {"id": "cam-005", "storeId": "store-002", "name": "Marina Entrance", "location": "Front Door",
     "streamUrl": "rtsp://192.168.2.10:554/stream1", "online": True, "fps": 30,
     "resolution": "1920x1080", "zones": []},
    {"id": "cam-006", "storeId": "store-002", "name": "Marina Aisle 1", "location": "Aisle A",
     "streamUrl": "rtsp://192.168.2.11:554/stream1", "online": True, "fps": 25,
     "resolution": "1920x1080", "zones": []},
    {"id": "cam-007", "storeId": "store-003", "name": "Abu Dhabi Main", "location": "Entrance",
     "streamUrl": "rtsp://192.168.3.10:554/stream1", "online": True, "fps": 30,
     "resolution": "1920x1080", "zones": []},
    {"id": "cam-008", "storeId": "store-004", "name": "JBR Entry", "location": "Entrance",
     "streamUrl": "rtsp://192.168.4.10:554/stream1", "online": True, "fps": 30,
     "resolution": "1920x1080", "zones": []},
]

WATCHLIST = [
    {"id": "wl-001", "name": "Person of Interest A", "alertLevel": "HIGH",
     "faceImageUrl": None, "notes": "Suspected shoplifter — multiple sightings",
     "addedAt": "2024-11-15T09:00:00Z", "lastMatchAt": "2024-12-01T14:23:00Z",
     "matchCount": 4, "active": True},
    {"id": "wl-002", "name": "Known Offender B", "alertLevel": "CRITICAL",
     "faceImageUrl": None, "notes": "Banned from all stores — court order",
     "addedAt": "2024-10-01T08:00:00Z", "lastMatchAt": "2024-11-28T11:05:00Z",
     "matchCount": 7, "active": True},
    {"id": "wl-003", "name": "Suspect C", "alertLevel": "MEDIUM",
     "faceImageUrl": None, "notes": "Under observation — loitering incidents",
     "addedAt": "2025-01-10T10:00:00Z", "lastMatchAt": None,
     "matchCount": 0, "active": True},
]

INCIDENTS = [
    {"id": "inc-001", "storeId": "store-001", "storeName": "Nazar Flagship — Dubai Mall",
     "cameraId": "cam-002", "cameraName": "Jewellery Aisle", "type": "sweep",
     "severity": "HIGH", "riskScore": 82.5,
     "description": "Suspected product sweeping detected — 3 items removed rapidly from shelf B",
     "ts": "2025-06-04T08:12:00Z", "resolved": False, "resolvedAt": None, "reportUrl": None},
    {"id": "inc-002", "storeId": "store-001", "storeName": "Nazar Flagship — Dubai Mall",
     "cameraId": "cam-001", "cameraName": "Entrance Cam A", "type": "watchlist_match",
     "severity": "CRITICAL", "riskScore": 95.0,
     "description": "Watchlist match: Known Offender B detected at main entrance",
     "ts": "2025-06-04T07:45:00Z", "resolved": True, "resolvedAt": "2025-06-04T07:55:00Z", "reportUrl": None},
    {"id": "inc-003", "storeId": "store-002", "storeName": "Nazar Marina Walk",
     "cameraId": "cam-005", "cameraName": "Marina Entrance", "type": "dwell",
     "severity": "MEDIUM", "riskScore": 61.0,
     "description": "Anomalous dwell time — individual remained near entrance for 18 minutes",
     "ts": "2025-06-04T06:30:00Z", "resolved": False, "resolvedAt": None, "reportUrl": None},
    {"id": "inc-004", "storeId": "store-001", "storeName": "Nazar Flagship — Dubai Mall",
     "cameraId": "cam-003", "cameraName": "Checkout Counter", "type": "theft_attempt",
     "severity": "HIGH", "riskScore": 78.0,
     "description": "POS discrepancy detected — camera count vs scanned items mismatch",
     "ts": "2025-06-04T05:00:00Z", "resolved": True, "resolvedAt": "2025-06-04T05:20:00Z", "reportUrl": None},
    {"id": "inc-005", "storeId": "store-003", "storeName": "Nazar Abu Dhabi",
     "cameraId": "cam-007", "cameraName": "Abu Dhabi Main", "type": "empty_shelf",
     "severity": "LOW", "riskScore": 35.0,
     "description": "Empty shelf detected on aisle 3 — restocking required",
     "ts": "2025-06-03T14:15:00Z", "resolved": False, "resolvedAt": None, "reportUrl": None},
]

# ── Live state (mutated by background task) ───────────────────────────────────

_risk_scores: dict[str, dict] = {}
_connected_ws: list[WebSocket] = []

EVENT_TYPES = [
    ("sweep", "HIGH", "Possible product sweep detected near shelf {zone}"),
    ("dwell", "MEDIUM", "Extended dwell time — person stationary for {minutes} minutes"),
    ("empty_shelf", "LOW", "Empty shelf detected on aisle {zone}"),
    ("queue_alert", "MEDIUM", "Queue depth exceeded threshold — {count} people waiting"),
    ("loitering", "MEDIUM", "Loitering detected near {zone}"),
    ("watchlist_match", "CRITICAL", "Watchlist match detected — confidence {conf}%"),
    ("door_event", "LOW", "Door opened at {zone}"),
]

def _risk_history() -> list[dict]:
    """30-point rolling history over last 30 minutes."""
    now = time.time()
    return [
        {"ts": int(now - (30 - i) * 60 * 1000),
         "score": 20 + random.gauss(30, 15)}
        for i in range(30)
    ]

def _init_risk_scores() -> None:
    base_scores = {"store-001": 72.0, "store-002": 38.0,
                   "store-003": 21.0, "store-004": 55.0}
    sev_map = {(0, 30): "LOW", (30, 60): "MEDIUM",
               (60, 80): "HIGH", (80, 101): "CRITICAL"}
    for store in STORES:
        sid = store["id"]
        score = base_scores[sid]
        sev = next(s for (lo, hi), s in sev_map.items() if lo <= score < hi)
        _risk_scores[sid] = {
            "storeId": sid,
            "score": round(score, 1),
            "severity": sev,
            "factors": [
                {"name": "Sweep Detection", "weight": 0.35, "value": round(score * 0.35, 1),
                 "description": "Product sweeping probability based on motion analysis"},
                {"name": "Dwell Anomaly", "weight": 0.25, "value": round(score * 0.25, 1),
                 "description": "Anomalous loitering or stationary behaviour"},
                {"name": "Facial Recognition", "weight": 0.20, "value": round(score * 0.20, 1),
                 "description": "Watchlist match confidence"},
                {"name": "Queue Stress", "weight": 0.10, "value": round(score * 0.10, 1),
                 "description": "Customer queue depth and wait times"},
                {"name": "Shelf Coverage", "weight": 0.10, "value": round(score * 0.10, 1),
                 "description": "Empty shelf detection ratio"},
            ],
            "history": _risk_history(),
            "computedAt": datetime.now(timezone.utc).isoformat(),
        }

_init_risk_scores()

# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0-mock", "uptime": 99.9}

@app.get("/api/stores")
def list_stores():
    return STORES

@app.get("/api/stores/{store_id}")
def get_store(store_id: str):
    for s in STORES:
        if s["id"] == store_id:
            return s
    return STORES[0]

@app.get("/api/stores/{store_id}/risk")
def get_risk(store_id: str):
    return _risk_scores.get(store_id, _risk_scores["store-001"])

@app.get("/api/stores/{store_id}/heatmap")
def get_heatmap(store_id: str, window: int = 30):
    rows, cols = 20, 30
    t = time.time()
    grid = [
        [
            max(0, int(50 + 40 * math.sin(t / 30 + r * 0.5 + c * 0.3) +
                       random.gauss(0, 10)))
            for c in range(cols)
        ]
        for r in range(rows)
    ]
    return {
        "storeId": store_id, "grid": grid, "rows": rows, "cols": cols,
        "windowMinutes": window,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/api/stores/{store_id}/incidents")
def get_store_incidents(store_id: str, page: int = 1, page_size: int = 25):
    items = [i for i in INCIDENTS if i["storeId"] == store_id]
    return {"items": items, "total": len(items), "page": page, "pages": 1}

@app.get("/api/incidents")
def get_all_incidents(page: int = 1, page_size: int = 25):
    return {"items": INCIDENTS, "total": len(INCIDENTS), "page": page, "pages": 1}

@app.get("/api/cameras")
def list_cameras(store_id: str | None = None):
    if store_id:
        return [c for c in CAMERAS if c["storeId"] == store_id]
    return CAMERAS

@app.get("/api/cameras/{camera_id}")
def get_camera(camera_id: str):
    for c in CAMERAS:
        if c["id"] == camera_id:
            return c
    return CAMERAS[0]

@app.get("/api/queue-status")
def get_queue_status():
    return [
        {
            "storeId": s["id"],
            "lanes": [
                {"laneId": f"lane-{s['id']}-1", "name": "Checkout 1",
                 "depth": random.randint(0, 8), "waitTimeSec": random.randint(30, 300), "open": True},
                {"laneId": f"lane-{s['id']}-2", "name": "Checkout 2",
                 "depth": random.randint(0, 4), "waitTimeSec": random.randint(20, 180), "open": random.choice([True, True, False])},
            ],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        for s in STORES
    ]

@app.get("/api/watchlist")
def get_watchlist():
    return WATCHLIST

@app.get("/api/watchlist/matches")
def get_watchlist_matches():
    return [
        {
            "id": str(uuid.uuid4()),
            "entryId": "wl-002",
            "entryName": "Known Offender B",
            "storeId": "store-001",
            "cameraId": "cam-001",
            "cameraName": "Entrance Cam A",
            "confidence": 0.91,
            "thumbnailUrl": None,
            "ts": "2024-12-01T14:23:00Z",
        }
    ]

@app.post("/api/watchlist")
async def add_watchlist():
    return {"id": str(uuid.uuid4()), "name": "New Entry", "alertLevel": "MEDIUM",
            "notes": "", "addedAt": datetime.now(timezone.utc).isoformat(),
            "matchCount": 0, "active": True}

@app.delete("/api/watchlist/{entry_id}")
def delete_watchlist(entry_id: str):
    return {"deleted": entry_id}

@app.get("/api/reports/generate/{incident_id}")
def generate_report(incident_id: str):
    return {"reportUrl": f"/snapshots/reports/{incident_id}.pdf", "status": "generated"}

@app.post("/api/doors/{store_id}/lock")
def lock_door(store_id: str):
    return {"storeId": store_id, "action": "lock", "success": True,
            "ts": datetime.now(timezone.utc).isoformat()}

@app.post("/api/doors/{store_id}/unlock")
def unlock_door(store_id: str):
    return {"storeId": store_id, "action": "unlock", "success": True,
            "ts": datetime.now(timezone.utc).isoformat()}

# ── WebSocket — real-time event stream ───────────────────────────────────────

@app.websocket("/ws/{store_id}")
async def websocket_endpoint(websocket: WebSocket, store_id: str):
    await websocket.accept()
    _connected_ws.append(websocket)
    try:
        # Send current risk score immediately on connect
        await websocket.send_text(json.dumps({
            "type": "risk_update",
            "storeId": store_id,
            "data": _risk_scores.get(store_id, _risk_scores["store-001"]),
        }))
        while True:
            # Keep-alive — client messages are ignored in demo
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _connected_ws:
            _connected_ws.remove(websocket)

# ── Background task — mutate risk scores & broadcast events ─────────────────

async def simulate_live_data() -> None:
    """Every 4 seconds nudge risk scores and emit a random event."""
    sev_map = [(0, 30, "LOW"), (30, 60, "MEDIUM"), (60, 80, "HIGH"), (80, 101, "CRITICAL")]

    while True:
        await asyncio.sleep(4)

        # Pick a random store to update
        store = random.choice(STORES)
        sid = store["id"]
        rs = _risk_scores[sid]

        # Nudge score ±5
        new_score = max(5.0, min(98.0, rs["score"] + random.uniform(-5, 5)))
        sev = next(s for (lo, hi, s) in sev_map if lo <= new_score < hi)
        rs["score"] = round(new_score, 1)
        rs["severity"] = sev
        rs["computedAt"] = datetime.now(timezone.utc).isoformat()
        rs["history"] = rs["history"][1:] + [
            {"ts": int(time.time() * 1000), "score": round(new_score, 1)}
        ]

        # Build a random event
        cam = random.choice([c for c in CAMERAS if c["storeId"] == sid] or CAMERAS[:1])
        ev_type, sev_ev, tmpl = random.choice(EVENT_TYPES)
        desc = tmpl.format(
            zone=random.choice(["Aisle B", "Entrance", "Checkout", "Back Room"]),
            minutes=random.randint(5, 25),
            count=random.randint(4, 12),
            conf=random.randint(80, 99),
        )

        event_payload: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "storeId": sid,
            "cameraId": cam["id"],
            "cameraName": cam["name"],
            "type": ev_type,
            "severity": sev_ev,
            "description": desc,
            "confidence": round(random.uniform(0.72, 0.98), 2),
            "ts": datetime.now(timezone.utc).isoformat(),
            "metadata": {},
        }

        risk_payload = {
            "type": "risk_update",
            "storeId": sid,
            "data": rs,
        }
        event_msg = {
            "type": "event",
            "storeId": sid,
            "data": event_payload,
        }

        dead = []
        for ws in list(_connected_ws):
            try:
                await ws.send_text(json.dumps(risk_payload))
                await ws.send_text(json.dumps(event_msg))
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in _connected_ws:
                _connected_ws.remove(ws)


@app.on_event("startup")
async def startup():
    asyncio.create_task(simulate_live_data())


if __name__ == "__main__":
    uvicorn.run("mock_backend:app", host="0.0.0.0", port=8001, reload=False, log_level="info")
