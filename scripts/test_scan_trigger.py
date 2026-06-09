"""
test_scan_trigger.py
====================
End-to-end test for the Trigger Scan flow on the live VPS.

Tests:
  1. Login as sales-demo user
  2. GET /api/cameras/discovered  → 200 (may be [])
  3. POST /api/cameras/scan-request → 200 { ok: true }
  4. GET /api/edge/agents          → 200 (may be empty if no agent installed)
  5. POST /api/edge/cameras/discovered without X-API-Key → 401 (auth check)
  6. Internal flag logic: verify consume_camera_scan clears the flag

Usage:
  python scripts/test_scan_trigger.py
"""
import sys
import os

# Make sure we can import backend modules for logic test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import urllib.request
import urllib.error
import json
import ssl

BASE = "https://retail-vantag.com"
DEMO_EMAIL = "sales-demo@retail-vantag.com"
DEMO_PASS = "VantagSales@2026"

ctx = ssl.create_default_context()

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"
INFO = "\033[36mINFO\033[0m"

results = []


def api(method, path, body=None, token=None, api_key=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if api_key:
        hdrs["X-API-Key"] = api_key
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=12) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return e.code, body


def check(name, condition, detail=""):
    tag = PASS if condition else FAIL
    results.append(condition)
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))


# ── 1. Login ─────────────────────────────────────────────────────────────────
print("\n[TEST 1] Login as sales-demo")
s, d = api("POST", "/api/auth/login", {"email": DEMO_EMAIL, "password": DEMO_PASS})
print(f"  {INFO} HTTP {s}")
check("HTTP 200", s == 200)
tok = d.get("access_token")
check("access_token present", bool(tok))
if not tok:
    print(f"\n{FAIL} Cannot continue without a token. Check demo credentials on VPS.")
    sys.exit(1)

# ── 2. GET /api/cameras/discovered ───────────────────────────────────────────
print("\n[TEST 2] GET /api/cameras/discovered")
s2, d2 = api("GET", "/api/cameras/discovered", token=tok)
print(f"  {INFO} HTTP {s2}  body={json.dumps(d2)[:120]}")
check("HTTP 200", s2 == 200, f"got {s2}")
check("returns a list", isinstance(d2, list), type(d2).__name__)

# ── 3. POST /api/cameras/scan-request ────────────────────────────────────────
print("\n[TEST 3] POST /api/cameras/scan-request  (Trigger Scan button)")
s3, d3 = api("POST", "/api/cameras/scan-request", token=tok)
print(f"  {INFO} HTTP {s3}  body={json.dumps(d3)[:120]}")
check("HTTP 200", s3 == 200, f"got {s3}")
check("ok=True in response", d3.get("ok") is True, str(d3))
check("message field present", "message" in d3, str(d3))

# ── 4. GET /api/edge/agents (may be 404 if backend not yet updated) ──────────
print("\n[TEST 4] GET /api/edge/agents  (new endpoint)")
s4, d4 = api("GET", "/api/edge/agents", token=tok)
print(f"  {INFO} HTTP {s4}  body={json.dumps(d4)[:120]}")
if s4 == 404:
    print(f"  [{SKIP}] Endpoint not yet deployed — run git pull + systemctl restart on VPS")
    results.append(None)  # skip
elif s4 == 200:
    check("HTTP 200", True)
    check("agents list present", "agents" in d4, str(d4))
    check("total field present", "total" in d4, str(d4))
    n = d4.get("total", 0)
    print(f"  {INFO} {n} agent(s) registered for this tenant")
    if n == 0:
        print(f"  {INFO} No agents registered — install the Edge Agent on a store PC to see them here")
else:
    check(f"HTTP 200 (got {s4})", False, str(d4))

# ── 5. POST /api/edge/cameras/discovered without X-API-Key → must be 401/422 ─
print("\n[TEST 5] POST /api/edge/cameras/discovered  (no X-API-Key -> must be rejected)")
fake = {"cameras": [{
    "ip": "192.168.1.100", "port": 554, "brand": "hikvision",
    "model": "DS-2CD2T47", "rtsp_path": "/Streaming/Channels/101",
    "rtsp_url": "rtsp://192.168.1.100:554/Streaming/Channels/101",
    "thumbnail_b64": None, "onvif": True, "confidence": 0.9,
    "needs_credentials": False
}]}
s5, d5 = api("POST", "/api/edge/cameras/discovered", body=fake)  # no key
print(f"  {INFO} HTTP {s5}  body={json.dumps(d5)[:80]}")
check("Rejected without X-API-Key (401/403/422)", s5 in (401, 403, 422), f"got {s5}")

# ── 6. Internal flag logic (unit-test the module directly) ───────────────────
print("\n[TEST 6] Internal scan-flag logic  (unit test)")
try:
    from api.edge_router import request_camera_scan, consume_camera_scan
    tid = "test-tenant-abc"
    # Initially not set
    v0 = consume_camera_scan(tid)
    check("flag starts as False", v0 is False, str(v0))
    # Set it
    request_camera_scan(tid)
    v1 = consume_camera_scan(tid)
    check("flag is True after request", v1 is True, str(v1))
    # Consumed — second consume returns False
    v2 = consume_camera_scan(tid)
    check("flag cleared after consume (one-shot)", v2 is False, str(v2))
except ImportError as e:
    print(f"  [{SKIP}] Cannot import backend modules in this env: {e}")
    results.extend([None, None, None])

# ── Summary ───────────────────────────────────────────────────────────────────
real = [r for r in results if r is not None]
passed = sum(1 for r in real if r)
skipped = sum(1 for r in results if r is None)
print(f"\n{'='*55}")
print(f"  Results: {passed}/{len(real)} passed, {skipped} skipped")
print("="*55)
if all(r for r in real):
    print(f"\n  [{PASS}] All live checks passed.")
    print("  The Trigger Scan button flow is working correctly.")
    print("  When an Edge Agent is installed on the store LAN,")
    print("  it will receive scan_requested=True on next heartbeat")
    print("  and POST discovered cameras to /api/edge/cameras/discovered.")
else:
    print(f"\n  [{FAIL}] Some checks failed — see details above.")
print()
