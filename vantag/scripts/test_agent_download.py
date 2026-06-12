"""
Test the /api/agent/download endpoint.
- Logs in with sales-demo account
- Downloads the agent zip
- Opens the zip in memory and reads config.json
- Asserts backend_url and mqtt_host are correct (not internal 127.0.0.1)
"""
import io
import json
import sys
import urllib.request
import urllib.error
import zipfile

BASE = "http://127.0.0.1:8000"
EMAIL = "sales-demo@retail-vantag.com"
PASSWORD = "VantagSales@2026"
EXPECTED_PROTO = "https"
EXPECTED_HOST_FRAGMENT = "retail-vantag.com"  # must NOT be 127.0.0.1 or localhost


def _post_json(path, payload, token=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _get(path, token=None, accept=None):
    req = urllib.request.Request(BASE + path, method="GET")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if accept:
        req.add_header("Accept", accept)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    failures = []

    # ── 1. Login ──────────────────────────────────────────────────────────────
    status, body = _post_json("/api/auth/login", {"email": EMAIL, "password": PASSWORD})
    print(f"[1] LOGIN  -> HTTP {status}")
    if status != 200:
        print("    FAIL: login returned", status, body[:200])
        sys.exit(1)
    tok = json.loads(body).get("access_token") or json.loads(body).get("token")
    if not tok:
        print("    FAIL: no token in response")
        sys.exit(1)
    print("    token obtained")

    # ── 2. Download agent zip ─────────────────────────────────────────────────
    # The nginx proxy sets X-Forwarded-Proto + Host. When calling via 127.0.0.1
    # directly those headers are absent, so we simulate them to reproduce the
    # production code path.
    req = urllib.request.Request(BASE + "/api/agent/download?platform=windows", method="GET")
    req.add_header("Authorization", "Bearer " + tok)
    req.add_header("X-Forwarded-Proto", "https")
    req.add_header("Host", "retail-vantag.com")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            dl_status = r.status
            dl_body = r.read()
    except urllib.error.HTTPError as e:
        dl_status = e.code
        dl_body = e.read()

    print(f"[2] DOWNLOAD -> HTTP {dl_status}  ({len(dl_body)} bytes)")
    if dl_status != 200:
        print("    FAIL body:", dl_body[:400].decode(errors="replace"))
        sys.exit(1)

    # ── 3. Parse zip + read config.json ───────────────────────────────────────
    try:
        zf = zipfile.ZipFile(io.BytesIO(dl_body))
        names = zf.namelist()
    except zipfile.BadZipFile:
        print("[3] FAIL: response is not a valid zip file")
        print("    first 200 bytes:", dl_body[:200])
        sys.exit(1)

    print(f"[3] ZIP contents ({len(names)} files):")
    for n in names:
        print("   ", n)

    cfg_path = next((n for n in names if n.endswith("config.json")), None)
    if not cfg_path:
        print("[4] FAIL: config.json not found in zip")
        sys.exit(1)

    cfg = json.loads(zf.read(cfg_path).decode())
    print(f"\n[4] config.json:\n{json.dumps(cfg, indent=2)}\n")

    # ── 4. Assertions ─────────────────────────────────────────────────────────
    backend_url = cfg.get("backend_url", "")
    mqtt_host = cfg.get("mqtt_host", "")
    mqtt_port = cfg.get("mqtt_port")
    api_key = cfg.get("api_key", "")
    agent_id = cfg.get("agent_id", "")

    checks = [
        ("backend_url starts with https://",
         backend_url.startswith("https://"),
         f"got: {backend_url!r}"),
        ("backend_url does NOT contain 127.0.0.1",
         "127.0.0.1" not in backend_url,
         f"got: {backend_url!r}"),
        ("backend_url does NOT contain localhost",
         "localhost" not in backend_url,
         f"got: {backend_url!r}"),
        (f"backend_url contains {EXPECTED_HOST_FRAGMENT!r}",
         EXPECTED_HOST_FRAGMENT in backend_url,
         f"got: {backend_url!r}"),
        ("mqtt_host is set (not empty)",
         bool(mqtt_host),
         "mqtt_host is empty"),
        ("mqtt_host does NOT contain 127.0.0.1",
         "127.0.0.1" not in mqtt_host,
         f"got: {mqtt_host!r}"),
        ("mqtt_host does NOT contain localhost",
         "localhost" not in mqtt_host,
         f"got: {mqtt_host!r}"),
        ("mqtt_port is 1883",
         mqtt_port == 1883,
         f"got: {mqtt_port!r}"),
        ("api_key is present",
         bool(api_key),
         "api_key is empty"),
        ("agent_id is present",
         bool(agent_id),
         "agent_id is empty"),
    ]

    print("[5] Assertions:")
    for desc, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"   [{mark}] {desc}" + (f"  ({detail})" if not ok else ""))
        if not ok:
            failures.append(desc)

    print()
    if failures:
        print(f"RESULT: FAIL — {len(failures)} assertion(s) failed")
        sys.exit(1)
    else:
        print("RESULT: PASS — downloaded config.json is production-ready")


if __name__ == "__main__":
    main()
