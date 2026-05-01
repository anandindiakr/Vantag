"""Build Live Test Results Report from JSON outputs."""
from _common import *
from _common import _set_borders, _shade_cell
import json, os

def load(p):
    with open(p, encoding="utf-8") as f: return json.load(f)

basic = load("live_test_results.json")
deep = load("deep_test_results.json")

d = new_doc("Live Pre-Launch Test Results",
            "Automated Test Run Against All 6 Production Domains",
            "VT-QA-100", "Quality")

toc(d, [
    ("1", "Executive Summary"),
    ("2", "Test Environment"),
    ("3", "Results Per Domain"),
    ("4", "Deep Test Results (retail-vantag.com)"),
    ("5", "Critical Findings & Go/No-Go Verdict"),
    ("6", "Recommended Fixes"),
])

# ── 1. Executive Summary ───────────────────────────────────────────────
h1(d, "1. Executive Summary")
total_basic = sum(sum(v.values()) for v in basic["summary"].values())
pass_basic  = sum(v.get("PASS", 0) for v in basic["summary"].values())
fail_basic  = sum(v.get("FAIL", 0) for v in basic["summary"].values())
deep_summary = deep["summary"]

table_rows(d, ["Metric", "Value"], [
    ["Run timestamp (UTC)", basic["run_at"]],
    ["Domains tested", "6"],
    ["Multi-domain checks run", str(total_basic)],
    ["Multi-domain pass", str(pass_basic)],
    ["Multi-domain fail", str(fail_basic)],
    ["Deep tests (retail-vantag.com)", f"{deep_summary['passed']}/{deep_summary['total']} ({deep_summary['pct']}%)"],
    ["Overall verdict", "CONDITIONAL PASS — fix P0 items before go-live"],
])

# ── 2. Environment ────────────────────────────────────────────────────
h1(d, "2. Test Environment")
para(d, "Tests executed from local Windows workstation against production VPS at 187.127.112.32 "
        "over HTTPS. Pure-Python tests — no external dependencies beyond the standard library.")
bullet(d, "DNS resolution verified for all 6 domains")
bullet(d, "TLS handshake + certificate inspection via ssl module")
bullet(d, "HTTP/HTTPS probes via urllib")
bullet(d, "TCP port probes via socket")

# ── 3. Per-Domain Results ──────────────────────────────────────────────
h1(d, "3. Results Per Domain")

for host, rec in basic["domains"].items():
    h2(d, f"{host}  ({rec['region']})")
    # Summary line
    tls = rec.get("tls", {})
    tls_line = f"TLS: {tls.get('issuer','?')}, {tls.get('days_left','?')} days remaining"
    para(d, f"DNS A: {rec.get('dns_a','?')}  |  {tls_line}  |  /  → {rec.get('root',{}).get('code','?')}",
         italic=True)

    rows = []
    for k, v in rec["checks"].items():
        rows.append([k.replace("_", " "), v])
    t = d.add_table(rows=len(rows), cols=2)
    _set_borders(t)
    for i, (n, v) in enumerate(rows):
        t.rows[i].cells[0].text = n
        t.rows[i].cells[1].text = v
        fill = "10B981" if v == "PASS" else ("F59E0B" if v == "WARN" else "DC2626")
        _shade_cell(t.rows[i].cells[1], fill)
        for p in t.rows[i].cells[1].paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                r.font.bold = True
                r.font.size = Pt(9)
        for p in t.rows[i].cells[0].paragraphs:
            for r in p.runs: r.font.size = Pt(10)

    seo = rec.get("seo", {})
    if seo and "title" in seo:
        para(d, f"Title ({seo.get('title_len','?')} chars): {seo.get('title','')}")
        para(d, f"Description length: {seo.get('desc_len','?')} chars")
        para(d, f"H1 present in raw HTML: {'YES' if seo.get('h1_present') else 'NO'}")

# ── 4. Deep Tests ─────────────────────────────────────────────────────
h1(d, "4. Deep Test Results — retail-vantag.com")
para(d, f"Tests run: {deep_summary['total']}  |  Passed: {deep_summary['passed']}  |  "
        f"Failed: {deep_summary['failed']}  |  Pass rate: {deep_summary['pct']}%", bold=True)

by_group = {}
# naive grouping using prefixes already embedded in names
for t in deep["tests"]:
    name = t["name"]
    grp = "API" if "api/" in name.lower() or "GET /health" in name else \
          "Pages" if name.startswith("GET /") else \
          "Auth" if any(k in name for k in ["Login", "Register"]) else \
          "AuthZ" if "token" in name or "admin" in name.lower() else \
          "Security" if any(k in name for k in ["HSTS","X-","Referrer","Permissions","Server","rate-limit"]) else \
          "Legal" if any(k in name for k in ["/privacy","/terms"]) else \
          "Downloads" if "download" in name.lower() else \
          "Network" if any(k in name for k in ["MQTT","PostgreSQL","Redis","WebSocket","/ws"]) else \
          "Other"
    by_group.setdefault(grp, []).append(t)

for grp in ["Pages", "API", "Auth", "AuthZ", "Security", "Legal", "Downloads", "Network", "Other"]:
    if grp not in by_group: continue
    h2(d, grp)
    tests = by_group[grp]
    t = d.add_table(rows=len(tests), cols=3)
    _set_borders(t)
    for i, row in enumerate(tests):
        t.rows[i].cells[0].text = row["name"]
        t.rows[i].cells[1].text = row["status"]
        t.rows[i].cells[2].text = str(row.get("detail",""))[:100]
        fill = "10B981" if row["status"] == "PASS" else "DC2626"
        _shade_cell(t.rows[i].cells[1], fill)
        for p in t.rows[i].cells[1].paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.color.rgb = RGBColor(0xFF,0xFF,0xFF); r.font.bold = True; r.font.size = Pt(9)
        for p in t.rows[i].cells[0].paragraphs:
            for r in p.runs: r.font.size = Pt(10)
        for p in t.rows[i].cells[2].paragraphs:
            for r in p.runs: r.font.size = Pt(9); r.font.color.rgb = C_MUTED

# ── 5. Critical Findings ──────────────────────────────────────────────
h1(d, "5. Critical Findings & Go/No-Go Verdict")

h2(d, "5.1 What WORKS (ready for launch)")
for item in [
    "All 6 domains resolve to VPS and serve valid HTTPS with ~78 days TLS remaining",
    "HSTS (1 year), X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy all set",
    "sitemap.xml and robots.txt served on all domains, host-aware with correct HTTPS URLs",
    "og-cover.png serves as image/png (not SPA fallback) on all domains",
    "SEO title ≤ 60 chars, meta description 132 chars (within 120-170 band)",
    "H1 present in raw HTML (SEO-critical: Bing/Google can see it pre-JS)",
    "Public pages (/, /pricing, /login, /register, /privacy, /terms, /help, /setup) all return 200",
    "Auth endpoints properly reject invalid payloads with 422 (no stack-trace leaks)",
    "Protected endpoints /api/tenants/me and /api/admin/tenants return 401 without token",
    "PostgreSQL 5432 and Redis 6379 correctly NOT reachable from public internet",
    "MQTT plain 1883 correctly NOT reachable from public internet",
]:
    bullet(d, "[PASS] " + item)

h2(d, "5.2 P0 BLOCKERS — must fix before go-live")
t = d.add_table(rows=4, cols=3)
_set_borders(t)
blockers = [
    ("AUTH bypass: GET /api/cameras returns 200 without token",
     "Serious data-leak risk. Any unauthenticated visitor can potentially list camera records. Multi-tenant isolation breach.",
     "Add router-level dependency on get_current_tenant in backend/api/cameras.py — verify there's no public GET before auth middleware."),
    ("LEGAL: /privacy and /terms are SPA fallback (no real content)",
     "Pages return 200 but body does not contain the words 'privacy' or 'terms' — they are the default React shell. Legally required content is MISSING.",
     "Build PrivacyPolicy.tsx and TermsOfService.tsx components with actual DPDP/PDPA/GDPR-compliant wording. Route them in frontend and server-side pre-render or inline text."),
    ("EDGE AGENT downloads all 404",
     "/downloads/windows, /downloads/android, /downloads/linux all return 404. Core onboarding journey broken — customer cannot activate product.",
     "Host the agent binaries at /downloads/{platform} either as static nginx alias to /var/www/vantag/agents/ or as FastAPI StreamingResponse."),
    ("MQTT TLS port 8883 not reachable",
     "Edge Agents cannot connect to broker. Without MQTT, door-lock control and event push do not work.",
     "Open UFW rule: sudo ufw allow 8883/tcp. Verify mosquitto listener 8883 { cafile, certfile, keyfile } directive in /etc/mosquitto/conf.d/vantag.conf."),
]
for i, (t_title, t_desc, t_fix) in enumerate(blockers):
    t.rows[i].cells[0].text = f"P0-{i+1}"
    t.rows[i].cells[1].text = t_title + "\n\n" + t_desc
    t.rows[i].cells[2].text = t_fix
    _shade_cell(t.rows[i].cells[0], "DC2626")
    for p in t.rows[i].cells[0].paragraphs:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in p.runs:
            r.font.color.rgb = RGBColor(0xFF,0xFF,0xFF); r.font.bold = True; r.font.size = Pt(11)
    for cell in t.rows[i].cells[1:]:
        for p in cell.paragraphs:
            for r in p.runs: r.font.size = Pt(10)

h2(d, "5.3 P1 Items — fix within first sprint after launch")
for item in [
    "Login rate-limit NOT triggering 429 after 6 bad attempts — implement in nginx or SlowAPI",
    "Server header leaks 'nginx/1.24.0 (Ubuntu)' — add `server_tokens off;` to nginx.conf",
    "/api/health and /api/version return 404 — add uniform API-prefixed health endpoints (only /health works)",
    "/ws WebSocket endpoint returns 404 on plain HTTP — verify actual WebSocket path; may be /socket.io or /api/ws",
]:
    bullet(d, item)

h2(d, "5.4 Go/No-Go Verdict")
rect_text = ("VERDICT: CONDITIONAL NO-GO.\n\n"
             "The platform is 67% production-ready (24/36 deep tests pass). "
             "However 4 P0 blockers exist that MUST be fixed before accepting paying customers:\n"
             "  • API auth bypass (data leak)\n"
             "  • Missing legal pages (regulatory non-compliance)\n"
             "  • Edge Agent downloads broken (customer journey broken)\n"
             "  • MQTT broker not reachable (core feature broken)\n\n"
             "Estimated fix time: 4–6 hours of focused engineering.\n"
             "Re-run this test suite after fixes and confirm 100% pass before flipping go-live.")
para(d, rect_text, bold=True)

# ── 6. Fixes ─────────────────────────────────────────────────────────
h1(d, "6. Recommended Fixes (in priority order)")

h2(d, "Fix 1 — Close /api/cameras auth leak")
code_block(d, """
# backend/api/cameras.py
from fastapi import APIRouter, Depends
from backend.api.deps import get_current_tenant

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

@router.get("")
async def list_cameras(tenant=Depends(get_current_tenant)):   # <-- add auth dep
    ...
""", "python")

h2(d, "Fix 2 — Real /privacy and /terms pages")
code_block(d, """
# frontend/web/src/pages/PrivacyPolicy.tsx
// Use copy from docs/06_Compliance/16_Compliance_and_Privacy_Policy.docx
// Add meta description + h1 + full text.
// Route in App.tsx: <Route path="/privacy" element={<PrivacyPolicy/>}/>
""", "tsx")

h2(d, "Fix 3 — Edge Agent download endpoints")
code_block(d, """
# /etc/nginx/sites-enabled/vantag
location /downloads/ {
  alias /var/www/vantag/agents/;
  autoindex off;
  add_header Content-Disposition "attachment";
}
""", "nginx")

h2(d, "Fix 4 — Open MQTT 8883 firewall + verify TLS listener")
code_block(d, """
sudo ufw allow 8883/tcp
sudo cat > /etc/mosquitto/conf.d/vantag.conf <<EOF
listener 8883
cafile   /etc/letsencrypt/live/retail-vantag.com/chain.pem
certfile /etc/letsencrypt/live/retail-vantag.com/cert.pem
keyfile  /etc/letsencrypt/live/retail-vantag.com/privkey.pem
allow_anonymous false
password_file /etc/mosquitto/passwd
EOF
sudo systemctl restart mosquitto
""", "bash")

h2(d, "Fix 5 — nginx server-tokens off + login rate-limit")
code_block(d, """
# /etc/nginx/nginx.conf (http block)
server_tokens off;

# Per-location limit:
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
location = /api/auth/login { limit_req zone=login burst=3 nodelay; }
""", "nginx")

h1(d, "7. Re-test Command")
para(d, "After fixes, re-run the automated suite:")
code_block(d, """
cd docs_package
python live_test.py && python deep_test.py
# Expect: multi-domain 17/17 pass, deep tests ≥ 34/36 pass
""", "bash")

save(d, "05_Quality", "24_Live_Test_Results_Report.docx")
print("Saved test report.")
