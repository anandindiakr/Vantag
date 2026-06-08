"""One-shot VPS test: log in with sales-demo, then GET /api/cameras/discovered.

Proves the route resolves to list_discovered_cameras (HTTP 200 + list)
rather than being shadowed by /{camera_id} (which returned 404).
"""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"
EMAIL = "sales-demo@retail-vantag.com"
PASSWORD = "VantagSales@2026"


def _post(path, payload, token=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _get(path, token=None):
    req = urllib.request.Request(BASE + path, method="GET")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main():
    status, body = _post("/api/auth/login", {"email": EMAIL, "password": PASSWORD})
    print("LOGIN ->", status)
    if status != 200:
        print("  body:", body[:300])
        print("RESULT: cannot test (login failed)")
        return
    tok = json.loads(body).get("access_token") or json.loads(body).get("token")
    if not tok:
        print("  no token in:", body[:300])
        return

    status, body = _get("/api/cameras/discovered", tok)
    print("GET /api/cameras/discovered ->", status)
    print("  body:", body[:400])
    if status == 200:
        print("RESULT: PASS - /discovered resolves to list_discovered_cameras (no shadowing)")
    elif status == 404:
        print("RESULT: FAIL - still shadowed by /{camera_id} (404)")
    else:
        print("RESULT: UNEXPECTED status", status)


if __name__ == "__main__":
    main()
