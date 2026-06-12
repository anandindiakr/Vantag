"""Build 3 go-live documents:
 1. Pre-Launch Critical Checks (the big checklist)
 2. Live Test Results Report
 3. Team Deployment Checklist (condensed ops card)
"""
from _common import *
from _common import _set_borders, _shade_cell


def _checkbox_row(table_cells, label, severity):
    """Add a row with [ ] checkbox, label, severity pill."""
    table_cells[0].text = "☐"
    for p in table_cells[0].paragraphs:
        for r in p.runs:
            r.font.size = Pt(14)
            r.font.bold = True
    table_cells[1].text = label
    for p in table_cells[1].paragraphs:
        for r in p.runs:
            r.font.size = Pt(10)
    table_cells[2].text = severity
    sev_color = {"P0": "DC2626", "P1": "F59E0B", "P2": "10B981"}[severity]
    _shade_cell(table_cells[2], sev_color)
    for p in table_cells[2].paragraphs:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in p.runs:
            r.font.bold = True
            r.font.size = Pt(9)
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)


def checklist_section(doc, title, color, items):
    """items = [(label, 'P0'|'P1'|'P2'), ...]"""
    h2(doc, title)
    t = doc.add_table(rows=len(items), cols=3)
    _set_borders(t)
    for i, (lbl, sev) in enumerate(items):
        _checkbox_row(t.rows[i].cells, lbl, sev)
        t.rows[i].cells[0].width = Inches(0.35)
        t.rows[i].cells[1].width = Inches(5.8)
        t.rows[i].cells[2].width = Inches(0.55)


# ═══════════════════════════════════════════════════════════════════════
# DOC 1 — PRE-LAUNCH CRITICAL CHECKS
# ═══════════════════════════════════════════════════════════════════════
def build_prelaunch():
    d = new_doc("Pre-Launch Critical Checks",
                "Go/No-Go Gates for Production Release",
                "VT-OPS-101", "Operations")
    toc(d, [
        ("1", "Go/No-Go Rule"),
        ("2", "Severity Legend"),
        ("3", "P0 — Must Pass (Blockers)"),
        ("4", "P1 — Should Pass (Reputation)"),
        ("5", "P2 — Good to Have (Polish)"),
        ("6", "15-Minute Smoke Test"),
        ("7", "Sign-off"),
    ])

    h1(d, "1. Go / No-Go Rule")
    para(d, "Do not flip production DNS unless every one of these is true:", bold=True)
    bullet(d, "Every P0 box is ticked — no exceptions")
    bullet(d, "At least 80% of P1 boxes are ticked")
    bullet(d, "Smoke test ran once with zero failures")
    bullet(d, "A human other than the deployer has paid a real ₹1 subscription successfully")
    bullet(d, "Real camera → real incident alert arrived on a phone in < 5 seconds")

    h1(d, "2. Severity Legend")
    table_rows(d, ["Severity", "Meaning"], [
        ["P0", "Hard blocker. Security, legal, or financial risk. Skip = do not launch."],
        ["P1", "Reputation risk. Skip = launch but expect churn or escalations."],
        ["P2", "Polish. Skip = functional but rougher-feeling product."],
    ])

    h1(d, "3. P0 — Must Pass (Hard Blockers)")

    checklist_section(d, "3.1 Security & Data Protection", C_PRIMARY, [
        ("TLS valid on all 6 domains (certbot renew --dry-run passes)", "P0"),
        ("HSTS header with max-age=31536000; includeSubDomains active", "P0"),
        ("No secrets in git history (grep full history for password/secret/key/token)", "P0"),
        ("/var/www/vantag/.env has 600 permissions and is www-data-owned", "P0"),
        ("JWT secret rotated from dev default; min 64 random bytes", "P0"),
        ("bcrypt cost ≥ 12 verified in code", "P0"),
        ("PostgreSQL binds only to 127.0.0.1 (ss -tlnp | grep 5432)", "P0"),
        ("Redis has requirepass set and binds to localhost", "P0"),
        ("SSH root login disabled, key-based only, fail2ban running", "P0"),
        ("UFW firewall allows only 22/80/443/8883 externally", "P0"),
    ])

    checklist_section(d, "3.2 Payments (Razorpay)", C_PRIMARY, [
        ("Webhook HMAC signature verification tested end-to-end (live mode)", "P0"),
        ("Webhook idempotency — same event.id replayed does not double-process", "P0"),
        ("Razorpay live keys (rzp_live_*) in .env, not test keys", "P0"),
        ("Refund flow tested: ₹1 refund issued and processed successfully", "P0"),
        ("Invoice numbering sequential and compliant per region (GST/SST)", "P0"),
        ("Failed-payment retry schedule active (4 attempts over 15 days)", "P0"),
        ("Subscription cancellation actually stops billing on next cycle", "P0"),
    ])

    checklist_section(d, "3.3 Multi-Tenant Isolation", C_PRIMARY, [
        ("Tenant A cannot GET/PATCH/DELETE Tenant B resources (returns 404)", "P0"),
        ("Automated cross-tenant access test in CI", "P0"),
        ("Super-admin audit log records every cross-tenant action with IP", "P0"),
        ("Evidence files segregated by tenant_id in storage paths", "P0"),
    ])

    checklist_section(d, "3.4 Legal & Compliance", C_PRIMARY, [
        ("Privacy Policy live at /privacy for all 3 regions", "P0"),
        ("Terms of Service live at /terms, accepted at registration", "P0"),
        ("DPDP (IN) / PDPA-SG / PDPA-MY wording in regional privacy pages", "P0"),
        ("DPO contact (dpo@retail-vantag.com) live and monitored", "P0"),
        ("Razorpay merchant entity matches invoice legal name / GSTIN / UEN", "P0"),
        ("Data-breach 72-hour notification procedure documented", "P0"),
    ])

    checklist_section(d, "3.5 Disaster Recovery", C_PRIMARY, [
        ("Daily pg_dump + WAL backup running and tested via staging restore", "P0"),
        ("Backups stored off-VPS (S3/B2/second region), 30-day retention", "P0"),
        ("One-command rollback script reverts last deploy in < 5 min", "P0"),
        ("Incident runbook (VT-OPS-013) accessible to on-call", "P0"),
    ])

    h1(d, "4. P1 — Should Pass")

    checklist_section(d, "4.1 Reliability", C_ACCENT, [
        ("Uptime monitor pings /health every 60s on every domain", "P1"),
        ("Alerts fire when API down > 2min or error rate > 1%", "P1"),
        ("Load test: 500 concurrent users, p95 < 400 ms", "P1"),
        ("Login endpoint rate-limited to 5/min/IP in nginx", "P1"),
        ("Graceful systemctl restart does not drop WebSocket clients", "P1"),
        ("logrotate configured — disk fill protected", "P1"),
    ])

    checklist_section(d, "4.2 AI Accuracy", C_ACCENT, [
        ("Detection precision ≥ 92% on fixture test set (12 detectors × 5 clips)", "P1"),
        ("False-positive rate ≤ 8% on empty-scene baselines", "P1"),
        ("Cold-start time < 3s on Android / Pi / Jetson", "P1"),
        ("Fall detector tested against pets, children, sitting-on-floor", "P1"),
        ("Zone editor polygons persist across browser refresh", "P1"),
    ])

    checklist_section(d, "4.3 User Experience", C_ACCENT, [
        ("End-to-end signup on throwaway phone + email in each region", "P1"),
        ("OTP email arrives < 30s, not in spam (SPF/DKIM/DMARC pass)", "P1"),
        ("All 11 Indian languages render without missing glyphs", "P1"),
        ("Mobile PWA installs on Android (Chrome) and iOS (Safari 14+)", "P1"),
        ("Dashboard shows reconnect banner when WebSocket drops", "P1"),
        ("No blank empty states — onboarding prompts shown instead", "P1"),
        ("Error messages never expose stack traces", "P1"),
    ])

    checklist_section(d, "4.4 SEO & Discoverability", C_ACCENT, [
        ("sitemap.xml returns 200 on all 6 domains", "P1"),
        ("robots.txt allows crawling, disallows /admin + /api", "P1"),
        ("Google Search Console verified for all 6 domains, sitemaps submitted", "P1"),
        ("Bing Webmaster Tools verified, sitemaps submitted", "P1"),
        ("H1 present in raw HTML (before JS hydration)", "P1"),
        ("Title ≤ 60 chars, description 120-160 chars on every page", "P1"),
        ("og-cover.png returns 200 with content-type image/png", "P1"),
        ("Structured data validates on search.google.com/test/rich-results", "P1"),
    ])

    h1(d, "5. P2 — Good to Have (Polish)")

    checklist_section(d, "5.1 Support", C_MUTED, [
        ("Help Center populated with 20+ articles per region", "P2"),
        ("AI Support Chat (GPT-4o) grounded on Help Center, tested on 10 tickets", "P2"),
        ("support@retail-vantag.com inbox monitored with auto-reply", "P2"),
        ("WhatsApp Business number set up for India tier", "P2"),
    ])

    checklist_section(d, "5.2 Analytics & Instrumentation", C_MUTED, [
        ("Sentry capturing frontend + backend errors; dev errors filtered", "P2"),
        ("Prometheus metrics exposed on /metrics (internal only)", "P2"),
        ("PostHog / Plausible page-view analytics (privacy-safe)", "P2"),
        ("Conversion funnel dashboards: landing → register → plan → pay", "P2"),
    ])

    checklist_section(d, "5.3 Commercial Readiness", C_MUTED, [
        ("Brochures (IN/SG/MY) downloadable from every landing page", "P2"),
        ("Demo video (60-90s) embedded on landing, auto-plays muted", "P2"),
        ("At least 1 customer testimonial or pilot logo on landing", "P2"),
        ("Live chat widget on pricing page", "P2"),
        ("Affiliate / installer onboarding page live (if that channel)", "P2"),
    ])

    h1(d, "6. 15-Minute Smoke Test")
    para(d, "Run before every production deploy. Any red = do not flip the switch.", bold=True)

    h2(d, "6.1 Health on all 6 domains")
    code_block(d, """
for d in retail-vantag.com retailnazar.com retailnazar.in \\
         retailnazar.info jagajaga.my retailjagajaga.com; do
  echo -n "$d -> "
  curl -sk -o /dev/null -w "%{http_code}\\n" "https://$d/health"
done
""", "bash")

    h2(d, "6.2 TLS expiry")
    code_block(d, """
for d in retail-vantag.com retailnazar.com jagajaga.my; do
  echo -n "$d -> "
  echo | openssl s_client -servername $d -connect $d:443 2>/dev/null \\
    | openssl x509 -noout -enddate
done
""", "bash")

    h2(d, "6.3 End-to-end flow")
    numbered(d, "Register a fresh tenant with throwaway email")
    numbered(d, "Verify OTP arrives in inbox within 30s")
    numbered(d, "Login, pick Starter plan, complete Razorpay test payment")
    numbered(d, "Download Edge Agent, scan QR, verify pairing")
    numbered(d, "Run camera auto-discovery")
    numbered(d, "Draw one zone, fire a test event from Demo Center")
    numbered(d, "Confirm incident appears in dashboard within 2s")
    numbered(d, "Confirm push notification reaches phone within 5s")

    h2(d, "6.4 Service health on VPS")
    code_block(d, """
ssh root@187.127.112.32 "systemctl status vantag mosquitto postgresql \\
  redis nginx | grep -E '(Active|Main PID)'"
""", "bash")

    h1(d, "7. Sign-off")
    table_rows(d, ["Role", "Name", "Date", "Signature"], [
        ["Tech Lead", "", "", ""],
        ["QA Lead", "", "", ""],
        ["Security Officer", "", "", ""],
        ["DPO", "", "", ""],
        ["Founder / CEO", "", "", ""],
    ])
    save(d, "04_Operations", "22_Pre_Launch_Critical_Checks.docx")


# ═══════════════════════════════════════════════════════════════════════
# DOC 2 — TEAM DEPLOYMENT CHECKLIST (short ops card)
# ═══════════════════════════════════════════════════════════════════════
def build_team_checklist():
    d = new_doc("Team Deployment Checklist",
                "One-Page Ops Card for Every Release",
                "VT-OPS-102", "Operations")

    h1(d, "Release Summary")
    table_rows(d, ["Field", "Value"], [
        ["Version", "____________________"],
        ["Deployer", "____________________"],
        ["Approver", "____________________"],
        ["Date & Time (UTC)", "____________________"],
        ["Git SHA", "____________________"],
        ["Rollback SHA", "____________________"],
    ])

    h1(d, "Phase 1 — Pre-Deploy (on laptop)")
    for it in [
        "Pull latest master; working tree clean",
        "Run `npm test && pytest -q` — all green",
        "Run `npm run build` in vantag/frontend/web — success",
        "Review CHANGELOG.md is updated",
        "Staging smoke test passed",
        "Announced maintenance window in #ops Telegram channel",
        "Rollback SHA noted above",
    ]:
        bullet(d, "☐  " + it)

    h1(d, "Phase 2 — Deploy")
    code_block(d, """
ssh root@187.127.112.32
cd /var/www/vantag
git fetch origin && git checkout master && git pull
source venv/bin/activate
pip install -r backend/requirements.txt --quiet
alembic -c backend/alembic.ini upgrade head
cd frontend/web && npm ci --silent && npm run build && cd ../..
systemctl restart vantag
systemctl reload nginx
""", "bash")
    for it in [
        "Migrations applied without error",
        "Frontend built (no warnings in output)",
        "systemctl restart vantag — active (running)",
        "nginx -t passed before reload",
    ]:
        bullet(d, "☐  " + it)

    h1(d, "Phase 3 — Smoke (within 5 min)")
    for it in [
        "curl https://retail-vantag.com/health → 200",
        "curl https://retailnazar.com/health → 200",
        "curl https://jagajaga.my/health → 200",
        "Open browser; login as demo; see dashboard",
        "Check Sentry — no new error classes since release",
        "Check /metrics — no request-error spike",
    ]:
        bullet(d, "☐  " + it)

    h1(d, "Phase 4 — Communicate")
    for it in [
        "Post release notes to #releases Telegram",
        "Tag git release: `git tag vX.Y.Z && git push --tags`",
        "Close completed tickets in issue tracker",
    ]:
        bullet(d, "☐  " + it)

    h1(d, "Rollback Procedure (if smoke fails)")
    code_block(d, """
cd /var/www/vantag
git checkout <ROLLBACK_SHA>
alembic -c backend/alembic.ini downgrade -1   # if schema changed
cd frontend/web && npm run build && cd ../..
systemctl restart vantag
systemctl reload nginx
# Verify health:
curl -skI https://retail-vantag.com/health
""", "bash")
    para(d, "If rollback does not restore service within 10 minutes, "
            "page the on-call tech lead and declare a P1 incident.",
         bold=True)

    h1(d, "Escalation Contacts")
    table_rows(d, ["Role", "Primary", "Backup"], [
        ["On-Call Engineer", "", ""],
        ["Tech Lead", "", ""],
        ["Security Officer", "", ""],
        ["Founder", "anandsg.kumar@gmail.com", ""],
        ["Razorpay Support", "support@razorpay.com", ""],
        ["Hostinger Support", "support@hostinger.com", ""],
    ])

    h1(d, "Post-Deploy Watch (next 24h)")
    for it in [
        "Review Sentry error volume hourly for first 4 hours",
        "Check conversion funnel — no sudden drop at any step",
        "Check payment webhook success rate in Razorpay dashboard",
        "Check Edge Agent heartbeat rate — should match pre-deploy baseline",
    ]:
        bullet(d, "☐  " + it)
    save(d, "04_Operations", "23_Team_Deployment_Checklist.docx")


if __name__ == "__main__":
    print("[Operations]")
    build_prelaunch()
    build_team_checklist()
    print("\nOps docs built.")
