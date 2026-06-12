import urllib.request, json

login_data = json.dumps({
    'email': 'sales-demo@retail-vantag.com',
    'password': 'VantagSales@2026'
}).encode()

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/auth/login',
    data=login_data,
    headers={'Content-Type': 'application/json'}
)
resp = urllib.request.urlopen(req)
d = json.load(resp)
token = d.get('access_token', 'NO_TOKEN')
print('TOKEN:', token[:40] + '...' if len(token) > 40 else token)

# Test /api/edge/agents (original requested endpoint)
req2 = urllib.request.Request(
    'http://127.0.0.1:8000/api/edge/agents',
    headers={'Authorization': 'Bearer ' + token}
)
try:
    resp2 = urllib.request.urlopen(req2)
    print('GET /api/edge/agents HTTP_STATUS:', resp2.status)
except urllib.error.HTTPError as e:
    print('GET /api/edge/agents HTTP_STATUS:', e.code)

# Test correct endpoint /api/tenants/me/edge-agents
req3 = urllib.request.Request(
    'http://127.0.0.1:8000/api/tenants/me/edge-agents',
    headers={'Authorization': 'Bearer ' + token}
)
try:
    resp3 = urllib.request.urlopen(req3)
    print('GET /api/tenants/me/edge-agents HTTP_STATUS:', resp3.status)
    body = json.load(resp3)
    print('RESPONSE:', json.dumps(body)[:200])
except urllib.error.HTTPError as e:
    print('GET /api/tenants/me/edge-agents HTTP_STATUS:', e.code)
