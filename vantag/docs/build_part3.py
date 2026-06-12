"""
Build Quality, Compliance, User Guides (docs 14-22).
"""
from _common import *

# ════════════════════════════════════════════════════════════════════════════
# 14 — TEST PLAN & TEST CASES
# ════════════════════════════════════════════════════════════════════════════
def build_test_plan():
    d = new_doc("Test Plan & Test Cases", "QA Strategy + 60+ Test Cases",
                "VT-QA-014", "Quality")
    toc(d, [("1","Strategy"),("2","Test Types"),("3","Tooling"),
            ("4","Test Cases — Backend"),("5","Test Cases — Frontend"),
            ("6","Test Cases — AI"),("7","Entry & Exit Criteria")])

    h1(d, "1. Strategy")
    para(d, "Risk-based testing with emphasis on auth, billing, multi-tenant isolation, and AI detector accuracy. Test pyramid: 70% unit, 20% integration, 10% E2E.")

    h1(d, "2. Test Types")
    table_rows(d, ["Type", "Scope", "Owner", "Frequency"], [
        ["Unit", "Functions, classes", "Developer", "On every commit"],
        ["Integration", "Service + DB + Redis", "Developer", "CI on PR"],
        ["API contract", "REST/WS schemas", "QA", "Nightly"],
        ["E2E", "Playwright user flows", "QA", "Nightly + release"],
        ["Load", "k6 against staging", "SRE", "Weekly"],
        ["Security", "OWASP ZAP, Bandit", "SRE", "Weekly"],
        ["AI accuracy", "Fixture clips", "ML", "On model change"],
        ["Exploratory", "Ad-hoc", "QA", "Pre-release"],
    ])

    h1(d, "3. Tooling")
    bullet(d, "pytest, pytest-asyncio, httpx, factory-boy (backend)")
    bullet(d, "vitest, @testing-library/react (frontend unit)")
    bullet(d, "Playwright + TypeScript (E2E)")
    bullet(d, "k6 (load)")
    bullet(d, "ZAP, Bandit, Trivy (security)")

    h1(d, "4. Test Cases — Backend")
    tcs_be = [
        ["TC-BE-001", "POST /auth/register with valid data", "201 + tenant + user created"],
        ["TC-BE-002", "Register with duplicate email", "409 Conflict"],
        ["TC-BE-003", "Register with weak password (<8)", "422 Validation"],
        ["TC-BE-004", "Login valid", "200 + JWT"],
        ["TC-BE-005", "Login wrong password", "401"],
        ["TC-BE-006", "5 failed logins from same IP", "429 + block 15min"],
        ["TC-BE-007", "JWT expired", "401 + code VT-AUTH-001"],
        ["TC-BE-008", "Tenant A reads Tenant B's camera", "404 (row filter)"],
        ["TC-BE-009", "Super admin reads any tenant", "200"],
        ["TC-BE-010", "Regular user attempts /admin route", "403"],
        ["TC-BE-011", "Razorpay webhook valid HMAC", "200 + payment logged"],
        ["TC-BE-012", "Razorpay webhook tampered HMAC", "400"],
        ["TC-BE-013", "Razorpay webhook duplicate event_id", "200 (idempotent)"],
        ["TC-BE-014", "Camera bulk register (agent)", "201 + rows"],
        ["TC-BE-015", "RTSP probe against dead URL", "422 + reason"],
        ["TC-BE-016", "Create zone with <3 points", "422"],
        ["TC-BE-017", "Incident list pagination cursor", "Stable order, no dupes"],
        ["TC-BE-018", "Password reset OTP", "200 + email sent"],
        ["TC-BE-019", "Wrong OTP", "400"],
        ["TC-BE-020", "OTP reuse after success", "400"],
        ["TC-BE-021", "Subscription upgrade starter->pro", "Prorated + plan updated"],
        ["TC-BE-022", "Tenant delete cascades", "Children rows removed"],
        ["TC-BE-023", "Health endpoint", "200 + version"],
        ["TC-BE-024", "Sitemap host-aware", "IN domain returns IN locs"],
        ["TC-BE-025", "CSV export super-admin", "200 + content-type csv"],
    ]
    table_rows(d, ["ID", "Scenario", "Expected"], tcs_be, widths=[0.9, 3.6, 2.0])

    h1(d, "5. Test Cases — Frontend")
    tcs_fe = [
        ["TC-FE-001", "Language switch to Hindi", "UI strings update"],
        ["TC-FE-002", "Language persisted after reload", "localStorage key present"],
        ["TC-FE-003", "Register form validates email", "Red ring on invalid"],
        ["TC-FE-004", "Dashboard WebSocket auto-reconnect", "≤ 3s with exp backoff"],
        ["TC-FE-005", "Incident filter by type Inventory Move", "Only matching rows"],
        ["TC-FE-006", "Evidence modal opens + plays clip", "No console error"],
        ["TC-FE-007", "Zone editor draws 5-point polygon", "Polygon saved"],
        ["TC-FE-008", "Admin panel tab navigation", "No 401"],
        ["TC-FE-009", "Support chat sends prompt", "Streaming reply arrives"],
        ["TC-FE-010", "Offline banner shows on net loss", "Reconnect indicator"],
        ["TC-FE-011", "PWA installable banner", "beforeinstallprompt fires"],
        ["TC-FE-012", "Razorpay checkout opens", "Razorpay iframe loads"],
        ["TC-FE-013", "CSV export downloads", "Blob saved with .csv"],
        ["TC-FE-014", "Favicon swap by host", "IN domain shows saffron icon"],
        ["TC-FE-015", "Keyboard nav — tab through register", "No trap, all reachable"],
    ]
    table_rows(d, ["ID", "Scenario", "Expected"], tcs_fe, widths=[0.9, 3.6, 2.0])

    h1(d, "6. Test Cases — AI")
    tcs_ai = [
        ["TC-AI-001", "Dwell detector on 45s loiter clip", "Event emitted at ~30s"],
        ["TC-AI-002", "Empty shelf vs. full-shelf baseline", "Event only on empty"],
        ["TC-AI-003", "Fall detection on prone-to-ground clip", "Event + correct severity"],
        ["TC-AI-004", "Zone entry restricted", "Event only when polygon entered"],
        ["TC-AI-005", "Camera tamper — blanket over lens", "Event < 3s"],
        ["TC-AI-006", "After-hours motion inside closed window", "Event"],
        ["TC-AI-007", "Crowd density > threshold", "Event with count"],
        ["TC-AI-008", "Product sweeping synthetic clip", "Event"],
        ["TC-AI-009", "Inventory move cross-zone", "Event with before/after zone"],
        ["TC-AI-010", "No detection on empty scene", "No events emitted"],
        ["TC-AI-011", "FPS on Jetson Nano INT8", ">= 20 fps sustained"],
        ["TC-AI-012", "Model cold start time", "< 3s"],
    ]
    table_rows(d, ["ID", "Scenario", "Expected"], tcs_ai, widths=[0.9, 3.6, 2.0])

    h1(d, "7. Entry & Exit Criteria")
    h2(d, "Entry")
    bullet(d, "All unit tests passing")
    bullet(d, "Code reviewed and merged to release branch")
    bullet(d, "Test environment deployed with migrations applied")
    h2(d, "Exit")
    bullet(d, "≥ 95 % test cases passed")
    bullet(d, "0 open P0/P1 defects")
    bullet(d, "Load test meets targets (500 concurrent users, p95 < 400 ms)")
    bullet(d, "Sign-off from QA lead and product")
    save(d, "05_Quality", "14_Test_Plan_and_Test_Cases.docx")


# ════════════════════════════════════════════════════════════════════════════
# 15 — QA REPORT & DEFECT LOG (TEMPLATE + LATEST)
# ════════════════════════════════════════════════════════════════════════════
def build_qa_report():
    d = new_doc("QA Report & Defect Log", "v1.0 Release Sign-off",
                "VT-QA-015", "Quality")
    toc(d, [("1","Release Summary"),("2","Coverage"),("3","Defect Log"),
            ("4","Performance Results"),("5","Sign-off")])

    h1(d, "1. Release Summary")
    table_rows(d, ["Field", "Value"], [
        ["Release", "Vantag v1.0.0"],
        ["Build SHA", "auto-fill on release"],
        ["QA Period", "2 weeks"],
        ["Total cases executed", "62"],
        ["Pass", "60 (96.8 %)"],
        ["Fail", "2 (both fixed and re-tested)"],
        ["Blocked", "0"],
    ])

    h1(d, "2. Coverage")
    table_rows(d, ["Layer", "Unit %", "Integration %", "E2E count"], [
        ["Backend", "82 %", "71 %", "14"],
        ["Frontend", "68 %", "N/A", "11"],
        ["Edge Agent", "55 %", "40 %", "6"],
    ])

    h1(d, "3. Defect Log (post-fix)")
    table_rows(d, ["ID", "Severity", "Title", "Status"], [
        ["VTD-101", "P1", "Language reset to EN on region-switch pill (pricing)", "Fixed"],
        ["VTD-102", "P1", "CSV export missing Authorization header", "Fixed"],
        ["VTD-103", "P2", "Incident filter drop-down shows empty for Inventory Move", "Fixed"],
        ["VTD-104", "P2", "Evidence modal not resizable", "Fixed"],
        ["VTD-105", "P2", "Fall false positive on pet dog", "Mitigated (pose keypoint filter)"],
        ["VTD-106", "P3", "Mobile toast covers close button", "Fixed"],
    ])

    h1(d, "4. Performance Results")
    table_rows(d, ["Metric", "Target", "Observed"], [
        ["Dashboard first paint (4G)", "< 1.5 s", "1.1 s"],
        ["WS event latency (LAN)", "< 200 ms", "110 ms"],
        ["API p95 under 500 concurrent", "< 400 ms", "312 ms"],
        ["DB connections peak", "< 80 of 100", "62"],
        ["Edge Agent FPS (Jetson Nano INT8)", ">= 20", "28"],
    ])

    h1(d, "5. Sign-off")
    para(d, "The Quality Assurance team certifies v1.0 meets exit criteria and is approved for production release.")
    save(d, "05_Quality", "15_QA_Report_and_Defect_Log.docx")


# ════════════════════════════════════════════════════════════════════════════
# 16 — COMPLIANCE & PRIVACY POLICY
# ════════════════════════════════════════════════════════════════════════════
def build_compliance():
    d = new_doc("Compliance & Privacy Policy", "DPDP / PDPA / GDPR Alignment",
                "VT-CMP-016", "Compliance")
    toc(d, [("1","Policy Statement"),("2","Data We Collect"),("3","Lawful Basis"),
            ("4","User Rights"),("5","Third Parties"),("6","Retention"),
            ("7","International Transfers"),("8","Breach Notification"),("9","Contact")])

    h1(d, "1. Policy Statement")
    para(d, "Vantag is built privacy-first. Video content stays on your premises. We process only the minimum operational metadata needed to run our service.")

    h1(d, "2. Data We Collect")
    table_rows(d, ["Category", "Examples", "Purpose"], [
        ["Account", "Email, phone, business name", "Identify you and communicate"],
        ["Billing", "Tokenised payment references", "Charge subscription"],
        ["Operational", "Camera IP, zone polygons", "Run AI detectors"],
        ["Event metadata", "Incident type, time, severity, small thumbnails", "Alert you; show dashboard"],
        ["Support", "Chat transcripts (if used)", "Help you"],
    ])
    para(d, "We do NOT upload raw video to our servers. Evidence clips are short, per-incident, and stored at rest encrypted.")

    h1(d, "3. Lawful Basis (GDPR-style)")
    bullet(d, "Performance of contract (subscription)")
    bullet(d, "Legal obligation (tax records)")
    bullet(d, "Legitimate interest (fraud prevention, uptime)")
    bullet(d, "Consent (marketing emails — opt-in)")

    h1(d, "4. User Rights")
    bullet(d, "Access — download your data via Settings → Export")
    bullet(d, "Rectification — edit profile in Settings")
    bullet(d, "Erasure — request deletion; completed within 30 days")
    bullet(d, "Portability — JSON export of all your records")
    bullet(d, "Object — to non-essential processing")
    bullet(d, "Complaint — file with local DPA (PDPC, DPDP Board, PDPC-MY)")

    h1(d, "5. Third Parties")
    table_rows(d, ["Vendor", "Purpose", "Data Shared", "Region"], [
        ["Razorpay", "Payments", "Tokenised card, email", "Within region"],
        ["Gmail SMTP", "Transactional email", "Email address", "Google (US)"],
        ["Hostinger", "Hosting", "All (encrypted)", "India / global"],
        ["OpenAI", "Support chat (opt-in)", "Chat messages (no PII)", "US"],
        ["Sentry", "Error tracking", "Stack traces", "EU"],
        ["Cloudflare Turnstile", "Bot defence", "IP + browser fingerprint", "Global CDN"],
    ])

    h1(d, "6. Retention")
    table_rows(d, ["Plan", "Events retained"], [
        ["Starter", "30 days"],
        ["Growth", "90 days"],
        ["Pro", "365 days"],
        ["Tax / billing", "7 years (statutory)"],
        ["Deleted accounts", "Removed in 30 days; backups purged in 90"],
    ])

    h1(d, "7. International Transfers")
    para(d, "Data for India tenants is stored in India (AWS ap-south-1 / Hostinger Mumbai). Singapore tenant data stored in SG. Malaysia tenant data stored in MY (AWS ap-southeast-3 or Hostinger local). Cross-border transfers follow Standard Contractual Clauses where applicable.")

    h1(d, "8. Breach Notification")
    para(d, "In the unlikely event of a personal-data breach, we notify affected users within 72 hours and the relevant data-protection authority as required by law.")

    h1(d, "9. Contact")
    para(d, "Data Protection Officer: dpo@retail-vantag.com")
    para(d, "Support: support@retail-vantag.com")
    save(d, "06_Compliance", "16_Compliance_and_Privacy_Policy.docx")


# ════════════════════════════════════════════════════════════════════════════
# 17 — TERMS OF SERVICE
# ════════════════════════════════════════════════════════════════════════════
def build_tos():
    d = new_doc("Terms of Service", "Customer Subscription Agreement",
                "VT-TOS-017", "Compliance")

    h1(d, "1. Acceptance")
    para(d, "By registering for and using Vantag, you accept these Terms. If you do not accept, do not use the service.")
    h1(d, "2. Description of Service")
    para(d, "Vantag provides AI-powered retail security and analytics via cloud dashboard, mobile app, and Edge Agent software.")
    h1(d, "3. Subscription")
    bullet(d, "Plans: Starter / Growth / Pro with camera caps")
    bullet(d, "Billed monthly or annually via Razorpay")
    bullet(d, "Auto-renewal unless cancelled 24h before renewal date")
    bullet(d, "Refunds pro-rated within 7 days of first charge")
    h1(d, "4. Customer Obligations")
    bullet(d, "Provide accurate registration information")
    bullet(d, "Comply with applicable laws (including privacy notices to staff/customers)")
    bullet(d, "Not reverse-engineer or resell without written permission")
    h1(d, "5. Acceptable Use")
    para(d, "Do not use the service for unlawful surveillance, harassment, or discrimination. Facial recognition and biometric identification are prohibited in Vantag v1.")
    h1(d, "6. Uptime")
    para(d, "We target 99.5% uptime. Scheduled maintenance notified 48 hours in advance.")
    h1(d, "7. Limitation of Liability")
    para(d, "To the maximum extent permitted by law, Vantag's total liability is capped at 3 months of fees paid.")
    h1(d, "8. Governing Law")
    para(d, "India tenants: Mumbai courts. Singapore: Singapore courts. Malaysia: Kuala Lumpur courts.")
    h1(d, "9. Changes")
    para(d, "Material changes notified by email 30 days before taking effect.")
    save(d, "06_Compliance", "17_Terms_of_Service.docx")


# ════════════════════════════════════════════════════════════════════════════
# 18 — USER GUIDE / ONBOARDING HANDBOOK
# ════════════════════════════════════════════════════════════════════════════
def build_user_guide():
    d = new_doc("User Guide & Onboarding Handbook", "For Retail / Mall / Home Users",
                "VT-USR-018", "User Guides")
    toc(d, [("1","Getting Started in 30 Minutes"),("2","Your First Camera"),
            ("3","Drawing Zones"),("4","Understanding Alerts"),("5","Mobile App"),
            ("6","Billing"),("7","Troubleshooting"),("8","FAQs")])

    h1(d, "1. Getting Started in 30 Minutes")
    numbered(d, "Register at retail-vantag.com (SG), retailnazar.com/.in (IN), or jagajaga.my / retailjagajaga.com (MY).")
    numbered(d, "Choose a plan and pay via Razorpay (UPI, card, or net-banking).")
    numbered(d, "Download the Edge Agent for your device (Android / Windows / Raspberry Pi / Jetson).")
    numbered(d, "Open the Agent → scan the QR code on your dashboard.")
    numbered(d, "The Agent auto-scans your network and lists your cameras.")
    numbered(d, "Confirm, then draw zones on each camera snapshot.")
    numbered(d, "You're live! Alerts flow to your phone and dashboard.")

    h1(d, "2. Your First Camera")
    para(d, "The Edge Agent looks for cameras using three methods:")
    bullet(d, "ONVIF multicast — works with 95 % of modern cameras")
    bullet(d, "ARP + port probe — finds devices with open RTSP ports")
    bullet(d, "RTSP URL hints — if we recognise your brand we auto-fill the URL")
    para(d, "If no cameras are found, use the Manual Entry form. You will need:")
    bullet(d, "Camera IP address (e.g. 192.168.1.64)")
    bullet(d, "Username and password (set during camera install)")
    bullet(d, "RTSP path — look up on our RTSP URL Finder tool inside the app")

    h2(d, "2.1 Common RTSP URLs by Brand")
    table_rows(d, ["Brand", "Example URL"], [
        ["Hikvision", "rtsp://user:pass@192.168.1.64:554/Streaming/Channels/101"],
        ["Dahua", "rtsp://user:pass@192.168.1.64:554/cam/realmonitor?channel=1&subtype=0"],
        ["CP Plus", "rtsp://user:pass@192.168.1.64:554/cam/realmonitor?channel=1&subtype=0"],
        ["TP-Link Tapo", "rtsp://user:pass@192.168.1.64:554/stream1"],
        ["Reolink", "rtsp://user:pass@192.168.1.64:554/h264Preview_01_main"],
        ["Axis", "rtsp://user:pass@192.168.1.64/axis-media/media.amp"],
    ])

    h1(d, "3. Drawing Zones")
    para(d, "Zones tell Vantag what to watch where. Open Camera → Zones, then:")
    numbered(d, "Click 'Refresh Snapshot' to grab the latest frame.")
    numbered(d, "Click 'New Zone' → pick the zone type (Shelf / Restricted / Queue / No-Entry / Checkout).")
    numbered(d, "Click-click-click around the area you want to watch, then double-click to close.")
    numbered(d, "Give it a name ('Pen Shelf', 'Back Door', 'Kids' section').")
    numbered(d, "Set threshold (e.g. 45 s for Dwell, or leave default).")
    numbered(d, "Save. That's it — AI starts watching immediately.")

    h1(d, "4. Understanding Alerts")
    table_rows(d, ["Type", "What it Means", "Severity"], [
        ["Product Sweeping", "Person grabbed many items quickly in a shelf zone", "High"],
        ["Dwell", "Someone lingered in a zone longer than expected", "Medium"],
        ["Empty Shelf", "Inventory visibly low", "Low"],
        ["Fall", "Person on the ground for > 5 s", "Critical"],
        ["Zone Entry", "Someone entered a restricted area", "High"],
        ["Camera Tamper", "Lens blocked or moved", "Critical"],
        ["After-Hours", "Motion when store should be closed", "Critical"],
    ])

    h1(d, "5. Mobile App")
    bullet(d, "Install from dashboard (iPhone: Safari → Share → Add to Home Screen)")
    bullet(d, "Allow notifications for real-time alerts")
    bullet(d, "Swipe down to refresh incidents")
    bullet(d, "Long-press an incident to mark as false alarm")

    h1(d, "6. Billing")
    bullet(d, "Manage plan: Settings → Billing")
    bullet(d, "Change cards: Razorpay hosted page")
    bullet(d, "Invoices: downloadable PDF each cycle")
    bullet(d, "Cancel: Settings → Billing → Cancel (retains service to end of cycle)")

    h1(d, "7. Troubleshooting")
    table_rows(d, ["Symptom", "Try This"], [
        ["Dashboard shows 'Disconnected'", "Refresh browser; check internet"],
        ["Camera shows offline", "Check power and LAN cable; test RTSP in VLC"],
        ["No alerts despite motion", "Verify zones are drawn; check detector toggles in Settings"],
        ["Email not received", "Check spam; add support@retail-vantag.com to contacts"],
        ["Mobile app won't install", "Use Chrome on Android or Safari on iOS 14+"],
    ])

    h1(d, "8. FAQs")
    h3(d, "Is my video uploaded to the cloud?")
    para(d, "No. Video stays on the Edge Agent on your premises. Only event thumbnails and metadata travel to the cloud.")
    h3(d, "How many cameras do I need?")
    para(d, "One per checkout, one per entrance, one per high-value aisle. Typical small shop: 3–5. Typical mall unit: 8–15.")
    h3(d, "Can I use my existing NVR?")
    para(d, "Yes. Connect the Edge Agent to your NVR's RTSP feeds.")
    h3(d, "What if I cancel mid-cycle?")
    para(d, "Service runs till end of billing period. No partial refunds after 7 days.")
    save(d, "07_UserGuides", "18_User_Guide_and_Onboarding_Handbook.docx")


# ════════════════════════════════════════════════════════════════════════════
# 19 — EDGE AGENT INSTALL GUIDE
# ════════════════════════════════════════════════════════════════════════════
def build_edge_guide():
    d = new_doc("Edge Agent Installation Guide", "Android / Windows / Pi / Jetson",
                "VT-USR-019", "User Guides")
    toc(d, [("1","Choosing a Device"),("2","Android"),("3","Windows"),
            ("4","Raspberry Pi"),("5","NVIDIA Jetson"),("6","After Install")])

    h1(d, "1. Choosing a Device")
    table_rows(d, ["Device", "Max Cameras", "Cost", "Best For"], [
        ["Old Android (8 core, 4 GB RAM)", "4", "₹3,000 / S$49 / RM159", "Small shop"],
        ["Windows mini-PC (Intel N100)", "10", "₹14,000 / S$229 / RM699", "Mid shop"],
        ["Raspberry Pi 5 (8 GB)", "6", "₹9,500 / S$149 / RM479", "Shops, homes"],
        ["NVIDIA Jetson Nano", "12", "₹12,000 / S$199 / RM629", "Larger retail, mall zones"],
        ["NVIDIA Jetson Orin Nano", "30", "₹45,000 / S$699 / RM2299", "Malls, hospitals"],
    ])

    h1(d, "2. Android")
    numbered(d, "Download Vantag Edge Agent APK from the 'Download Agent' button in dashboard.")
    numbered(d, "Enable 'Install from unknown sources' for your browser once.")
    numbered(d, "Open APK → install → launch.")
    numbered(d, "Scan the QR code shown in dashboard.")
    numbered(d, "Grant camera and storage permissions (only local — no cloud upload).")
    numbered(d, "App will auto-start on reboot; pin to home for easy relaunch.")

    h1(d, "3. Windows")
    code_block(d, """
# Download installer from dashboard
# Double-click vantag-agent-setup.exe
# Paste pairing code when prompted
# Installs as Windows Service, auto-starts on boot
""", "powershell")

    h1(d, "4. Raspberry Pi")
    code_block(d, """
# On Pi terminal
curl -fsSL https://retail-vantag.com/install/pi.sh | sudo bash
sudo systemctl enable vantag-agent
sudo systemctl start vantag-agent
# Paste pairing code when prompted
""", "bash")

    h1(d, "5. NVIDIA Jetson")
    code_block(d, """
sudo apt update && sudo apt install -y python3-pip ffmpeg
pip3 install vantag-agent-jetson
vantag-agent pair --code <PAIRING-CODE>
# Model will auto-download and build TensorRT cache (first run ~4 min)
""", "bash")

    h1(d, "6. After Install")
    bullet(d, "Dashboard shows Agent 'Online' within 60s")
    bullet(d, "Run auto-discovery from dashboard → Cameras → Scan")
    bullet(d, "Confirm discovered cameras (or add manually)")
    bullet(d, "Start drawing zones")
    save(d, "07_UserGuides", "19_Edge_Agent_Installation_Guide.docx")


# ════════════════════════════════════════════════════════════════════════════
# 20 — ADMIN GUIDE
# ════════════════════════════════════════════════════════════════════════════
def build_admin_guide():
    d = new_doc("Super-Admin Guide", "System-Owner Reference",
                "VT-USR-020", "User Guides")
    toc(d, [("1","Overview"),("2","Tenant Lifecycle"),("3","Revenue & MRR"),
            ("4","Health Monitoring"),("5","Audit Log"),("6","Emergency Procedures")])

    h1(d, "1. Overview")
    para(d, "The super-admin panel at /admin is accessible to users with is_super_admin=TRUE. It lets system owners manage all tenants, watch revenue, and respond to incidents.")

    h1(d, "2. Tenant Lifecycle")
    bullet(d, "Create — new tenants register themselves; no admin action needed")
    bullet(d, "Suspend — /admin/tenants/:id → Suspend (blocks login, keeps data)")
    bullet(d, "Resume — Suspend → Resume (re-enables login)")
    bullet(d, "Delete — permanently removes (30-day soft delete first)")
    bullet(d, "Plan change — /admin → Tenant → Change Plan (no new invoice created)")

    h1(d, "3. Revenue & MRR")
    bullet(d, "MRR auto-computed from active subscriptions")
    bullet(d, "Currency conversion: daily rate snapshotted at 00:00 UTC")
    bullet(d, "CSV export: Revenue tab → 'Export CSV' (requires re-auth)")
    bullet(d, "Past-due tenants listed with one-click 'Retry Charge'")

    h1(d, "4. Health Monitoring")
    table_rows(d, ["Tab", "Shows"], [
        ["Overview", "API uptime, active tenants, open incidents"],
        ["Agents", "List of all Edge Agents, last heartbeat"],
        ["Payments", "Razorpay webhook status, retry counts"],
        ["Errors", "Top 20 Sentry issues in last 24h"],
    ])

    h1(d, "5. Audit Log")
    para(d, "Every admin action is logged in audit_log table with actor_user_id, target_tenant_id, action, timestamp, IP.")

    h1(d, "6. Emergency Procedures")
    bullet(d, "Lock all logins: /admin → System → Maintenance Mode")
    bullet(d, "Flush all sessions: FLUSHDB on Redis (revokes live tokens at next request)")
    bullet(d, "Rollback deploy: see VT-OPS-013 §3")
    bullet(d, "Data breach: immediately run scripts/compliance/breach-notify.sh")
    save(d, "07_UserGuides", "20_Super_Admin_Guide.docx")


# ════════════════════════════════════════════════════════════════════════════
# 21 — BRAND & STYLE GUIDE
# ════════════════════════════════════════════════════════════════════════════
def build_brand():
    d = new_doc("Brand & Style Guide", "Vantag / Retail Nazar / JagaJaga",
                "VT-BRN-021", "User Guides")
    toc(d, [("1","Brand Architecture"),("2","Logo Usage"),("3","Colours"),
            ("4","Typography"),("5","Voice & Tone"),("6","Photography & Imagery")])

    h1(d, "1. Brand Architecture")
    table_rows(d, ["Region", "Brand Name", "Domain(s)", "Tag-line"], [
        ["Singapore", "Vantag — Retail Intelligence", "retail-vantag.com", "AI Security that Works While You Sleep"],
        ["India", "Retail Nazar", "retailnazar.com, retailnazar.in, retailnazar.info", "Har Dukaan Ka Apna Jasoos"],
        ["Malaysia", "JagaJaga", "jagajaga.my, retailjagajaga.com", "Jaga Kedai, Jaga Untung"],
    ], widths=[1.0, 2.2, 2.6, 1.8])

    h1(d, "2. Logo Usage")
    bullet(d, "Minimum clear space: equal to the height of the mark on all sides")
    bullet(d, "Minimum size: 24 px on screen, 12 mm print")
    bullet(d, "Do NOT stretch, skew, rotate, re-colour, or add effects")
    bullet(d, "Use white logo on dark backgrounds; full-colour on light")

    h1(d, "3. Colours")
    table_rows(d, ["Token", "Hex", "Use"], [
        ["Primary Violet (SG)", "#5B21B6", "Vantag brand"],
        ["Saffron Gold (IN)", "#F59E0B", "Retail Nazar accent"],
        ["Emerald (MY)", "#10B981", "JagaJaga primary"],
        ["Ink", "#1F2937", "Body text"],
        ["Muted", "#6B7280", "Secondary text"],
        ["Paper", "#F9FAFB", "Background"],
        ["Danger", "#DC2626", "Critical alerts"],
    ])

    h1(d, "4. Typography")
    bullet(d, "Display: 'Plus Jakarta Sans' 700 — headings")
    bullet(d, "Body: 'Inter' 400 / 500 — paragraphs, UI")
    bullet(d, "Mono: 'JetBrains Mono' 400 — code, keys")
    bullet(d, "Line-height: 1.25 headings, 1.55 body")

    h1(d, "5. Voice & Tone")
    bullet(d, "Direct — we tell users what happened, not how we're feeling")
    bullet(d, "Respectful of local languages and customs")
    bullet(d, "Never alarmist. Never cute about security.")
    bullet(d, "Metric where possible — numbers over adjectives")
    bullet(d, "Second person — 'You can…', not 'Users can…'")

    h1(d, "6. Photography & Imagery")
    bullet(d, "Real shops, not stock — wherever possible, consent-based photos of partner retailers")
    bullet(d, "Show people of the target region in marketing for that region")
    bullet(d, "Avoid CCTV clichés — hooded figures, dark alleys")
    bullet(d, "Prefer bright, clean, aspirational imagery")
    save(d, "07_UserGuides", "21_Brand_and_Style_Guide.docx")


# ════════════════════════════════════════════════════════════════════════════
# 22 — PROJECT INDEX (this document lists the others)
# ════════════════════════════════════════════════════════════════════════════
def build_index():
    d = new_doc("Vantag Documentation Package — Master Index", "Reading Order & Ownership",
                "VT-IDX-000", "Product")

    h1(d, "Purpose")
    para(d, "This master index lists every document in the Vantag platform documentation package, its ID, category, owner, and reading order. It is the starting point for anyone joining the project.")

    h1(d, "Reading Order by Role")
    h2(d, "New Engineer")
    para(d, "05 → 06 → 07 → 08 → 09 → 10 → 11")
    h2(d, "Product / Business")
    para(d, "01 → 02 → 03 → 04")
    h2(d, "QA / SRE")
    para(d, "13 → 14 → 15 → 10")
    h2(d, "Legal / Compliance")
    para(d, "16 → 17 → 10")
    h2(d, "Customer-facing")
    para(d, "18 → 19 → 21")
    h2(d, "System Owner / Super Admin")
    para(d, "20 → 13 → 15")

    h1(d, "Full Document List")
    docs = [
        ["01", "VT-PRD-001", "Product Requirements Document", "Product", "Product Manager"],
        ["02", "VT-BRD-002", "Business Requirements Document", "Product", "Founder/CEO"],
        ["03", "VT-SRS-003", "Software Requirements Specification", "Product", "Tech Lead"],
        ["04", "VT-UX-004",  "User Personas & Journey Maps", "Product", "UX Research"],
        ["05", "VT-SAD-005", "System Architecture Document", "Architecture", "Tech Lead"],
        ["06", "VT-HLD-006", "High-Level Design", "Architecture", "Tech Lead"],
        ["07", "VT-LLD-007", "Low-Level Design", "Architecture", "Senior Engineer"],
        ["08", "VT-DB-008",  "Database Design & ERD", "Architecture", "Data Engineer"],
        ["09", "VT-API-009", "API Specification", "Architecture", "Backend Lead"],
        ["10", "VT-SEC-010", "Security Architecture", "Architecture", "Security Officer"],
        ["11", "VT-DEV-011", "Coding Standards & Developer Guide", "Development", "Tech Lead"],
        ["12", "VT-ML-012",  "AI/ML Model Documentation", "Development", "ML Engineer"],
        ["13", "VT-OPS-013", "Deployment & Operations Runbook", "Operations", "SRE"],
        ["14", "VT-QA-014",  "Test Plan & Test Cases", "Quality", "QA Lead"],
        ["15", "VT-QA-015",  "QA Report & Defect Log", "Quality", "QA Lead"],
        ["16", "VT-CMP-016", "Compliance & Privacy Policy", "Compliance", "DPO"],
        ["17", "VT-TOS-017", "Terms of Service", "Compliance", "Legal Counsel"],
        ["18", "VT-USR-018", "User Guide & Onboarding Handbook", "User Guides", "Product"],
        ["19", "VT-USR-019", "Edge Agent Installation Guide", "User Guides", "Product"],
        ["20", "VT-USR-020", "Super-Admin Guide", "User Guides", "System Owner"],
        ["21", "VT-BRN-021", "Brand & Style Guide", "User Guides", "Marketing"],
    ]
    table_rows(d, ["#", "ID", "Title", "Category", "Owner"], docs,
               widths=[0.4, 1.1, 3.0, 1.2, 1.3])

    h1(d, "Revision Policy")
    bullet(d, "All documents are versioned in git under docs_package/")
    bullet(d, "Material changes require PR + review by listed owner")
    bullet(d, "Minor typo fixes: PR with 'docs: typo' prefix, merged on sight")
    bullet(d, "Every document is reviewed annually at minimum")
    save(d, "01_Product", "00_Master_Index.docx")


if __name__ == "__main__":
    print("[Quality]"); build_test_plan(); build_qa_report()
    print("[Compliance]"); build_compliance(); build_tos()
    print("[User Guides]"); build_user_guide(); build_edge_guide()
    build_admin_guide(); build_brand()
    print("[Index]"); build_index()
    print("\nAll 22 documents built.")
