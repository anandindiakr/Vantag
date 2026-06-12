"""
Build 20+ production-grade documents for the Vantag Retail Intelligence Platform.
Run: python build_all_docs.py
"""
from _common import *

# ════════════════════════════════════════════════════════════════════════════
# 01 — PRODUCT REQUIREMENTS DOCUMENT (PRD)
# ════════════════════════════════════════════════════════════════════════════
def build_prd():
    d = new_doc("Product Requirements Document", "Vantag — Retail Intelligence & Security Platform",
                "VT-PRD-001", "Product")
    toc(d, [
        ("1", "Executive Summary"), ("2", "Problem Statement"),
        ("3", "Target Users & Personas"), ("4", "Goals & Success Metrics"),
        ("5", "Product Scope — In & Out"), ("6", "Functional Requirements"),
        ("7", "Non-Functional Requirements"), ("8", "User Journeys"),
        ("9", "Release Plan"), ("10", "Risks & Mitigations"),
    ])

    h1(d, "1. Executive Summary")
    para(d, ("Vantag is a Software-as-a-Service (SaaS) Retail Security and Predictive Analytics "
             "platform that turns any existing IP camera into a 24/7 AI-powered guardian. Targeting "
             "small-to-medium retailers, shopping malls, hospitals, clinics, post offices, police "
             "stations, small offices, and homes across India (Retail Nazar), Singapore (Vantag), "
             "and Malaysia (JagaJaga), the platform detects 12 distinct security, safety, and "
             "operational events in real time — including shoplifting, loitering, fall incidents, "
             "empty-shelf events, inventory movement, restricted-zone entry, camera tampering, "
             "crowd density, after-hours intrusion, and more. All AI inference runs on a local Edge "
             "device, ensuring that customer video never leaves the premises — only lightweight "
             "event metadata is transmitted to the cloud dashboard."))

    h1(d, "2. Problem Statement")
    para(d, ("Retail shrinkage (theft, fraud, inventory loss) costs retailers 1.5–3 % of annual "
             "revenue globally, with emerging markets disproportionately affected. Traditional CCTV "
             "systems passively record footage, requiring human review that rarely occurs in time "
             "to prevent loss. Existing AI-CCTV solutions are prohibitively expensive (USD 5,000 – "
             "50,000 per store), require dedicated hardware, and lock customers into proprietary "
             "cameras. Small retailers—who most need protection—cannot access these tools."))

    h2(d, "2.1 Pain Points by Persona")
    table_rows(d, ["Persona", "Primary Pain", "Current Workaround"], [
        ["Small Retail Owner (2-10 cameras)", "Cannot afford dedicated security staff or premium AI", "Passive CCTV (>90 % never reviewed)"],
        ["Mall Facilities Manager", "16-60 cameras, cannot monitor all feeds simultaneously", "Hire 3-5 guards per shift"],
        ["Hospital Administrator", "Patient falls, unauthorized access to restricted zones", "Manual rounds by nursing staff"],
        ["Post Office / Police Station", "Public access areas need continuous vigilance", "Single officer on duty, easily distracted"],
        ["Homeowner", "Family safety when away; fall-detection for elderly", "Consumer cameras with false-alarm push notifications"],
    ], widths=[1.8, 2.5, 2.2])

    h1(d, "3. Target Users & Personas")
    personas = [
        ("Ravi Kumar", "Owner, Kirana Store (Mumbai, India)", "42", "3 cameras",
         "Losing Rs. 8,000–15,000/month to petty theft. Cannot hire a guard. Needs mobile alerts on his phone."),
        ("Siti Nurhaliza", "Manager, Convenience Chain (Penang, Malaysia)", "35", "22 cameras",
         "Runs 3 stores. Needs centralised view and empty-shelf alerts to manage inventory staff remotely."),
        ("Mr Tan", "Facilities Head, Shopping Mall (Singapore)", "51", "48 cameras",
         "Needs crowd analytics, slip-and-fall detection (insurance), and after-hours intrusion flags."),
        ("Dr Priya Nair", "Hospital Admin (Chennai, India)", "47", "30 cameras",
         "Patient falls, restricted-area (pharmacy/ICU) monitoring, staff-patient interaction audit."),
    ]
    for name, role, age, cams, pains in personas:
        h3(d, f"{name} — {role}")
        para(d, f"Age: {age}  |  Cameras: {cams}")
        para(d, f"Needs: {pains}")

    h1(d, "4. Goals & Success Metrics")
    table_rows(d, ["Goal", "Metric", "Target (12 months)"], [
        ["Acquire paying tenants", "Active paying tenants", "1,500"],
        ["Regional coverage", "Live tenants in IN / SG / MY", "IN: 1,200  SG: 150  MY: 150"],
        ["Setup time", "Median time from register to first event", "< 30 minutes"],
        ["Detection accuracy", "True-positive rate across 12 detectors", "> 92 %"],
        ["False-positive rate", "Alerts dismissed by user / total alerts", "< 8 %"],
        ["MRR", "Monthly Recurring Revenue", "USD 45,000"],
        ["NPS", "Net Promoter Score", "> 45"],
        ["Uptime", "Cloud dashboard availability", "> 99.5 %"],
    ], widths=[2.2, 2.6, 1.8])

    h1(d, "5. Product Scope")
    h2(d, "5.1 In-Scope (v1.0)")
    for item in [
        "Multi-tenant SaaS with region auto-detection (IN / SG / MY)",
        "12 AI detection types running on Edge Agent (YOLOv8-based)",
        "Real-time web + mobile dashboard with live feeds and event log",
        "Edge Agent for Android, Windows, Raspberry Pi, NVIDIA Jetson",
        "Automatic RTSP camera discovery (ONVIF, ARP, UPnP)",
        "MQTT-based smart-lock / door-control integration",
        "POS integration (Square, Shopify, generic REST)",
        "Razorpay payment gateway (INR, SGD, MYR)",
        "Multi-language UI (English, Hindi, Tamil, Telugu, Kannada, Malay, Malayalam, Marathi, Gujarati, Bengali, Punjabi)",
        "Super-admin dashboard for tenant lifecycle, revenue, and system health",
        "AI Support Chat (GPT-4o) with context-aware help",
    ]:
        bullet(d, item)

    h2(d, "5.2 Out-of-Scope (v1.0)")
    for item in [
        "Cloud-based AI inference (privacy/cost considerations — v2 roadmap)",
        "Custom-branded white-label deployments (enterprise v2)",
        "Facial recognition / biometric identification (legal/ethical scope)",
        "Natively-hosted video recording (NVR role reserved for customer's existing system)",
        "Blockchain-based evidence chain (future compliance feature)",
    ]:
        bullet(d, item)

    h1(d, "6. Functional Requirements")
    frs = [
        ("FR-01", "Tenant Self-Registration", "Owner registers shop with email, phone, country, shop name, currency. System auto-detects region by domain."),
        ("FR-02", "Plan Selection & Payment", "Customer picks Starter/Growth/Pro, pays via Razorpay in local currency. Subscription auto-renews."),
        ("FR-03", "Edge Agent Pairing", "System generates unique API key + QR code. Agent pairs with cloud via HTTPS after scanning QR."),
        ("FR-04", "Camera Auto-Discovery", "Agent runs ONVIF WS-Discovery, ARP scan, port probe on LAN. Returns camera list to cloud."),
        ("FR-05", "Manual Camera Entry", "Fallback form to enter RTSP URL manually with brand/model auto-hints from database of 200+ paths."),
        ("FR-06", "Zone Editor", "User draws polygons on camera snapshots to define shelf, restricted, queue, and no-entry zones."),
        ("FR-07", "12 AI Detectors", "Product Sweeping, Dwell, Empty Shelf, Theft, Inventory Movement, Fall, Zone Entry, Crowd, Camera Tamper, Staff Behaviour, After-Hours, License Plate."),
        ("FR-08", "Real-Time Event Stream", "WebSocket channel streams new events to dashboard within <2s of detection."),
        ("FR-09", "Evidence Capture", "On event, Agent captures 5-second video clip + 3 snapshots, uploads to cloud S3-compatible store."),
        ("FR-10", "Incident Review", "User views event list, filters by type/zone/camera/time; clicks evidence to replay."),
        ("FR-11", "One-Tap Door Lock", "Dashboard button publishes MQTT command to lock controller; confirms within 1 second."),
        ("FR-12", "Mobile Dashboard", "Progressive Web App (PWA) installable to Android/iOS home screen with push notifications."),
        ("FR-13", "Multi-Language UI", "Runtime language switcher; persisted to localStorage; auto-detected on first visit by region."),
        ("FR-14", "Super-Admin Panel", "System owner sees all tenants, MRR, incidents, health, user lifecycle actions."),
        ("FR-15", "AI Support Chat", "GPT-4o chat embedded in-app; grounded on product docs; escalates to support@retail-vantag.com."),
        ("FR-16", "Data Retention", "Events stored 30 days (Starter), 90 days (Growth), 365 days (Pro); configurable export."),
    ]
    table_rows(d, ["ID", "Requirement", "Description"], frs, widths=[0.7, 2.0, 4.1])

    h1(d, "7. Non-Functional Requirements")
    nfrs = [
        ("Performance", "Dashboard first-paint < 1.5s on 4G; WebSocket event latency < 200 ms"),
        ("Scalability", "Single VPS handles 500 tenants / 10,000 cameras; horizontal scale via read replicas + Redis pub/sub"),
        ("Availability", "> 99.5 % monthly uptime; RTO < 30 min; RPO < 5 min"),
        ("Security", "TLS 1.3, HSTS, OWASP Top-10 mitigated, JWT rotation, bcrypt passwords, pentest annually"),
        ("Privacy", "Video never leaves premises; PII stored only in customer's home region; GDPR/DPDP compliant"),
        ("Accessibility", "WCAG 2.1 AA on public pages; keyboard-navigable; screen-reader friendly"),
        ("Localisation", "11 languages; RTL ready; currency per region; locale-aware date/number formatting"),
        ("Observability", "Structured JSON logs; Prometheus metrics; Sentry error capture; uptime monitor every 60s"),
    ]
    table_rows(d, ["Category", "Requirement"], nfrs, widths=[1.8, 5.2])

    h1(d, "8. User Journeys — Happy Path")
    h2(d, "8.1 New Retailer Onboarding")
    code_block(d, """
flowchart LR
  A[Landing page] --> B[Register shop]
  B --> C[Pick plan]
  C --> D[Razorpay payment]
  D --> E[Download Edge Agent]
  E --> F[Scan QR on Agent]
  F --> G[Agent auto-detects cameras]
  G --> H[Confirm camera list]
  H --> I[Draw zones]
  I --> J[AI starts → events flow]
""", "mermaid")

    h2(d, "8.2 Incident Response")
    code_block(d, """
sequenceDiagram
  Camera ->> EdgeAgent: RTSP stream
  EdgeAgent ->> EdgeAgent: YOLOv8 inference
  EdgeAgent -->> Cloud: event {type, zone, evidence}
  Cloud -->> MobileApp: push notification
  MobileApp ->> Cloud: mark as resolved
""", "mermaid")

    h1(d, "9. Release Plan")
    table_rows(d, ["Phase", "Scope", "Target Release"], [
        ["v0.9 Beta", "Core 3 detectors, single region (SG), ≤ 50 tenants", "Completed"],
        ["v1.0 GA", "All 12 detectors, 3 regions, super-admin, Razorpay, PWA mobile", "Current"],
        ["v1.1", "POS deeper integrations, Loss-Prevention report pack, Jetson optimisation", "Q3 2026"],
        ["v1.2", "Cloud-Hybrid inference, white-label, CRM webhooks", "Q4 2026"],
        ["v2.0", "Enterprise SSO (Okta/Azure AD), on-prem option, federated multi-site", "Q2 2027"],
    ], widths=[1.2, 4.0, 1.8])

    h1(d, "10. Risks & Mitigations")
    table_rows(d, ["Risk", "Likelihood", "Impact", "Mitigation"], [
        ["AI false-positive rate too high", "Medium", "High", "Per-zone threshold tuning + user feedback loop retraining monthly"],
        ["Customer video privacy breach", "Low", "Critical", "Edge-first architecture — video never leaves LAN. Legal counsel review."],
        ["Razorpay webhook abuse", "Low", "High", "HMAC signature verification, idempotency keys, rate limit 10 req/s"],
        ["Edge Agent hardware cost barrier", "High", "Medium", "Android phone option (₹3,000), rental scheme for Pro tier"],
        ["Low search visibility at launch", "High", "Medium", "Blog content plan, Google Business profiles, 20+ inbound links Q1"],
    ], widths=[2.0, 0.9, 0.9, 3.2])

    save(d, "01_Product", "01_PRD_Product_Requirements_Document.docx")


# ════════════════════════════════════════════════════════════════════════════
# 02 — BUSINESS REQUIREMENTS DOCUMENT (BRD)
# ════════════════════════════════════════════════════════════════════════════
def build_brd():
    d = new_doc("Business Requirements Document", "Commercial & Operational Requirements",
                "VT-BRD-002", "Product")
    toc(d, [("1","Business Context"),("2","Objectives & KPIs"),("3","Market Sizing"),
            ("4","Revenue Model"),("5","Pricing Strategy"),("6","Go-to-Market"),
            ("7","Operational Model"),("8","Legal & Regulatory"),("9","Success Criteria")])

    h1(d, "1. Business Context")
    para(d, ("Vantag is positioned as the first DIY AI-security SaaS accessible to "
             "small-medium retailers in India, Singapore, and Malaysia. The Total "
             "Addressable Market is estimated at 8.2 million shops across the three "
             "regions (India 7M, Malaysia 1M, Singapore 200K). With a 1 % penetration "
             "over five years, the Serviceable Obtainable Market is 82,000 tenants "
             "generating USD 72M annual revenue at median ARPU."))

    h1(d, "2. Objectives & KPIs")
    table_rows(d, ["Objective", "Year-1 KPI", "Year-3 KPI"], [
        ["Tenant acquisition", "1,500", "18,000"],
        ["Gross Revenue", "USD 540K", "USD 7.2M"],
        ["Gross Margin", "68 %", "78 %"],
        ["CAC payback", "< 6 months", "< 4 months"],
        ["Churn (logo)", "< 6 %/month", "< 2.5 %/month"],
        ["NPS", "> 45", "> 60"],
    ], widths=[2.5, 2.0, 2.0])

    h1(d, "3. Market Sizing")
    table_rows(d, ["Region", "Total Shops (TAM)", "SAM (1 % reachable)", "SOM (Y3 target)"], [
        ["India", "7,000,000", "70,000", "15,000"],
        ["Malaysia", "1,000,000", "10,000", "2,000"],
        ["Singapore", "200,000", "5,000", "1,000"],
        ["Total", "8,200,000", "85,000", "18,000"],
    ], widths=[1.3, 1.8, 1.8, 1.6])

    h1(d, "4. Revenue Model")
    para(d, "Subscription-based SaaS with three tiers plus optional hardware resale.")
    bullet(d, "Monthly subscriptions (primary — 82 % of revenue)")
    bullet(d, "Annual prepayment with 17 % discount (13 % of revenue)")
    bullet(d, "Optional Edge Agent hardware kit (Android mini-PC bundle, one-time ₹7,500 / S$129 / RM379)")
    bullet(d, "Enterprise site-licenses with SLA (v1.2 onwards)")

    h1(d, "5. Pricing Strategy")
    h2(d, "India (INR)")
    table_rows(d, ["Plan", "Cameras", "Monthly", "Annual (17% off)"], [
        ["Starter", "5", "Rs. 1,999", "Rs. 1,666/mo"],
        ["Growth", "15", "Rs. 4,499", "Rs. 3,749/mo"],
        ["Pro", "30", "Rs. 8,999", "Rs. 7,499/mo"],
    ])
    h2(d, "Singapore (SGD)")
    table_rows(d, ["Plan", "Cameras", "Monthly", "Annual"], [
        ["Starter", "5", "S$ 39", "S$ 32/mo"],
        ["Growth", "15", "S$ 99", "S$ 82/mo"],
        ["Pro", "30", "S$ 189", "S$ 157/mo"],
    ])
    h2(d, "Malaysia (MYR)")
    table_rows(d, ["Plan", "Cameras", "Monthly", "Annual"], [
        ["Starter", "5", "RM 59", "RM 49/mo"],
        ["Growth", "15", "RM 149", "RM 124/mo"],
        ["Pro", "30", "RM 299", "RM 249/mo"],
    ])

    h1(d, "6. Go-to-Market")
    bullet(d, "Content SEO targeting 'AI CCTV for shop', 'retail theft detection', 'DIY security system'")
    bullet(d, "Google Ads on high-intent searches (~USD 2.5 CPC in India, S$8 in SG)")
    bullet(d, "Direct sales to mall management companies in SG (24 malls = 4,800 cameras potential)")
    bullet(d, "Distributor channel in India (CCTV installers get 20 % recurring commission)")
    bullet(d, "Partnership with local POS vendors (Square, Pine Labs) for cross-sell")

    h1(d, "7. Operational Model")
    table_rows(d, ["Function", "Staffing (Y1)", "Tools"], [
        ["Engineering", "1 full-stack + 1 ML eng (contract)", "GitHub, Linear, Sentry"],
        ["Customer Support", "1 L1 support + AI chat", "Zendesk, Intercom"],
        ["Sales", "1 BDE per region (India, SG, MY)", "HubSpot CRM"],
        ["Marketing / Content", "Part-time copywriter + SEO contractor", "Ghost blog, Ahrefs"],
        ["Operations / DevOps", "Founder-led", "Hostinger VPS + GCP optional"],
    ], widths=[1.6, 3.0, 2.4])

    h1(d, "8. Legal & Regulatory")
    bullet(d, "India — DPDP Act 2023 compliance; data resident within IN region")
    bullet(d, "Singapore — PDPA 2012 compliance; register with PDPC if > 10K personal records")
    bullet(d, "Malaysia — PDPA 2010 compliance; appoint local Data Protection Officer")
    bullet(d, "Razorpay merchant agreement and KYC for each region")
    bullet(d, "PCI-DSS SAQ-A scope (payment tokenisation handled by Razorpay, not Vantag)")

    h1(d, "9. Success Criteria")
    bullet(d, "1,500 paying tenants at month-12")
    bullet(d, "USD 45K MRR exit-run-rate by month-12")
    bullet(d, "Gross margin > 65 %")
    bullet(d, "< 5 P1 incidents per quarter")
    bullet(d, "No data breaches, zero customer video leaks")
    save(d, "01_Product", "02_BRD_Business_Requirements_Document.docx")


# ════════════════════════════════════════════════════════════════════════════
# 03 — SOFTWARE REQUIREMENTS SPECIFICATION (SRS)
# ════════════════════════════════════════════════════════════════════════════
def build_srs():
    d = new_doc("Software Requirements Specification", "IEEE 830 Format",
                "VT-SRS-003", "Product")
    toc(d, [("1","Introduction"),("2","Overall Description"),("3","Specific Requirements"),
            ("4","External Interfaces"),("5","Data Model"),("6","Non-Functional Requirements"),
            ("7","System Features"),("8","Appendices")])

    h1(d, "1. Introduction")
    h2(d, "1.1 Purpose")
    para(d, "This SRS defines the software requirements for Vantag v1.0 — the AI-powered retail security and predictive analytics SaaS platform.")
    h2(d, "1.2 Scope")
    para(d, "Covers the cloud backend (FastAPI), web frontend (React), mobile Progressive Web App, Edge Agent (Python), AI pipelines (YOLOv8), MQTT bridge, payment integration, and admin tooling.")
    h2(d, "1.3 Definitions")
    table_rows(d, ["Term", "Meaning"], [
        ["Tenant", "Paying customer organisation (shop owner / admin)"],
        ["Edge Agent", "Python app running on customer-premises device"],
        ["Incident", "AI-detected event requiring human review"],
        ["Zone", "Polygon drawn by user on a camera snapshot for targeted detection"],
        ["Evidence", "Video clip + snapshots captured for a given incident"],
    ])

    h1(d, "2. Overall Description")
    h2(d, "2.1 Product Perspective")
    code_block(d, """
flowchart TB
  subgraph Cloud [Vantag Cloud — VPS]
    API[FastAPI backend]
    DB[(PostgreSQL)]
    Redis[(Redis)]
    MQTT[Mosquitto MQTT]
    Web[React Web App]
  end
  subgraph Customer [Customer Premises]
    Agent[Edge Agent]
    Cam1[Camera 1]
    Cam2[Camera 2]
    NVR[NVR/DVR]
  end
  Agent -- HTTPS/WSS --> API
  Cam1 -- RTSP --> Agent
  Cam2 -- RTSP --> Agent
  NVR -- RTSP --> Agent
  Agent -- MQTT --> MQTT
  Web -- REST/WS --> API
""", "mermaid")

    h2(d, "2.2 User Classes")
    table_rows(d, ["Class", "Description", "Permissions"], [
        ["Tenant Owner", "Signed up & paid", "Full CRUD on own cameras, zones, users, billing"],
        ["Tenant Staff", "Invited by owner", "Read incidents, resolve alerts"],
        ["Super Admin", "System owner", "Full access to all tenants"],
        ["Edge Agent", "Machine identity", "Push camera data, stream events"],
        ["Anonymous", "Public website visitor", "Read marketing + docs"],
    ])

    h1(d, "3. Specific Requirements")
    h2(d, "3.1 Authentication & Authorisation")
    bullet(d, "JWT bearer tokens, RS256 signed, 24h expiry, refresh via rotate endpoint")
    bullet(d, "bcrypt(cost=12) password hashing")
    bullet(d, "Password reset flow via 6-digit OTP delivered over SMTP (Gmail App Password)")
    bullet(d, "Role-Based Access Control: owner / staff / super_admin")
    bullet(d, "Rate limiting: 5 failed logins/min triggers 15-min IP block")

    h2(d, "3.2 AI Inference Pipeline")
    bullet(d, "YOLOv8n-seg as base object detector, fine-tuned on retail dataset (~45K labelled frames)")
    bullet(d, "BoT-SORT tracker for cross-frame object identity")
    bullet(d, "Rule engine per detector type — e.g., Dwell = same track_id in zone > threshold_seconds")
    bullet(d, "Frame skip = 3 (every 4th frame processed) for performance")
    bullet(d, "TensorRT export on Jetson (7× speedup vs CPU)")

    h2(d, "3.3 Camera Discovery")
    bullet(d, "ONVIF WS-Discovery multicast to 239.255.255.250:3702")
    bullet(d, "ARP scan of local /24 subnet")
    bullet(d, "Port probe: 554 (RTSP), 80, 8080, 8000, 37777 (Dahua)")
    bullet(d, "RTSP URL database with 200+ paths per vendor")

    h1(d, "4. External Interfaces")
    table_rows(d, ["Interface", "Protocol", "Purpose"], [
        ["Razorpay Checkout", "HTTPS + Webhook HMAC", "Subscription creation & billing events"],
        ["Razorpay Subscriptions", "REST", "Recurring billing"],
        ["RTSP cameras", "RTSP/TCP over port 554", "Video ingest"],
        ["ONVIF devices", "SOAP over HTTP", "Camera discovery & PTZ control"],
        ["MQTT brokers", "MQTT 3.1.1 / 5", "Door-lock & IoT device control"],
        ["SMTP", "TLS over 465/587", "Transactional email"],
        ["Cloudflare Turnstile", "HTTPS", "Bot protection on register/login"],
        ["OpenAI GPT-4o", "HTTPS", "AI Support Chat"],
    ])

    h1(d, "5. Data Model Overview")
    code_block(d, """
erDiagram
  TENANTS ||--o{ TENANT_USERS : has
  TENANTS ||--o{ CAMERAS : owns
  TENANTS ||--o{ ZONES : has
  TENANTS ||--o{ INCIDENTS : generates
  TENANTS ||--|| SUBSCRIPTIONS : has
  CAMERAS ||--o{ ZONES : contains
  CAMERAS ||--o{ INCIDENTS : triggers
  INCIDENTS ||--o{ EVIDENCE : has
  TENANT_USERS ||--o{ SESSIONS : has
""", "mermaid")

    h1(d, "6. Non-Functional Requirements")
    para(d, "Refer to VT-PRD-001 §7. Additional:")
    bullet(d, "99.5 % uptime SLA; planned maintenance windows Sundays 02:00–04:00 local")
    bullet(d, "Horizontal scale target: 500 tenants / node")
    bullet(d, "Database backups: daily full + WAL streaming; 30-day retention; cross-region copy")

    h1(d, "7. System Features (high-level matrix)")
    table_rows(d, ["Feature", "FR Ref", "Priority"], [
        ["Tenant registration", "FR-01", "Must"],
        ["Payment via Razorpay", "FR-02", "Must"],
        ["Edge pairing via QR", "FR-03", "Must"],
        ["Auto-discovery", "FR-04", "Must"],
        ["12 detectors", "FR-07", "Must"],
        ["Zone editor", "FR-06", "Must"],
        ["Evidence capture", "FR-09", "Must"],
        ["POS integration", "FR-15", "Should"],
        ["Super-admin panel", "FR-14", "Must"],
        ["AI Support Chat", "FR-15", "Should"],
        ["Multi-language UI", "FR-13", "Must"],
    ])

    h1(d, "8. Appendices")
    para(d, "See companion docs: VT-HLD-005, VT-LLD-006, VT-API-008, VT-DB-007.")
    save(d, "01_Product", "03_SRS_Software_Requirements_Specification.docx")


if __name__ == "__main__":
    print("Building Vantag documentation package...\n")
    print("[Product]")
    build_prd()
    build_brd()
    build_srs()
    print("\nStage 1 complete. Run build_part2.py for Architecture docs.")
