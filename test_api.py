import urllib.request, urllib.error, json, sys

# Step 1: Login
login_data = json.dumps({"email": "sales-demo@retail-vantag.com", "password": "VantagSales@2026"}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/auth/login",
    data=login_data,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())
        token = body.get("access_token", "NO_TOKEN")
        print(f"LOGIN_STATUS:{resp.status}")
        print(f"TOKEN_PREFIX:{token[:30]}...")
except urllib.error.HTTPError as e:
    print(f"LOGIN_ERROR:{e.code} {e.read()}")
    sys.exit(1)

# Step 2: Call /api/edge/agents
req2 = urllib.request.Request(
    "http://127.0.0.1:8000/api/edge/agents",
    headers={"Authorization": f"Bearer {token}"},
    method="GET"
)
try:
    with urllib.request.urlopen(req2, timeout=10) as resp2:
        body2 = resp2.read().decode()
        print(f"HTTP_STATUS:{resp2.status}")
        print(f"RESPONSE:{body2[:300]}")
except urllib.error.HTTPError as e:
    print(f"AGENTS_ERROR:{e.code}")
    body_err = e.read().decode()
    print(f"AGENTS_BODY:{body_err[:300]}")
    print(f"HTTP_STATUS:{e.code}")
