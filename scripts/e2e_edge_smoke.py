#!/usr/bin/env python3
"""
End-to-end smoke test for the Vantag Edge Agent integration.

Runs ON the VPS against the live backend (127.0.0.1:8000). Exercises the exact
path a real paid customer follows:

  1. Log in as a real tenant  -> JWT
  2. GET /api/agent/download   -> credentialed zip (extract config.json)
  3. POST /api/edge/heartbeat  -> camera shows ONLINE  (X-API-Key auth)
  4. POST /api/edge/events     -> detection w/ snapshot (X-API-Key auth)
  5. GET stores incidents      -> the edge event is visible
  6. GET snapshot_url          -> real JPEG bytes served back
"""
import base64
import io
import json
import sys
import zipfile
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
EMAIL = "sales-demo@retail-vantag.com"
PASSWORD = "VantagSales@2026"

# 1x1 white JPEG (valid baseline JPEG) so the snapshot save path is real.
TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAP//////////////////////////////////"
    "////////////////////////////////////////////////////wgALCAABAAEBAREA"
    "/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)


def req(method, path, token=None, api_key=None, body=None, raw=False):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    if api_key:
        headers["X-API-Key"] = api_key
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            payload = resp.read()
            return resp.status, payload if raw else _maybe_json(payload)
    except urllib.error.HTTPError as e:
        return e.code, _maybe_json(e.read())


def _maybe_json(b):
    try:
        return json.loads(b.decode())
    except Exception:
        return b


def step(n, msg):
    print("\n[STEP %s] %s" % (n, msg))


fail = []

# ---- 1. login -------------------------------------------------------------
step(1, "Login as sales-demo tenant")
code, res = req("POST", "/api/auth/login", body={"email": EMAIL, "password": PASSWORD})
print("  login ->", code)
token = None
if isinstance(res, dict):
    token = res.get("access_token") or res.get("token")
if code != 200 or not token:
    print("  body:", res)
    fail.append("login failed")
    print("\nRESULT: FAIL (cannot continue)")
    sys.exit(1)
print("  token OK")

# ---- 2. download credentialed package ------------------------------------
step(2, "GET /api/agent/download?platform=windows")
code, blob = req("GET", "/api/agent/download?platform=windows", token=token, raw=True)
print("  download ->", code, "(%d bytes)" % (len(blob) if isinstance(blob, (bytes, bytearray)) else 0))
cfg = None
if code == 200 and isinstance(blob, (bytes, bytearray)):
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = zf.namelist()
        print("  zip entries:", len(names))
        has_cfg = "config.json" in names
        has_runbat = any(n.endswith("run.bat") for n in names)
        has_agent = any(n.endswith("agent/main.py") for n in names)
        print("  config.json:", has_cfg, "| run.bat:", has_runbat, "| agent/main.py:", has_agent)
        if has_cfg:
            cfg = json.loads(zf.read("config.json").decode())
            print("  config keys:", sorted(cfg.keys()))
        if not (has_cfg and has_runbat and has_agent):
            fail.append("zip missing expected files")
    except Exception as e:
        fail.append("zip parse error: %s" % e)
else:
    fail.append("download failed")

if not cfg:
    print("\nRESULT: FAIL (no config.json)")
    sys.exit(1)

api_key = cfg.get("api_key")
agent_id = cfg.get("agent_id")
cameras = cfg.get("cameras") or []
print("  api_key present:", bool(api_key), "| agent_id:", agent_id, "| cameras:", len(cameras))
cam_id = (cameras[0]["camera_id"] if cameras and isinstance(cameras[0], dict) and "camera_id" in cameras[0]
          else (cameras[0] if cameras else "cam-smoke-1"))

# ---- 3. heartbeat ---------------------------------------------------------
step(3, "POST /api/edge/heartbeat (X-API-Key) -> camera ONLINE")
hb = {
    "agent_id": agent_id,
    # Backend HeartbeatBody.camera_statuses is dict[str, str] (camera_id -> "online"/"offline").
    "camera_statuses": {str(cam_id): "online"},
    "cpu_percent": 18.5,
    "memory_percent": 41.0,
    "fps_per_camera": {str(cam_id): 12.0},
}
code, res = req("POST", "/api/edge/heartbeat", api_key=api_key, body=hb)
print("  heartbeat ->", code)
if code != 200:
    print("  body:", res)
    fail.append("heartbeat != 200")

# ---- 4. detection event ---------------------------------------------------
step(4, "POST /api/edge/events (X-API-Key) -> inventory_movement + snapshot")
ev = {
    "camera_id": str(cam_id),
    "event_type": "inventory_movement",
    "severity": "medium",
    "confidence": 0.88,
    "risk_score": 62,
    "snapshot_b64": TINY_JPEG_B64,
    "metadata": {"description": "Smoke test: 2 items removed from shelf", "object_count": 2},
}
code, res = req("POST", "/api/edge/events", api_key=api_key, body=ev)
print("  event ->", code)
snap_url = None
if isinstance(res, dict):
    snap_url = res.get("snapshot_url")
    print("  response:", {k: res.get(k) for k in ("status", "incident_id", "snapshot_url", "store_id")})
if code != 200:
    fail.append("event != 200")

# ---- 5. incidents list ----------------------------------------------------
step(5, "GET tenant stores + incidents -> edge event visible")
code, stores = req("GET", "/api/stores", token=token)
store_ids = []
if isinstance(stores, list):
    store_ids = [s.get("id") or s.get("store_id") for s in stores if isinstance(s, dict)]
elif isinstance(stores, dict) and "stores" in stores:
    store_ids = [s.get("id") or s.get("store_id") for s in stores["stores"]]
print("  stores ->", code, "| store_ids:", store_ids)
found = False
# Cameras without a CameraConfig.location fall into the "auto-detected" store
# bucket, so always probe it in addition to the tenant's registered stores.
probe_ids = list(dict.fromkeys([s for s in (store_ids or []) if s] + ["auto-detected"]))
for sid in probe_ids:
    c, inc = req("GET", "/api/stores/%s/incidents" % sid, token=token)
    items = inc if isinstance(inc, list) else (inc.get("incidents") if isinstance(inc, dict) else [])
    n = len(items) if isinstance(items, list) else 0
    has_inv = any(
        isinstance(i, dict)
        and (i.get("event_type") or i.get("type")) == "inventory_movement"
        for i in (items or [])
    )
    print("  store %s incidents -> %s (count=%s, inventory_movement=%s)" % (sid, c, n, has_inv))
    if has_inv:
        found = True
        if not snap_url:
            for i in items:
                if isinstance(i, dict) and i.get("snapshot_url"):
                    snap_url = i["snapshot_url"]
                    break
        break
if not found:
    fail.append("edge event NOT visible in incidents")

# ---- 6. snapshot served ---------------------------------------------------
step(6, "GET snapshot_url -> JPEG bytes")
if snap_url:
    path = snap_url if snap_url.startswith("/") else "/" + snap_url
    if snap_url.startswith("http"):
        path = snap_url.split("127.0.0.1:8000", 1)[-1]
    code, blob = req("GET", path, token=token, raw=True)
    ok_jpeg = isinstance(blob, (bytes, bytearray)) and len(blob) > 100
    print("  snapshot %s -> %s (%d bytes, jpeg=%s)" % (path, code, len(blob) if isinstance(blob, (bytes, bytearray)) else 0, ok_jpeg))
    if code != 200 or not ok_jpeg:
        fail.append("snapshot not served")
else:
    print("  no snapshot_url captured")
    fail.append("no snapshot_url")

# ---- summary --------------------------------------------------------------
print("\n" + "=" * 60)
if fail:
    print("RESULT: FAIL ->", "; ".join(fail))
    sys.exit(1)
print("RESULT: PASS - full edge agent path works end-to-end")
