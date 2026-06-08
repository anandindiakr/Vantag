#!/usr/bin/env bash
# Verify the backend is up and the new edge/agent routes are registered.
set -e
BASE="http://127.0.0.1:8000"

echo "== service =="
systemctl is-active vantag.service || true

echo "== openapi routes (edge/agent/health) =="
curl -s "$BASE/openapi.json" -o /tmp/vantag_api.json
python3 - <<'PY'
import json
d = json.load(open('/tmp/vantag_api.json'))
paths = sorted(d.get('paths', {}))
for p in paths:
    if any(k in p for k in ('agent', 'edge', 'health')):
        print(p)
PY

echo "== download route (expect 401/403 without JWT, NOT 404) =="
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/agent/download?platform=windows")
echo "GET /api/agent/download -> $code"
