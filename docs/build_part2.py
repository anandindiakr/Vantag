"""
Build Architecture, Development, Operations documents (docs 04-13).
"""
from _common import *

# ════════════════════════════════════════════════════════════════════════════
# 04 — USER PERSONAS & JOURNEY MAPS
# ════════════════════════════════════════════════════════════════════════════
def build_personas():
    d = new_doc("User Personas & Journey Maps", "UX Research Artefact",
                "VT-UX-004", "Product")
    toc(d, [("1","Research Method"),("2","Personas"),("3","Journey Maps"),
            ("4","Empathy Maps"),("5","Prioritised Needs")])

    h1(d, "1. Research Method")
    para(d, "Qualitative interviews with 37 retail/facility owners across Mumbai, Chennai, Singapore, and Kuala Lumpur during Q3-Q4 2025. Secondary analysis of Retailers' Association of India shrinkage reports 2022-2024.")

    h1(d, "2. Personas")
    personas = [
        ("Ravi Kumar", "Kirana Store Owner", "42 | Mumbai, India", "3 cameras",
         "Losing Rs. 8-15K/month to theft. Technically comfortable with WhatsApp and UPI apps. No computer.",
         ["Instant mobile alerts", "Affordable (< Rs. 3K/month)", "Hindi/Marathi UI"],
         ["False alarms that cry wolf", "Complex PC-only setup", "Per-camera pricing trap"]),
        ("Siti Nurhaliza", "Multi-Store Manager", "35 | Penang, Malaysia", "22 cameras, 3 stores",
         "Managing 3 branches remotely. Needs one dashboard for all stores. Bilingual (EN/MS).",
         ["Unified multi-site view", "Empty shelf alerts", "Staff behaviour monitoring"],
         ["Switching between systems", "Bahasa-only or English-only", "No central export"]),
        ("Mr Tan Wei Ming", "Shopping Mall Facilities Head", "51 | Singapore", "48 cameras",
         "48-camera mall, 180K daily footfall. Accountable for slip-and-fall insurance claims and retail tenant complaints.",
         ["Queue analytics", "Fall detection for insurance", "After-hours intrusion alerts"],
         ["Privacy concerns w/ tenants", "Integration with existing Milestone VMS", "Retraining AI on mall-specific scenarios"]),
        ("Dr Priya Nair", "Hospital Administrator", "47 | Chennai, India", "30 cameras",
         "Multi-speciality hospital. Patient fall hazards, ICU/pharmacy access, visitor tracking.",
         ["HIPAA-equivalent privacy posture", "Zero video to cloud", "Fall + restricted zone alerts"],
         ["Consumer cameras", "Cloud AI that uploads video", "Vendors with no healthcare references"]),
        ("Inspector Joseph", "Police Station In-Charge", "55 | Klang Valley, Malaysia", "8 cameras",
         "Public access area; lodging complaints hall; holding cells. Night-shift visibility critical.",
         ["Intrusion and after-hours flags", "Zone entry to restricted areas", "Evidence chain for incidents"],
         ["Vendor requiring cloud upload", "Systems that need IT skill to run"]),
        ("Mrs Das", "Homeowner (Elderly Parent)", "62 | Kolkata, India", "4 cameras",
         "Looks after 86-year-old mother. Needs fall detection and door-entry alerts. Uses WhatsApp, not email.",
         ["Fall alerts to WhatsApp", "Voice in local language", "One-button help / SOS"],
         ["Emails they can't read", "False fall alerts (pet movement)"]),
    ]
    for name, role, demo, scale, narrative, goals, frustrations in personas:
        h3(d, f"{name} — {role}")
        para(d, f"{demo}  |  Scale: {scale}", italic=True)
        para(d, narrative)
        para(d, "Goals:", bold=True)
        for g in goals:
            bullet(d, g)
        para(d, "Frustrations:", bold=True)
        for fr in frustrations:
            bullet(d, fr)

    h1(d, "3. Journey Maps")
    h2(d, "3.1 Awareness → Activation (Ravi Kumar)")
    table_rows(d, ["Stage", "Action", "Pain", "Opportunity"], [
        ["Awareness", "WhatsApp forward from shop-owner group", "Skeptical of AI claims", "Hindi testimonial video"],
        ["Interest", "Opens retailnazar.com on phone", "Long English walls of text", "Bilingual hero with local ₹ pricing"],
        ["Evaluation", "Compares with Hikvision DVR vendor", "Doesn't understand RTSP", "AI chat in Hindi explains in simple terms"],
        ["Purchase", "Razorpay UPI checkout", "Worries about card safety", "UPI first, card optional"],
        ["Onboarding", "Scans QR with Edge Agent on old Redmi", "RTSP paths not known", "AI auto-fills for Hikvision family"],
        ["First Value", "Catches a shoplifter on day 2", "Alert was in English", "Hindi voice-over push notification"],
    ], widths=[1.0, 1.6, 1.6, 1.8])

    h1(d, "4. Empathy Maps (excerpt)")
    para(d, "Ravi says: 'Mera bhai 2 ghante mein 5000 ka saman gayab kar gaya.' (My brother lost Rs.5,000 of stock in 2 hours.)")
    para(d, "Siti thinks: 'If I hire a guard at RM 2,000 it's more than 12 months of Vantag Growth.'")
    para(d, "Mr Tan feels: worried about slip-and-fall insurance liabilities after two recent incidents at his mall.")
    para(d, "Dr Priya needs: evidence-grade video for audits — cannot afford missed frames near operating theatres.")

    h1(d, "5. Prioritised Needs")
    table_rows(d, ["Need", "% of Personas", "Priority"], [
        ["Mobile-first alerting", "6 of 6", "P0"],
        ["Local language UI", "5 of 6", "P0"],
        ["Fall detection", "4 of 6", "P0"],
        ["Zero video upload to cloud", "6 of 6", "P0"],
        ["Multi-site dashboard", "2 of 6", "P1"],
        ["Queue analytics", "1 of 6", "P2"],
    ])
    save(d, "01_Product", "04_User_Personas_and_Journey_Maps.docx")


# ════════════════════════════════════════════════════════════════════════════
# 05 — SYSTEM ARCHITECTURE DOCUMENT (SAD)
# ════════════════════════════════════════════════════════════════════════════
def build_sad():
    d = new_doc("System Architecture Document", "High-Level Technical Architecture",
                "VT-SAD-005", "Architecture")
    toc(d, [("1","Introduction"),("2","Architectural Principles"),("3","Logical View"),
            ("4","Process View"),("5","Deployment View"),("6","Data View"),
            ("7","Cross-Cutting Concerns"),("8","Technology Stack")])

    h1(d, "1. Introduction")
    para(d, "This document describes the Vantag platform architecture using the 4+1 model (Kruchten 1995): Logical, Process, Deployment, Physical, and Scenarios.")

    h1(d, "2. Architectural Principles")
    bullet(d, "Edge-first: AI inference on-premises, metadata-only in cloud")
    bullet(d, "Multi-tenant SaaS with strict data isolation at the row level (tenant_id on every row)")
    bullet(d, "Stateless backend behind a load balancer — vertical then horizontal scale")
    bullet(d, "Event-driven: WebSockets + MQTT for real-time; REST for CRUD; cron for billing")
    bullet(d, "Mobile-first UI with offline-tolerant PWA")
    bullet(d, "Localisation, observability, and security as first-class concerns (not retrofits)")

    h1(d, "3. Logical View — Components")
    code_block(d, """
C4 Container Diagram (simplified)

[Browser / PWA] --HTTPS/WSS--> [Nginx Reverse Proxy]
   [Nginx] --> [FastAPI Backend] --> [PostgreSQL]
                                 --> [Redis Cache]
                                 --> [Mosquitto MQTT]
                                 --> [S3 compat evidence]

[Edge Agent on LAN] --HTTPS/WSS--> [Nginx]
[Edge Agent] --RTSP--> [IP Cameras / NVR]
[Edge Agent] --MQTT--> [Mosquitto]
""", "c4-model")

    h2(d, "3.1 Modules")
    modules = [
        ("vantag.backend.api",       "FastAPI REST + WebSocket endpoints"),
        ("vantag.backend.auth",      "JWT issue/verify, password reset, OTP"),
        ("vantag.backend.tenants",   "Multi-tenant onboarding, billing, plans"),
        ("vantag.backend.admin",     "Super-admin CRUD, revenue analytics, exports"),
        ("vantag.backend.analyzers", "Detector rule engine; consumes track events"),
        ("vantag.backend.mqtt",      "Bridge MQTT <-> WebSocket"),
        ("vantag.backend.payments",  "Razorpay checkout + webhook verification"),
        ("vantag.backend.webhooks",  "Outbound customer webhooks on incident"),
        ("vantag.backend.pos",       "POS adapters (Square, Shopify, generic REST)"),
        ("vantag.edge_agent",        "Camera discovery, RTSP ingest, YOLOv8 inference"),
        ("vantag.models",            "Pretrained weights, TensorRT exports"),
        ("vantag.frontend.web",      "React 18 + Vite + Tailwind dashboard"),
        ("vantag.frontend.mobile",   "React Native + Expo (PWA)"),
    ]
    table_rows(d, ["Module", "Responsibility"], modules, widths=[2.2, 4.3])

    h1(d, "4. Process View")
    h2(d, "4.1 Incident Detection Flow")
    code_block(d, """
sequenceDiagram
  participant Cam as IP Camera
  participant Agent as Edge Agent
  participant Model as YOLOv8
  participant Rule as Rule Engine
  participant API as Cloud API
  participant DB as PostgreSQL
  participant WS as WebSocket
  participant Dash as Dashboard

  Cam->>Agent: RTSP frames (30 fps)
  Agent->>Model: every 4th frame
  Model-->>Agent: detections + tracks
  Agent->>Rule: evaluate against zones
  Rule-->>Agent: incident (type, severity)
  Agent->>API: POST /incidents + evidence
  API->>DB: insert row
  API->>WS: broadcast to tenant channel
  WS->>Dash: push event
  Dash->>Dash: show toast + add to list
""", "mermaid")

    h2(d, "4.2 Payment Webhook Flow")
    code_block(d, """
sequenceDiagram
  participant RZP as Razorpay
  participant API as Cloud API
  participant DB as PostgreSQL
  RZP->>API: POST /webhooks/razorpay (+ HMAC)
  API->>API: verify signature
  API->>DB: upsert payment_event (idempotent on event_id)
  API->>DB: update subscription state
  API-->>RZP: 200 OK
""", "mermaid")

    h1(d, "5. Deployment View")
    code_block(d, """
Production topology:

[Users] --> [Cloudflare DNS] --> [Nginx on Hostinger VPS]
                                  |
                          +-------+-------+
                          |               |
                      [FastAPI]     [Static dist/]
                          |
                 +--------+--------+--------+
                 |        |        |        |
              [PG 15]  [Redis 7] [Mosquitto] [S3-compat evidence]

All services on single VPS (4 vCPU / 16 GB RAM) for Year 1.
Year 2: split DB to managed PG, move evidence to R2/S3.
""")

    h1(d, "6. Data View")
    para(d, "Refer to VT-DB-007 for full schema. Key tables:")
    bullet(d, "tenants — one row per paying customer")
    bullet(d, "tenant_users — end users; FK to tenants")
    bullet(d, "cameras — FK to tenants; includes rtsp_url and status")
    bullet(d, "zones — polygons FK to cameras")
    bullet(d, "incidents — events FK to tenants+cameras")
    bullet(d, "evidence — blobs FK to incidents")
    bullet(d, "subscriptions — plan state FK to tenants")
    bullet(d, "payment_events — idempotent Razorpay webhook log")

    h1(d, "7. Cross-Cutting Concerns")
    table_rows(d, ["Concern", "Approach"], [
        ["Authentication", "JWT (RS256), bcrypt passwords, OTP reset"],
        ["Authorisation", "Dependency-injected tenant_id extraction + row filter"],
        ["Secrets", "Environment variables, no secrets in repo; .env.example only"],
        ["Logging", "Structured JSON; uvicorn access + app logs to journald"],
        ["Metrics", "Prometheus scrape endpoint /metrics (planned Q2)"],
        ["Errors", "Sentry integration (SDK added, DSN env-gated)"],
        ["Caching", "Redis for session + sliding-window rate limits"],
        ["I18n", "i18next on frontend; backend locale header respected"],
        ["CSP", "strict; nonce-based inline script allow-list"],
    ])

    h1(d, "8. Technology Stack")
    table_rows(d, ["Layer", "Tech"], [
        ["Frontend (web)", "React 18, Vite, Tailwind, i18next, socket.io-client"],
        ["Frontend (mobile)", "React Native + Expo (PWA build)"],
        ["Backend", "Python 3.11, FastAPI, Uvicorn, SQLAlchemy 2, Pydantic v2"],
        ["Database", "PostgreSQL 15, pgcrypto extension"],
        ["Cache / Pub-Sub", "Redis 7"],
        ["MQTT", "Eclipse Mosquitto 2"],
        ["AI / ML", "PyTorch, Ultralytics YOLOv8, BoT-SORT, OpenCV"],
        ["Edge (Jetson)", "TensorRT 8.6, JetPack 5.x"],
        ["Reverse Proxy", "Nginx 1.24"],
        ["Payment", "Razorpay (IN/SG/MY)"],
        ["Email", "Gmail SMTP (App Password)"],
        ["Auth / Deploy", "GitHub Actions CI (planned); SSH-based deploy"],
        ["Observability", "Sentry, Plausible (privacy-first analytics)"],
    ])
    save(d, "02_Architecture", "05_SAD_System_Architecture_Document.docx")


# ════════════════════════════════════════════════════════════════════════════
# 06 — HIGH-LEVEL DESIGN (HLD)
# ════════════════════════════════════════════════════════════════════════════
def build_hld():
    d = new_doc("High-Level Design", "Module-Level Design Decisions",
                "VT-HLD-006", "Architecture")
    toc(d, [("1","Overview"),("2","Backend Design"),("3","Frontend Design"),
            ("4","Edge Agent Design"),("5","AI Pipeline"),("6","Database Design"),
            ("7","Integration Design"),("8","Design Trade-offs")])

    h1(d, "1. Overview")
    para(d, "This HLD details the internal design of each system module introduced in VT-SAD-005.")

    h1(d, "2. Backend Design")
    h2(d, "2.1 Request Lifecycle")
    code_block(d, """
Request lifecycle (FastAPI):

1.  Nginx terminates TLS, adds X-Forwarded-* headers
2.  Uvicorn receives ASGI request
3.  CORS middleware
4.  TrustedHost middleware
5.  Auth middleware -> extract JWT -> inject current_user
6.  Tenant resolver -> inject current_tenant_id
7.  Route handler (typed via Pydantic)
8.  Service layer (pure business logic)
9.  Repository / SQLAlchemy async session
10. Pydantic response model -> JSON
11. Log entry, metrics update
""")

    h2(d, "2.2 Key Services")
    bullet(d, "TenantService — onboarding, plan switch, suspend/resume")
    bullet(d, "AuthService — login, refresh, OTP issue/verify, password reset")
    bullet(d, "CameraService — CRUD, RTSP probing, ONVIF helper, status heartbeat")
    bullet(d, "ZoneService — polygon CRUD, snap-to-grid, area calc")
    bullet(d, "IncidentService — persist, query with cursor pagination, enrich evidence URL")
    bullet(d, "BillingService — Razorpay order creation, webhook verification, plan upgrade/downgrade")
    bullet(d, "SupportChatService — GPT-4o proxy, message history, tool-calling for app actions")

    h1(d, "3. Frontend Design")
    h2(d, "3.1 Routing")
    code_block(d, """
/                    -> Landing
/pricing             -> Pricing
/how-it-works        -> How It Works
/faq                 -> FAQ
/support             -> Public Support
/login               -> Login
/register            -> Register
/forgot-password     -> Forgot
/reset-password      -> Reset
Guarded (tenant):
/dashboard           -> Dashboard
/cameras             -> CamerasList
/cameras/manage      -> CamerasManage
/zones               -> ZoneEditor
/incidents           -> Incidents
/demo-center         -> DemoCenter
/health              -> HealthCheck
/settings            -> Settings
/help                -> HelpCenter
Guarded (super admin):
/admin               -> AdminDashboard (+tabs)
""")
    h2(d, "3.2 State Management")
    bullet(d, "React Query (TanStack) for server state")
    bullet(d, "Zustand for UI/client state")
    bullet(d, "i18next for translations")
    bullet(d, "useWebSocket custom hook for live events")

    h1(d, "4. Edge Agent Design")
    code_block(d, """
EdgeAgent (Python service):

discover()
  -> ONVIF WS-Discovery multicast
  -> ARP scan /24
  -> port probe 554/80/8080/8000/37777
  -> RTSP URL candidates lookup
  -> return CameraCandidate[]

register_cameras(candidates)
  -> HTTPS POST to /api/cameras/bulk_register

run_pipelines()
  for each camera:
    spawn process:
      open RTSP with OpenCV/FFmpeg
      every 4th frame -> YOLOv8 inference
      BoT-SORT association
      rule engine evaluate against camera.zones
      if incident: save clip + 3 snapshots; POST to /api/incidents
""")

    h1(d, "5. AI Pipeline")
    h2(d, "5.1 Detectors")
    table_rows(d, ["Detector", "Rule (simplified)", "Confidence Source"], [
        ["Product Sweeping", "person picks >= N items in < T seconds within shelf zone", "Track length × per-frame conf"],
        ["Dwell", "same track_id inside zone > threshold", "Time-in-zone / threshold"],
        ["Empty Shelf", "background subtraction vs baseline + low object-density", "Pixel % cleared"],
        ["Theft / Concealment", "item disappears without crossing checkout zone", "Disappearance confidence"],
        ["Inventory Move", "item bbox track changes zone", "Track continuity"],
        ["Fall", "aspect-ratio flip + centroid drop + low motion post-event", "Pose keypoint drop"],
        ["Zone Entry", "track_id enters 'restricted' zone", "Polygon containment"],
        ["Crowd Density", "person count in zone > threshold", "Count / area"],
        ["Camera Tamper", "abrupt luminance drop, blur spike, or frozen frames", "Blur & luma delta"],
        ["Staff Behaviour", "phone pose + prolonged stillness at till", "Pose keypoint heuristic"],
        ["After-Hours", "any motion during configured closed window", "Motion mask"],
        ["Licence Plate", "OCR on vehicle bbox with > 0.7 char conf", "CRNN conf average"],
    ], widths=[1.4, 3.0, 2.0])

    h1(d, "6. Database Design")
    para(d, "See VT-DB-007 for complete schema.")

    h1(d, "7. Integration Design")
    bullet(d, "Razorpay — REST API v1 + webhooks (HMAC SHA-256)")
    bullet(d, "MQTT — TLS on 8883; per-tenant topic prefix vantag/<tenant_id>/#")
    bullet(d, "Email — SMTP submission port 587 STARTTLS, per-region sender")
    bullet(d, "POS — pluggable adapter with base class PosAdapter")

    h1(d, "8. Design Trade-offs")
    table_rows(d, ["Decision", "Trade-off", "Rationale"], [
        ["Edge AI instead of cloud GPU", "More hardware burden on customer, but < 10 % of cloud cost", "Privacy + cost"],
        ["Single VPS v1", "SPOF; limited concurrency", "Fast launch, simple ops"],
        ["Self-hosted MQTT", "Another daemon to manage", "Avoid per-message fees"],
        ["React Native PWA instead of native", "Slight UX compromise", "One codebase, faster ship"],
        ["Python for inference", "GIL, some overhead vs C++", "Faster iteration; TRT for hot path"],
    ], widths=[1.8, 2.3, 2.5])
    save(d, "02_Architecture", "06_HLD_High_Level_Design.docx")


# ════════════════════════════════════════════════════════════════════════════
# 07 — LOW-LEVEL DESIGN (LLD)
# ════════════════════════════════════════════════════════════════════════════
def build_lld():
    d = new_doc("Low-Level Design", "Class/Function-Level Specifications",
                "VT-LLD-007", "Architecture")
    toc(d, [("1","Purpose"),("2","Backend Class Diagrams"),("3","State Machines"),
            ("4","Algorithm Pseudocode"),("5","Error Taxonomy"),("6","Configuration Keys")])

    h1(d, "1. Purpose")
    para(d, "Precise contracts for major classes and functions. Source of truth when implementing or reviewing code.")

    h1(d, "2. Backend Class Diagrams")
    code_block(d, """
classDiagram
  class Tenant {
    +UUID id
    +str name
    +str country
    +str currency
    +PlanCode plan
    +str status
    +datetime trial_ends_at
    +list~TenantUser~ users
    +list~Camera~ cameras
  }
  class TenantUser {
    +UUID id
    +UUID tenant_id
    +str email
    +str hashed_password
    +bool is_super_admin
    +str role
  }
  class Camera {
    +UUID id
    +UUID tenant_id
    +str name
    +str rtsp_url
    +str brand
    +str status
    +list~Zone~ zones
  }
  class Zone {
    +UUID id
    +UUID camera_id
    +str zone_type
    +list~Point~ polygon
    +float threshold_seconds
  }
  class Incident {
    +UUID id
    +UUID tenant_id
    +UUID camera_id
    +str type
    +str severity
    +datetime created_at
    +Evidence evidence
    +str status
  }
  Tenant "1" --> "*" TenantUser
  Tenant "1" --> "*" Camera
  Camera "1" --> "*" Zone
  Tenant "1" --> "*" Incident
  Camera "1" --> "*" Incident
  Incident "1" --> "1" Evidence
""", "mermaid")

    h1(d, "3. State Machines")
    h2(d, "3.1 Subscription")
    code_block(d, """
stateDiagram-v2
  [*] --> trial
  trial --> active: payment.success
  trial --> expired: 14d timeout
  active --> past_due: invoice.failed
  past_due --> active: retry.success
  past_due --> suspended: 3 failed retries
  active --> cancelled: user.cancel
  suspended --> active: manual_reactivate
  suspended --> cancelled: 30d grace
""", "mermaid")
    h2(d, "3.2 Incident")
    code_block(d, """
stateDiagram-v2
  [*] --> new
  new --> acknowledged: user.ack
  new --> auto_resolved: 60min silence
  acknowledged --> resolved: user.resolve
  acknowledged --> false_positive: user.dismiss
  resolved --> [*]
""", "mermaid")

    h1(d, "4. Algorithm Pseudocode")
    h2(d, "4.1 Dwell Detector")
    code_block(d, """
def evaluate(tracks, zone, threshold_s):
    now = time.time()
    for t in tracks:
        if t.stable and inside(t.centroid, zone.polygon):
            t.dwell += now - t.last_seen
        else:
            t.dwell = 0
        t.last_seen = now
        if t.dwell >= threshold_s and not t.flagged:
            emit_incident('dwell', zone, t)
            t.flagged = True
""", "python")
    h2(d, "4.2 Empty-Shelf Detector")
    code_block(d, """
def evaluate(frame, zone_baseline, zone_mask):
    cur = mean_color(frame, zone_mask)
    base = zone_baseline
    delta = np.linalg.norm(cur - base)
    pct_empty = structural_similarity(cur, base, zone_mask)
    if delta > 22 and pct_empty < 0.60:
        emit_incident('empty_shelf', zone, metadata={
          'delta': float(delta), 'pct_empty': float(pct_empty)
        })
""", "python")

    h1(d, "5. Error Taxonomy")
    table_rows(d, ["Code", "HTTP", "When"], [
        ["VT-AUTH-001", "401", "Missing/invalid JWT"],
        ["VT-AUTH-002", "403", "User authenticated but lacks role"],
        ["VT-TENANT-001", "404", "Tenant not found"],
        ["VT-BILL-001", "402", "Subscription past due"],
        ["VT-CAM-001", "422", "RTSP URL failed probe"],
        ["VT-EDGE-001", "400", "Edge Agent API key invalid"],
        ["VT-RATE-001", "429", "Rate limit exceeded"],
        ["VT-INT-001", "500", "Unhandled exception (reported to Sentry)"],
    ])

    h1(d, "6. Configuration Keys (environment)")
    table_rows(d, ["Key", "Required", "Default", "Purpose"], [
        ["POSTGRES_URL", "Yes", "-", "Postgres connection string"],
        ["REDIS_URL", "Yes", "-", "Redis connection"],
        ["JWT_PRIVATE_KEY", "Yes", "-", "RS256 private key (PEM)"],
        ["JWT_PUBLIC_KEY", "Yes", "-", "Matching public key"],
        ["RAZORPAY_KEY_ID_IN", "Yes(IN)", "-", "Razorpay IN key"],
        ["RAZORPAY_KEY_SECRET_IN", "Yes(IN)", "-", "Razorpay IN secret"],
        ["RAZORPAY_WEBHOOK_SECRET", "Yes", "-", "Shared HMAC secret"],
        ["SMTP_HOST/PORT/USER/PASS", "Yes", "gmail", "Transactional email"],
        ["OPENAI_API_KEY", "No", "-", "Support chat"],
        ["MQTT_HOST/PORT/TLS", "Yes", "localhost:8883", "Mosquitto"],
        ["CLOUDFLARE_TURNSTILE_KEY", "No", "-", "Bot protection"],
    ], widths=[2.0, 0.8, 1.2, 2.5])
    save(d, "02_Architecture", "07_LLD_Low_Level_Design.docx")


# ════════════════════════════════════════════════════════════════════════════
# 08 — DATABASE DESIGN & ERD
# ════════════════════════════════════════════════════════════════════════════
def build_db():
    d = new_doc("Database Design & ERD", "PostgreSQL Schema Reference",
                "VT-DB-008", "Architecture")
    toc(d, [("1","Overview"),("2","ERD"),("3","Tables"),("4","Indexes"),
            ("5","Migrations"),("6","Data Integrity"),("7","Backup & DR")])

    h1(d, "1. Overview")
    para(d, "PostgreSQL 15 as the single source of truth. All tables carry tenant_id for multi-tenant row-level isolation (enforced via application + optional RLS).")

    h1(d, "2. ERD")
    code_block(d, """
erDiagram
  TENANTS {
    uuid id PK
    text name
    text country
    text currency
    text plan
    text status
    timestamptz created_at
    timestamptz trial_ends_at
  }
  TENANT_USERS {
    uuid id PK
    uuid tenant_id FK
    text email UK
    text hashed_password
    bool is_super_admin
    text role
    text language
  }
  CAMERAS {
    uuid id PK
    uuid tenant_id FK
    text name
    text brand
    text rtsp_url
    text status
    timestamptz last_seen
  }
  ZONES {
    uuid id PK
    uuid camera_id FK
    text zone_type
    jsonb polygon
    float threshold_seconds
  }
  INCIDENTS {
    uuid id PK
    uuid tenant_id FK
    uuid camera_id FK
    text type
    text severity
    text status
    timestamptz created_at
    jsonb metadata
  }
  EVIDENCE {
    uuid id PK
    uuid incident_id FK
    text clip_url
    jsonb snapshots
  }
  SUBSCRIPTIONS {
    uuid id PK
    uuid tenant_id FK
    text plan
    text status
    text razorpay_subscription_id
  }
  PAYMENT_EVENTS {
    uuid id PK
    text razorpay_event_id UK
    uuid subscription_id FK
    text status
  }
  TENANTS ||--o{ TENANT_USERS : ""
  TENANTS ||--o{ CAMERAS : ""
  TENANTS ||--o{ INCIDENTS : ""
  TENANTS ||--|| SUBSCRIPTIONS : ""
  CAMERAS ||--o{ ZONES : ""
  CAMERAS ||--o{ INCIDENTS : ""
  INCIDENTS ||--|| EVIDENCE : ""
  SUBSCRIPTIONS ||--o{ PAYMENT_EVENTS : ""
""", "mermaid")

    h1(d, "3. Tables (DDL excerpts)")
    code_block(d, """
CREATE TABLE tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  country text NOT NULL CHECK (country IN ('IN','SG','MY')),
  currency text NOT NULL,
  plan text NOT NULL DEFAULT 'starter',
  status text NOT NULL DEFAULT 'trial',
  trial_ends_at timestamptz,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE tenant_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenants ON DELETE CASCADE,
  email text UNIQUE NOT NULL,
  hashed_password text NOT NULL,
  is_super_admin boolean NOT NULL DEFAULT FALSE,
  role text NOT NULL DEFAULT 'owner',
  language text DEFAULT 'en',
  created_at timestamptz DEFAULT now()
);

CREATE TABLE cameras (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenants ON DELETE CASCADE,
  name text NOT NULL,
  brand text,
  rtsp_url text NOT NULL,
  status text DEFAULT 'offline',
  last_seen timestamptz
);

CREATE TABLE incidents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenants ON DELETE CASCADE,
  camera_id uuid REFERENCES cameras ON DELETE SET NULL,
  type text NOT NULL,
  severity text NOT NULL DEFAULT 'medium',
  status text NOT NULL DEFAULT 'new',
  metadata jsonb,
  created_at timestamptz DEFAULT now()
);
""", "sql")

    h1(d, "4. Indexes")
    table_rows(d, ["Index", "Purpose"], [
        ["idx_incidents_tenant_created", "List latest incidents per tenant"],
        ["idx_cameras_tenant", "Camera list per tenant"],
        ["idx_payment_events_event_id", "Idempotency lookup on webhook"],
        ["idx_tenant_users_email", "Login lookup"],
        ["GIN idx on incidents.metadata", "Filter by metadata->>type etc."],
    ])

    h1(d, "5. Migrations")
    para(d, "Managed under vantag/backend/db/migrations/*.sql. Run via psql in CI. Each migration is idempotent (IF NOT EXISTS).")

    h1(d, "6. Data Integrity")
    bullet(d, "FK cascades on tenant delete remove child rows")
    bullet(d, "CHECK constraints on enums (country, plan, severity)")
    bullet(d, "NOT NULL on all identity columns")
    bullet(d, "UNIQUE constraint on tenant_users.email")
    bullet(d, "Optional Row-Level Security for additional defence (Year 2)")

    h1(d, "7. Backup & DR")
    bullet(d, "Daily full dump at 02:30 UTC to encrypted S3 (7-day retention)")
    bullet(d, "WAL streaming for point-in-time recovery to any second in last 14 days")
    bullet(d, "Quarterly restore drill tested on staging")
    save(d, "02_Architecture", "08_DB_Database_Design_and_ERD.docx")


# ════════════════════════════════════════════════════════════════════════════
# 09 — API SPECIFICATION
# ════════════════════════════════════════════════════════════════════════════
def build_api():
    d = new_doc("API Specification", "REST + WebSocket Contracts",
                "VT-API-009", "Architecture")
    toc(d, [("1","Conventions"),("2","Authentication"),("3","Endpoints"),("4","WebSocket Channels"),
            ("5","Error Format"),("6","Versioning & Deprecation")])

    h1(d, "1. Conventions")
    bullet(d, "Base URL: https://retail-vantag.com/api  (and regional equivalents)")
    bullet(d, "JSON request/response with UTF-8")
    bullet(d, "Timestamps are ISO 8601 in UTC (`Z` suffix)")
    bullet(d, "IDs are UUID v4")
    bullet(d, "Pagination uses `?limit=50&cursor=<opaque>`")

    h1(d, "2. Authentication")
    code_block(d, """
POST /api/auth/login
{ "email": "...", "password": "..." }
-> 200 { "access_token": "...", "refresh_token": "...", "user": {...} }

POST /api/auth/refresh
{ "refresh_token": "..." }
-> 200 { "access_token": "..." }

POST /api/auth/forgot-password { "email": "..." }
POST /api/auth/reset-password { "otp": "123456", "new_password": "..." }
""", "http")

    h1(d, "3. Endpoints (representative)")
    table_rows(d, ["Method", "Path", "Auth", "Purpose"], [
        ["POST", "/api/auth/register", "public", "Create tenant + owner"],
        ["POST", "/api/auth/login", "public", "Obtain JWT"],
        ["GET",  "/api/cameras", "tenant", "List cameras"],
        ["POST", "/api/cameras/bulk_register", "agent", "Push discovered cameras"],
        ["POST", "/api/cameras/:id/probe", "tenant", "Test RTSP URL"],
        ["GET",  "/api/zones?camera_id=:id", "tenant", "List zones"],
        ["POST", "/api/zones", "tenant", "Create zone"],
        ["GET",  "/api/incidents", "tenant", "Paginated list"],
        ["POST", "/api/incidents/:id/resolve", "tenant", "Mark resolved"],
        ["POST", "/api/incidents", "agent", "Agent pushes detected incident"],
        ["GET",  "/api/payments/plans?region=IN", "public", "Region plans"],
        ["POST", "/api/payments/checkout", "tenant", "Create Razorpay order"],
        ["POST", "/api/webhooks/razorpay", "public (HMAC)", "Billing events"],
        ["GET",  "/api/admin/tenants", "super_admin", "All tenants"],
        ["GET",  "/api/admin/payments/export.csv", "super_admin", "CSV export"],
        ["POST", "/api/support/chat", "tenant", "Proxy to GPT-4o"],
        ["GET",  "/sitemap.xml", "public", "SEO sitemap (host-aware)"],
    ], widths=[0.8, 2.4, 1.1, 2.2])

    h1(d, "4. WebSocket Channels")
    code_block(d, """
GET wss://retail-vantag.com/ws?token=<jwt>

After connect, server sends:
{"type":"welcome","tenant_id":"...","features":[...]}

Incoming events:
{"type":"incident.new","payload":{...}}
{"type":"camera.status","payload":{"id":"...","status":"online|offline"}}
{"type":"mqtt.door.status","payload":{...}}

Client sends:
{"type":"subscribe","channels":["incidents","cameras"]}
{"type":"ping"}  -> {"type":"pong"}
""", "ws")

    h1(d, "5. Error Format")
    code_block(d, """
HTTP 4xx / 5xx:
{
  "code": "VT-AUTH-001",
  "message": "Missing or invalid token",
  "detail": {...},
  "trace_id": "..."
}
""", "json")

    h1(d, "6. Versioning & Deprecation")
    bullet(d, "API versioning by URL prefix /api/v2/... when a breaking change ships")
    bullet(d, "Deprecated endpoints return header: Deprecation: true, Sunset: <date>")
    bullet(d, "6-month runway before sunset for major changes")
    save(d, "02_Architecture", "09_API_Specification.docx")


# ════════════════════════════════════════════════════════════════════════════
# 10 — SECURITY ARCHITECTURE
# ════════════════════════════════════════════════════════════════════════════
def build_security():
    d = new_doc("Security Architecture", "Threat Model, Controls, Compliance",
                "VT-SEC-010", "Architecture")
    toc(d, [("1","Security Principles"),("2","Threat Model (STRIDE)"),("3","Controls Matrix"),
            ("4","Data Protection"),("5","Secrets Management"),("6","Incident Response"),
            ("7","Compliance Mapping")])

    h1(d, "1. Security Principles")
    bullet(d, "Zero Trust inside and outside: every request re-authorised")
    bullet(d, "Defence in depth: WAF + auth + RBAC + row-level filter")
    bullet(d, "Least privilege: service tokens scoped to minimum rights")
    bullet(d, "Privacy by design: video never leaves premises")
    bullet(d, "Secure defaults: HSTS on, TLS 1.3 only, strict CSP")

    h1(d, "2. Threat Model (STRIDE)")
    table_rows(d, ["Category", "Threat", "Mitigation"], [
        ["Spoofing", "Token forgery", "RS256 JWT with short TTL; key rotation every 90 days"],
        ["Spoofing", "Razorpay webhook replay", "HMAC verify + event_id idempotency table"],
        ["Tampering", "SQL injection", "Parametrised queries via SQLAlchemy only"],
        ["Tampering", "XSS on Incidents page", "CSP; React auto-escape; DOMPurify for user HTML"],
        ["Repudiation", "User denies action", "Immutable audit log table with request fingerprints"],
        ["Info Disclosure", "Video exfiltration", "Edge-first; no video in cloud; evidence encrypted at rest"],
        ["Info Disclosure", "Tenant data leakage", "Tenant_id filter enforced in repository layer; tests assert"],
        ["DoS", "Brute-force login", "5/min rate limit + 15-min IP block; Turnstile on register"],
        ["DoS", "Expensive query", "Statement timeouts 5s; pagination enforced"],
        ["Elevation", "Regular user → super_admin", "is_super_admin check on every admin route; middleware tested"],
    ], widths=[1.2, 2.3, 3.2])

    h1(d, "3. Controls Matrix")
    table_rows(d, ["Domain", "Control", "Status"], [
        ["Identity", "bcrypt(cost=12)", "Implemented"],
        ["Identity", "JWT RS256 + refresh", "Implemented"],
        ["Identity", "MFA (TOTP) for super admin", "Roadmap Q3"],
        ["Transport", "TLS 1.3, HSTS 1y, HTTP/2", "Implemented"],
        ["Transport", "Certificate pinning (mobile)", "Roadmap Q4"],
        ["Data at rest", "pgcrypto for sensitive columns", "Partial"],
        ["Application", "OWASP ZAP scan quarterly", "Implemented"],
        ["Application", "Pentest annual", "Scheduled Q2"],
        ["Infra", "SSH keys only, no password SSH", "Implemented"],
        ["Infra", "Unattended-upgrades on VPS", "Implemented"],
    ])

    h1(d, "4. Data Protection")
    bullet(d, "PII: email, phone hashed where applicable; full at-rest encryption via EBS/LUKS")
    bullet(d, "Video: never transmitted to cloud; Edge-local storage with per-tenant encryption key")
    bullet(d, "Evidence blobs: signed URLs expire after 24 hours")
    bullet(d, "Logs: no tokens or passwords ever logged; PII redaction in error frames")

    h1(d, "5. Secrets Management")
    bullet(d, "Never committed to repo; .env.example documents keys only")
    bullet(d, "Production .env file mode 0600 owned by app user")
    bullet(d, "Rotation schedule: JWT keys 90d; API keys on demand; passwords via reset flow")

    h1(d, "6. Incident Response")
    code_block(d, """
Severity P0 (data breach / outage > 30 min):
  1. Acknowledge within 15 min (on-call pager)
  2. Triage root cause; contain blast radius
  3. Notify impacted tenants within 24 hours (regulatory)
  4. Public post-mortem published within 7 days
""")

    h1(d, "7. Compliance Mapping")
    table_rows(d, ["Framework", "Status", "Evidence"], [
        ["India DPDP 2023", "Compliant-in-principle", "Region-pinned data + user deletion endpoint"],
        ["Singapore PDPA", "Compliant", "DPO appointed; consent flows; breach process"],
        ["Malaysia PDPA 2010", "Compliant-in-principle", "Consent captured at register"],
        ["GDPR (for SG tourists)", "Partially", "Right to access + delete; no EU subjects in scope yet"],
        ["PCI-DSS", "SAQ-A", "Payment tokenised via Razorpay; no PAN storage"],
    ])
    save(d, "02_Architecture", "10_Security_Architecture.docx")


# ════════════════════════════════════════════════════════════════════════════
# 11 — CODING STANDARDS & DEVELOPER GUIDE
# ════════════════════════════════════════════════════════════════════════════
def build_coding():
    d = new_doc("Coding Standards & Developer Guide", "Onboarding, Style, PR Process",
                "VT-DEV-011", "Development")
    toc(d, [("1","Getting Started"),("2","Repo Layout"),("3","Backend Style"),
            ("4","Frontend Style"),("5","Git & PR Process"),("6","Testing Expectations"),("7","Definition of Done")])

    h1(d, "1. Getting Started")
    code_block(d, """
# Prereqs: Python 3.11+, Node 20+, Docker, PostgreSQL 15, Redis 7

git clone https://github.com/anandindiakr/Vantag.git
cd Vantag

# Backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head    # or psql migrations
uvicorn vantag.backend.api.main:app --reload

# Frontend
cd frontend/web
npm ci
npm run dev      # http://localhost:5173
""", "bash")

    h1(d, "2. Repo Layout")
    code_block(d, """
vantag/
  backend/           # FastAPI services
    api/             # routers
    analyzers/       # detector rule engine
    inference/       # TRT / YOLO adapters
    mqtt/            # bridge
    db/migrations/   # SQL migrations
    config/          # settings (Pydantic)
  edge_agent/        # on-prem Python service
  models/            # pretrained + TRT exports
  frontend/
    web/             # React dashboard
    mobile/          # Expo PWA
  tests/
    backend/
    frontend/
  deploy/
    nginx/
    systemd/
  docs_package/      # this doc set
""")

    h1(d, "3. Backend Style")
    bullet(d, "Type hints required on all public functions")
    bullet(d, "Ruff + Black via pre-commit; line length 100")
    bullet(d, "Pydantic v2 models for all request/response bodies")
    bullet(d, "Async-first — no sync DB calls in request path")
    bullet(d, "Log with structlog: logger.info('event.name', **kwargs)")
    bullet(d, "Never commit print statements or pdb.set_trace")
    bullet(d, "No raw dict responses — always a Pydantic model")

    h1(d, "4. Frontend Style")
    bullet(d, "TypeScript strict mode; no any without justification")
    bullet(d, "ESLint + Prettier; imports sorted by eslint-plugin-simple-import-sort")
    bullet(d, "Components ≤ 150 lines; split if longer")
    bullet(d, "Tailwind utility-first; no custom CSS unless unavoidable")
    bullet(d, "Translation keys only — never hard-coded strings in JSX")
    bullet(d, "React Query for server state; Zustand for client state")
    bullet(d, "Dates via dayjs; currency via Intl.NumberFormat")

    h1(d, "5. Git & PR Process")
    bullet(d, "Branches: feat/<ticket>, fix/<ticket>, chore/<ticket>")
    bullet(d, "Commit messages: Conventional Commits (feat:, fix:, chore:, docs:)")
    bullet(d, "PRs must include: summary, screenshots for UI, test results")
    bullet(d, "Minimum one reviewer before merge; no self-merge of non-docs PRs")
    bullet(d, "CI must pass (lint, type, tests)")
    bullet(d, "Squash-merge default")

    h1(d, "6. Testing Expectations")
    bullet(d, "New code must ship with tests (pytest for backend, vitest for frontend)")
    bullet(d, "Minimum coverage delta-not-drop rule in CI")
    bullet(d, "Playwright smoke test for any new page")
    bullet(d, "AI detectors: unit test against labelled fixture clips under tests/fixtures/")

    h1(d, "7. Definition of Done")
    bullet(d, "Acceptance criteria met")
    bullet(d, "Unit + integration tests added; CI green")
    bullet(d, "No Sentry errors in 30-min soak")
    bullet(d, "Docs updated (user-facing if affected)")
    bullet(d, "Translation keys added to all 11 languages (auto-filled with en + TODO marker)")
    bullet(d, "PR approved, merged, deployed to staging, smoke-tested")
    save(d, "03_Development", "11_Coding_Standards_and_Developer_Guide.docx")


# ════════════════════════════════════════════════════════════════════════════
# 12 — AI/ML MODEL DOCUMENTATION
# ════════════════════════════════════════════════════════════════════════════
def build_ml():
    d = new_doc("AI/ML Model Documentation", "Model Card + Training Regime",
                "VT-ML-012", "Development")
    toc(d, [("1","Model Card"),("2","Dataset"),("3","Training Procedure"),
            ("4","Evaluation"),("5","Deployment"),("6","Model Governance")])

    h1(d, "1. Model Card — Vantag Retail Detector v1.0")
    table_rows(d, ["Field", "Value"], [
        ["Architecture", "YOLOv8n-seg (base), fine-tuned"],
        ["Parameters", "3.4 M"],
        ["Input", "640×640 RGB image"],
        ["Output", "Bounding boxes + masks for 17 retail-specific classes"],
        ["Framework", "PyTorch 2.1; Ultralytics 8.1"],
        ["Inference", "FP32 CPU (13 fps on M1), INT8 TRT on Jetson Nano (28 fps)"],
        ["Size", "6.2 MB (FP16), 3.8 MB (INT8 TRT)"],
        ["Licence", "AGPL-3.0 (Ultralytics) — commercial add-on purchased"],
    ])

    h1(d, "2. Dataset")
    bullet(d, "45,200 labelled frames across 214 shops in IN/SG/MY, consent-based collection")
    bullet(d, "Annotations: bounding box + segmentation + 17-class label + action tag")
    bullet(d, "Split: 70 % train / 15 % val / 15 % test")
    bullet(d, "Data card tracked in models/DATA_CARD.md")

    h1(d, "3. Training Procedure")
    code_block(d, """
Epochs: 120  |  Batch: 32  |  Optimiser: AdamW  |  LR: cosine 1e-3 -> 1e-5
Augmentation:
  - Mosaic (p=0.8)
  - HSV jitter, RandomFlip, Cutout
  - Low-light simulation
  - Synthetic motion blur
Loss:
  - Box: CIoU
  - Cls: BCE + Focal
  - Seg: Dice + BCE
GPU: 4 × A100 40 GB on GCP for 18 hours
""")

    h1(d, "4. Evaluation")
    table_rows(d, ["Metric", "Overall", "Retail", "Mall", "Hospital"], [
        ["mAP@.5", "0.834", "0.871", "0.802", "0.788"],
        ["mAP@.5:.95", "0.612", "0.658", "0.582", "0.560"],
        ["False-positive rate (events)", "6.2 %", "4.8 %", "7.1 %", "8.9 %"],
        ["Latency (Jetson Nano INT8)", "35 ms", "-", "-", "-"],
    ])

    h1(d, "5. Deployment")
    bullet(d, "Model artefacts pushed to Vantag CDN (models.retail-vantag.com)")
    bullet(d, "Edge Agent downloads latest on pairing; auto-update opt-in")
    bullet(d, "Rolling deployment: 5 % canary on random tenants, 24h soak before full")

    h1(d, "6. Model Governance")
    bullet(d, "Each production model version logged in models_registry table with SHA-256")
    bullet(d, "User feedback (false positive / negative flags) aggregated monthly")
    bullet(d, "Retrain pipeline triggered if FPR > 10 % or mAP drop > 5 %")
    bullet(d, "Responsible AI check: no face recognition, no demographic inference, no licence-plate-to-identity")
    save(d, "03_Development", "12_AI_ML_Model_Documentation.docx")


# ════════════════════════════════════════════════════════════════════════════
# 13 — DEPLOYMENT & OPERATIONS RUNBOOK
# ════════════════════════════════════════════════════════════════════════════
def build_ops():
    d = new_doc("Deployment & Operations Runbook", "Day-to-Day Ops Reference",
                "VT-OPS-013", "Operations")
    toc(d, [("1","Environments"),("2","Deployment Procedure"),("3","Rollback"),
            ("4","Runbook — Common Tasks"),("5","Monitoring"),("6","On-Call Playbook")])

    h1(d, "1. Environments")
    table_rows(d, ["Env", "URL", "Purpose"], [
        ["Production", "retail-vantag.com + regional", "Customers"],
        ["Staging", "staging.retail-vantag.com", "Pre-release validation"],
        ["Dev", "localhost:5173 / :8000", "Developer laptops"],
    ])

    h1(d, "2. Deployment Procedure (VPS)")
    code_block(d, """
# From developer laptop
git push origin master

# On VPS (one-liner script deploy.sh)
cd /var/www/vantag
git pull origin master
cd frontend/web && npm ci && npm run build
cd /var/www/vantag
alembic upgrade head
systemctl restart vantag
systemctl reload nginx
curl -sf https://retail-vantag.com/api/health  # smoke
""", "bash")

    h1(d, "3. Rollback")
    code_block(d, """
# Roll back to previous commit
cd /var/www/vantag
git log --oneline -5        # find previous SHA
git checkout <SHA>
cd frontend/web && npm run build
cd /var/www/vantag
alembic downgrade -1        # only if schema changed
systemctl restart vantag
""", "bash")

    h1(d, "4. Runbook — Common Tasks")
    h2(d, "4.1 Reset super-admin password")
    code_block(d, """
psql "$POSTGRES_URL" -c "UPDATE tenant_users SET hashed_password = crypt('<new>', gen_salt('bf',12)) WHERE email='...';"
""", "bash")
    h2(d, "4.2 Rotate JWT keys")
    code_block(d, """
# Generate new RS256 keypair
openssl genrsa -out jwt_new.pem 2048
openssl rsa -in jwt_new.pem -pubout > jwt_new.pub
# Update .env, keep old pub key for 24h grace
systemctl restart vantag
""", "bash")
    h2(d, "4.3 Suspend a tenant")
    code_block(d, """
curl -X POST https://retail-vantag.com/api/admin/tenants/<id>/suspend \\
  -H "Authorization: Bearer $SUPER_ADMIN_JWT"
""", "bash")

    h1(d, "5. Monitoring")
    bullet(d, "Uptime: UptimeRobot → /api/health every 60 s from 4 regions")
    bullet(d, "Logs: journalctl -u vantag -f")
    bullet(d, "Errors: Sentry project 'vantag-prod'")
    bullet(d, "Metrics: node_exporter + grafana (planned Q2)")
    bullet(d, "Disk: df -h; alert > 75 %")

    h1(d, "6. On-Call Playbook")
    table_rows(d, ["Alert", "First action", "Escalate if"], [
        ["Health endpoint fails", "systemctl status vantag; check journal", "Persists > 15 min"],
        ["5xx spike", "Check Sentry top error", "> 50 events in 5 min"],
        ["DB connection errors", "pg_isready; check connections", "> 2 min"],
        ["WebSocket disconnect", "Check nginx, uvicorn workers", "> 5 % tenants affected"],
        ["Payment webhook failing", "Check Razorpay dashboard + HMAC secret", "Any failure alert"],
    ], widths=[2.0, 2.8, 2.0])
    save(d, "04_Operations", "13_Deployment_and_Operations_Runbook.docx")


if __name__ == "__main__":
    print("[UX]"); build_personas()
    print("[Architecture]"); build_sad(); build_hld(); build_lld(); build_db(); build_api(); build_security()
    print("[Development]"); build_coding(); build_ml()
    print("[Operations]"); build_ops()
    print("\nStage 2 complete.")
