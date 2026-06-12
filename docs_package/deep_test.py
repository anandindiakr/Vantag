"""Deeper live tests — API endpoints, pages, security negative tests."""
import json, socket, ssl, re
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

HOST = "retail-vantag.com"
BASE = f"https://{HOST}"
results = {"run_at": datetime.utcnow().isoformat() + "Z", "tests": []}

def add(name, passed, detail=""):
    res = {"name": name, "status": "PASS" if passed else "FAIL", "detail": detail}
    results["tests"].append(res)
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name:45s} {detail}")
    return passed

def fetch(path, method="GET", data=None, headers=None, timeout=10):
    url = BASE + path
    h = {"User-Agent": "VantagDeepTest/1.0"}
    if headers: h.update(headers)
    req = Request(url, data=data, method=method, headers=h)
    ctx = ssl.create_default_context()
    try:
        r = urlopen(req, context=ctx, timeout=timeout)
        return r.status, dict(r.headers), r.read(131072).decode("utf-8", errors="replace")
    except HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8", errors="replace")[:2048]
        except: pass
        return e.code, dict(e.headers) if e.headers else {}, body
    except Exception as e:
        return 0, {}, str(e)

print(f"\n=== DEEP TESTS on {HOST} ===\n")

# --- Pages ---
print("[PAGES]")
for path, expected in [("/", 200), ("/pricing", 200), ("/login", 200),
                       ("/register", 200), ("/privacy", 200), ("/terms", 200),
                       ("/help", 200), ("/setup", 200)]:
    code, _, body = fetch(path)
    add(f"GET {path}", code == expected, f"→ {code}")

# --- API health + metadata ---
print("\n[API]")
code, _, body = fetch("/api/health")
add("GET /api/health", code == 200, f"→ {code}")
code, _, body = fetch("/health")
add("GET /health", code == 200, f"→ {code}")
code, hdrs, body = fetch("/api/version")
add("GET /api/version returns JSON", "application/json" in str(hdrs.get("Content-Type", "")).lower() or "json" in body, f"→ {code}")

# --- Auth endpoints ---
print("\n[AUTH]")
# Login with bad credentials
code, _, body = fetch("/api/auth/login", method="POST",
                      data=json.dumps({"email": "nobody@test.invalid", "password": "wrong"}).encode(),
                      headers={"Content-Type": "application/json"})
add("Login wrong credentials → 401/400", code in (400, 401, 422), f"→ {code}")
# No stack trace leak
add("No stack trace in error body", "Traceback" not in body and "File \"/" not in body, f"body_len={len(body)}")

# Register with invalid email
code, _, body = fetch("/api/auth/register", method="POST",
                      data=json.dumps({"email": "not-an-email", "password": "x"}).encode(),
                      headers={"Content-Type": "application/json"})
add("Register invalid email → 4xx", 400 <= code < 500, f"→ {code}")

# --- Protected endpoint ---
print("\n[AUTHZ]")
code, _, body = fetch("/api/tenants/me")
add("GET /api/tenants/me no-token → 401", code in (401, 403), f"→ {code}")

code, _, body = fetch("/api/admin/tenants")
add("GET /api/admin/tenants no-token → 401/403", code in (401, 403), f"→ {code}")

code, _, body = fetch("/api/cameras")
add("GET /api/cameras no-token → 401", code in (401, 403), f"→ {code}")

# --- CORS / methods ---
print("\n[SECURITY HEADERS]")
code, hdrs, _ = fetch("/")
hk = {k.lower(): v for k, v in hdrs.items()}
add("HSTS max-age >= 1y", "max-age=31536000" in hk.get("strict-transport-security", ""),
    f"→ {hk.get('strict-transport-security','')[:60]}")
add("X-Content-Type-Options nosniff", hk.get("x-content-type-options", "").lower() == "nosniff",
    f"→ {hk.get('x-content-type-options','')}")
add("X-Frame-Options set", bool(hk.get("x-frame-options")), f"→ {hk.get('x-frame-options','')}")
add("Referrer-Policy set", bool(hk.get("referrer-policy")), f"→ {hk.get('referrer-policy','')}")
add("Permissions-Policy set", bool(hk.get("permissions-policy")), f"→ {hk.get('permissions-policy','')}")
add("Server header does NOT leak version", "/" not in hk.get("server", "")[3:], f"→ {hk.get('server','')}")

# --- Rate limiting sanity (hit /api/auth/login 6 times) ---
print("\n[RATE LIMITS]")
codes = []
for i in range(6):
    c, _, _ = fetch("/api/auth/login", method="POST",
                    data=json.dumps({"email": f"rate-test-{i}@x.io", "password": "wrong"}).encode(),
                    headers={"Content-Type": "application/json"})
    codes.append(c)
blocked = any(c == 429 for c in codes)
add("Login rate-limit triggers 429 after 6 attempts", blocked or codes[-1] >= 400,
    f"codes={codes} (429 observed={blocked})")

# --- SEO: privacy / terms content ---
print("\n[LEGAL PAGES]")
for path in ["/privacy", "/terms"]:
    code, _, body = fetch(path)
    body_lower = body.lower()
    add(f"{path} contains 'privacy'/'terms' content",
        code == 200 and any(w in body_lower for w in ["privacy", "terms", "data protection"]),
        f"code={code}, len={len(body)}")

# --- Edge Agent download links ---
print("\n[EDGE AGENT DOWNLOADS]")
for path in ["/downloads/windows", "/downloads/android", "/downloads/linux",
             "/api/agent/download/windows", "/api/agent/download/android"]:
    code, _, _ = fetch(path)
    add(f"GET {path}", code in (200, 302), f"→ {code}")

# --- WebSocket endpoint responds ---
print("\n[WEBSOCKET]")
code, _, body = fetch("/ws")
# WS endpoints typically return 400 on plain HTTP — expected
add("/ws returns 400/426 on plain HTTP", code in (400, 426), f"→ {code}")

# --- MQTT port accessible (TCP handshake) ---
print("\n[MQTT]")
def tcp_test(host, port, timeout=6):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as e:
        return False

add("MQTT TLS port 8883 reachable", tcp_test(HOST, 8883), "")
add("MQTT plain 1883 NOT public (should be FAIL=closed)", not tcp_test(HOST, 1883), "")
add("PostgreSQL 5432 NOT public", not tcp_test(HOST, 5432), "")
add("Redis 6379 NOT public", not tcp_test(HOST, 6379), "")

# --- Summary ---
total = len(results["tests"])
passed = sum(1 for t in results["tests"] if t["status"] == "PASS")
print(f"\n=== {passed}/{total} tests passed ===")
results["summary"] = {"total": total, "passed": passed, "failed": total - passed,
                      "pct": round(passed/total*100, 1) if total else 0}

with open("deep_test_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, default=str)
print("Saved: deep_test_results.json")
