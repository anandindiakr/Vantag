# Vantag Platform — Full Audit Report

**Date**: 2026-04-27  
**Commit audited**: 935811a (Initial commit, `main` branch)  
**Auditor**: Automated deep-dive (read-only)

## Overall Scores (per area)

| Area | Score | Notes |
|---|---|---|
| Security | 55/100 | Plaintext RTSP creds, weak fallbacks, no rate-limit in app |
| Multi-tenancy | 62/100 | DB queries scoped, but WS + snapshot endpoints not |
| Payment integrity | 60/100 | Webhook sig verified, but no idempotency key, step-3 bypass |
| AI / Inference | 72/100 | Good fallbacks; no GPU auto-detect, low conf threshold |
| Edge Agent | 45/100 | Duplicate route conflict, no auth on simple endpoints |
| Observability | 48/100 | Basic logging; no Sentry, no Prometheus, no structured JSON |
| UX / Onboarding | 65/100 | Good flow; no forgot-password, session timeout, empty states |
| Business Logic | 50/100 | Hard 30-day SQLite purge; no roles beyond owner/admin |
| i18n | 68/100 | 12 languages loaded; no RTL; email templates English-only |
| Dev Experience | 58/100 | Some tests; no CI/CD; no Alembic migrations in place |
| Performance | 60/100 | In-memory event store; snapshots served unauthenticated |
| Competitive gaps | 50/100 | Missing: video search, cloud storage, scheduled reports |
| Mobile | 70/100 | Push + deep linking done; no biometric, no offline mode |

---

## Executive Summary

Vantag is a well-structured, actively developed retail SaaS with a coherent multi-tenant architecture, working payment flows, a functional AI inference pipeline (YOLO + 14 analyzers), and a polished onboarding wizard. The codebase shows thoughtful design patterns — bcrypt hashing, HMAC webhook verification, graceful YOLO fallback — suggesting competent engineering.

**However**, several issues create real risk before production launch:

1. **RTSP credentials are stored in plaintext** in `cameras.yaml` (committed to the repository) and echoed through the `create_camera` API without encryption at rest.
2. **The onboarding Step 3 (payment) can be bypassed** — if no `razorpay_payment_id` is supplied, the tenant is immediately set to `status="trial"` without any payment or signature check.
3. **WebSocket endpoints have zero authentication** — any client can subscribe to the global event stream `/ws/events` without a token, leaking all real-time retail alerts.
4. **A duplicate route conflict** exists in `edge_router.py` — both `POST /api/edge/register` paths will silently overwrite each other in FastAPI's router registry.
5. **The `.env` file containing the JWT secret is committed to the repo** (not in `.gitignore` at repository root level for actual secrets — only example files are excluded by pattern, but the live `.env` was found in the tree).

**Top 5 high-value improvements:**
1. Encrypt RTSP URLs at rest (DB column-level encryption or KMS)
2. Add JWT authentication to all WebSocket endpoints
3. Implement idempotency keys for webhook event processing
4. Add a `forgot-password` email flow (no reset mechanism exists)
5. Add structured JSON logging + Sentry error tracking

---

## Critical Findings (must fix before going live)

### CF-1: Live `.env` with real JWT secret committed to repository
- **File(s)**: `.env:2`
- **Risk**: JWT secret `c35317...` and face-encryption key are version-controlled. Anyone with repo read access can forge tokens for any tenant.
- **Recommended fix**: Add `.env` (not just `.env.local`) to `.gitignore`, rotate the secret, use environment-level injection (systemd `EnvironmentFile=`, Docker `--env-file`).
- **Effort**: XS

### CF-2: RTSP credentials in plaintext in cameras.yaml
- **File(s)**: `backend/config/cameras.yaml:123` (`rtsp://admin:admin@192.168.1.248:554/…`), lines 206, 306
- **Risk**: Camera credentials committed to VCS and stored as cleartext YAML. An attacker who accesses the server can replay RTSP streams or reconfigure cameras.
- **Recommended fix**: Store RTSP URLs in the encrypted Postgres `camera_config` table column (using `pgcrypto` or application-level AES). Do not commit `cameras.yaml` with real IPs/credentials.
- **Effort**: M

### CF-3: WebSocket endpoints have no authentication
- **File(s)**: `backend/api/websocket_router.py:181-241`
- **Risk**: `GET /ws/events` and `GET /ws/store/{store_id}/events` accept connections with no JWT check. Any unauthenticated party can receive all real-time alerts, snapshots, and events from all tenants.
- **Recommended fix**: Read `token` query parameter or `Authorization` header during WebSocket handshake; call `_decode_token()` before `manager.connect()`. Reject with `ws.close(code=4001)` on failure.
- **Effort**: S

### CF-4: Onboarding Step 3 (payment) bypass
- **File(s)**: `backend/api/onboarding_router.py:147-154`
- **Risk**: `POST /api/onboarding/step/3` — if `razorpay_payment_id` is `None`, the tenant is immediately set `status="active"` (actually `"trial"` — but no signature check is performed, allowing trial extension by repeated calls). No Razorpay signature verification happens in this path at all.
- **Recommended fix**: Either require a valid signed payment, or make trial activation a separate code path that cannot be called post-trial. Call `verify_payment_signature()` unconditionally when IDs are present.
- **Effort**: S

### CF-5: Duplicate route registration conflict in edge_router.py
- **File(s)**: `backend/api/edge_router.py:64` and `edge_router.py:202`
- **Risk**: Two `@edge_router.post("/register")` handlers are defined in the same file. FastAPI uses the first registered route, silently ignoring the second. The unauthenticated `simple_register_cameras` (line 202) accepts `tenant_id` directly with no API key check — meaning any caller who knows a `tenant_id` can register arbitrary camera IPs under that tenant.
- **Recommended fix**: Rename the simple route to `POST /register/simple` or `/register/agent`. Add at minimum a `tenant_id` validation check or require the onboarding token.
- **Effort**: S

### CF-6: Snapshot directory served unauthenticated
- **File(s)**: `backend/api/main.py:232-237`
- **Risk**: `app.mount("/snapshots", StaticFiles(...))` serves the entire `snapshots/` directory with no authentication. Any URL like `https://api.vantag.in/snapshots/tenant-a-id/cam-01/uuid.jpg` is publicly accessible — cross-tenant and without login.
- **Recommended fix**: Remove the `StaticFiles` mount; add an authenticated endpoint that verifies `tenant_id` from the JWT matches the path prefix before streaming the file.
- **Effort**: M

---

## High Priority (fix in next sprint)

### HP-1: OTP stored in-process memory (not Redis/DB)
- **File(s)**: `backend/api/auth_router.py:224`
- **Risk**: `_otp_store` is a plain Python dict. On process restart or multi-worker deployment (gunicorn), OTPs are lost and verification always fails. Under load, memory grows unbounded.
- **Recommended fix**: Store OTPs in Redis with a TTL of 10 min: `redis.setex(f"otp:{email}", 600, otp_code)`.
- **Effort**: S

### HP-2: Razorpay webhook has no idempotency protection
- **File(s)**: `backend/api/billing_router.py:100-128`
- **Risk**: The webhook handler records the event in `PaymentEvent` but never checks if `razorpay_event_id` already exists before inserting. A replayed or duplicate webhook will create a duplicate `PaymentEvent` row. Downstream event processing (when wired) will double-credit/double-activate.
- **Recommended fix**: `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` on `razorpay_event_id`. Query for existing event before business-logic execution.
- **Effort**: S

### HP-3: bcrypt is an optional import with an insecure SHA-256 fallback
- **File(s)**: `backend/api/auth_router.py:24-33`
- **Risk**: If `bcrypt` is not installed, passwords are hashed with plain `hashlib.sha256` — trivially brute-forceable. This silently degrades security with no startup warning.
- **Recommended fix**: Require `bcrypt` or `argon2-cffi` in `requirements.txt`. Raise a `RuntimeError` at startup if neither is available. Do not ship a plaintext-equivalent fallback.
- **Effort**: XS

### HP-4: JWT secret falls back to `"change-me"` in two places
- **File(s)**: `backend/config/settings.py:21`, `backend/middleware/tenant_middleware.py:17`
- **Risk**: Both files have `os.getenv("VANTAG_JWT_SECRET", "change-me")` / `"dev-secret-change-in-production"`. A misconfigured production instance with a missing env var will use a known-public fallback, breaking all token security.
- **Recommended fix**: At startup, assert `len(settings.jwt_secret) >= 32` and that it is not a well-known fallback string. Log a CRITICAL warning and refuse to start.
- **Effort**: XS

### HP-5: No rate-limiting or brute-force protection on login at application layer
- **File(s)**: `backend/api/auth_router.py:142-219`
- **Risk**: Nginx rate-limits `/api/auth/` to 10 req/min per IP, but this only applies in the production nginx config and is not enforced for direct backend access or local dev. No lockout after N failed attempts.
- **Recommended fix**: Add a Redis-backed counter: after 5 failed logins for an email, lock for 15 min and return `429`. Use `slowapi` or manual Redis logic.
- **Effort**: S

### HP-6: CORS wildcard `"*"` is the default
- **File(s)**: `backend/api/main.py:88-91`
- **Risk**: If `VANTAG_ALLOWED_ORIGINS` env var is not set, `allow_origins=["*"]` with `allow_credentials=True` is technically a CORS misconfiguration (browsers will reject credentialed requests to `*`, but it signals the lack of hardening and will cause issues).
- **Recommended fix**: Default to `[]` (deny all) or set to the known production domains. Validate at startup that `*` is not used in production (`VANTAG_ENV=production`).
- **Effort**: XS

### HP-7: `/api/cameras` endpoints lack tenant isolation
- **File(s)**: `backend/api/cameras_router.py:148-166, 179-194`
- **Risk**: `GET /api/cameras` and `GET /api/cameras/{camera_id}` fetch from the pipeline's in-memory registry, which is shared across all tenants (loaded from `cameras.yaml`). A tenant A user can view tenant B's camera IDs and stream snapshots.
- **Recommended fix**: Filter camera results by `user["tenant_id"]` from the JWT. The SaaS path should query `CameraConfig` table (which already has `tenant_id`) instead of the pipeline registry.
- **Effort**: M

---

## Medium Priority (nice to have)

### MP-1: No forgot-password / reset-password flow
- **File(s)**: `backend/api/auth_router.py` — no `POST /auth/forgot-password` endpoint exists
- **Risk**: Users who forget their password have no self-service recovery path. Support burden + churn.
- **Recommended fix**: Add `POST /auth/forgot-password` (sends reset link with signed token, 30 min TTL) and `POST /auth/reset-password` (validates token, updates `hashed_password`).
- **Effort**: M

### MP-2: Incident history hard-deleted after 30 days; no configurable retention
- **File(s)**: `backend/api/main.py:163`, `backend/db/incident_store.py:170`
- **Risk**: SQLite store purges all incidents older than 30 days on startup, but plan "growth" advertises 30-day history and "enterprise" advertises unlimited. There's no plan-based retention logic.
- **Recommended fix**: Move incidents to Postgres `DetectionEvent` table (already exists). Apply plan-based retention: `starter=7d`, `growth=30d`, `enterprise=unlimited`.
- **Effort**: M

### MP-3: MQTT broker has no TLS
- **File(s)**: `deploy/mosquitto/mosquitto.conf:1` — `listener 1883`
- **Risk**: MQTT on port 1883 is unencrypted. Camera events (including incident alerts) transit in cleartext on the LAN/network.
- **Recommended fix**: Add `listener 8883` with TLS certificates. Set `cafile`, `certfile`, `keyfile`. Update `MQTTClient` to use `tls_set()`.
- **Effort**: M

### MP-4: `verify_payment_signature` returns `True` when no key is configured
- **File(s)**: `backend/services/razorpay_service.py:74`
- **Risk**: If `RAZORPAY_KEY_SECRET_IN/SG/MY` are not set, both `verify_payment_signature` and `verify_webhook_signature` silently return `True`, accepting any payment/webhook without verification.
- **Recommended fix**: In `verify_payment_signature`, if `key_secret` is empty, raise a `ValueError` (or return `False`) rather than treating it as "test mode passes".
- **Effort**: XS

### MP-5: `Razorpay_plan_ids` are all empty strings
- **File(s)**: `backend/config/plans.py:22-27`
- **Risk**: All `razorpay_plan_ids` are `""`. Subscription recurring billing (if implemented) will silently fail or create one-time orders instead of subscriptions.
- **Recommended fix**: Populate plan IDs from Razorpay dashboard or load from env vars. Add a validation check at startup that warns when they are empty in production.
- **Effort**: S

### MP-6: No structured JSON logging or error tracking
- **File(s)**: `backend/api/main.py:68` — standard Python `logging`, no JSON formatter
- **Risk**: Log parsing, search, and alerting (e.g., in Grafana, CloudWatch, Datadog) require structured logs. Errors in production will be hard to diagnose.
- **Recommended fix**: Configure `python-json-logger` or `structlog` at startup. Add Sentry DSN via `SENTRY_DSN` env var.
- **Effort**: S

### MP-7: Simple edge agent endpoints lack authentication
- **File(s)**: `backend/api/edge_router.py:192-253`
- **Risk**: `POST /api/edge/register` (simple) and `POST /api/edge/heartbeat` (simple) only require a `tenant_id` in the POST body — any party who knows a `tenant_id` (UUIDs, guessable from prior API responses) can register rogue cameras or send fake heartbeats.
- **Recommended fix**: Require at minimum the `onboarding_token` (already generated in `create_tenant`) as a bearer token for these unauthenticated edge paths.
- **Effort**: S

---

## Low Priority / Polish

- **LP-1**: `generate_otp()` uses `random.choices` (`backend/services/email_service.py:41`) — should use `secrets.choice` for cryptographic quality.
- **LP-2**: `cameras_router.py` defines `set_pipeline()` and `_get_pipeline()` twice (lines 51-63 and 857-870) — dead code duplication.
- **LP-3**: Health check endpoint (`GET /health`) returns only uptime/version; does not check DB connectivity, Redis, or MQTT broker status. Add sub-checks.
- **LP-4**: No `Content-Security-Policy` header in nginx config — low risk but good practice for the web frontend.
- **LP-5**: PDF reports (`reports_router.py`) have no tenant-scoping — any authenticated user can list and download reports for any store.
- **LP-6**: `ecosystem.config.js` (PM2 config) present alongside Docker Compose, suggesting inconsistent deployment tooling. Choose one.
- **LP-7**: `yolov8n.pt` is in the repo root AND referenced from `models/` — ensure single source of truth.
- **LP-8**: TypeScript strict mode not confirmed; `(navigation as any)` cast in `usePushNotifications.ts:132`.

---

## Missing Features (user value)

| Feature | Why it Matters | Implementation Sketch |
|---|---|---|
| **Forgot-password flow** | Basic expectation; high churn without it | `POST /auth/forgot-password` → signed token email → `POST /auth/reset-password` with token + new password |
| **Scheduled email reports** | Managers want weekly PDF summaries without logging in | Celery/APScheduler job: cron query incidents → `reportlab` PDF → SMTP send |
| **RBAC (roles: owner, manager, guard)** | Guards should only view alerts, not change settings or billing | Add `role` column to `TenantUser`; `require_role("manager")` guards on settings endpoints |
| **GDPR / data deletion API** | Required for EU-adjacent SG market | `DELETE /api/tenants/me` → anonymise PII in DB, purge snapshots, send confirmation email |
| **GST invoice generation for India** | Legal requirement for B2B customers | Add `gst_number` field to tenant; generate invoices with 18% GST line item in PDF |
| **Cloud snapshot storage (S3/R2)** | Disk fills up on VPS with 30 cameras; snapshots lost on redeploy | Wire `edge_router.py:145` stub to Cloudflare R2 or AWS S3 presigned upload |
| **Video clip export** | Every competitor offers this; customers need evidence for police | On incident creation, save ±30s RTSP clip to object storage; link in incident record |
| **Incident escalation workflow** | Security guard → manager → owner escalation with SLA | Status machine on `DetectionEvent`: `new → acknowledged → escalated → resolved` |
| **Multi-store (location) management** | Enterprise plan promises it; not implemented | `Store` model with `tenant_id`; camera and event filtered by `store_id`; per-store dashboards |
| **WhatsApp/SMS alerts** | Primary channel for Indian/MY retailers (low email literacy) | Twilio or MSG91 integration; add `notification_channel` preference to tenant settings |

---

## Detailed Findings by Area

### 1. Security

**Strengths**: bcrypt with rounds=12 (when available), `secrets.compare_digest` for OTP, HMAC-SHA256 for Razorpay, Mosquitto `allow_anonymous false`, nginx rate limits, TLS 1.2+1.3 in nginx config, HSTS header present.

**Issues**:
- `.env` with production JWT secret committed to repo (CF-1)
- `cameras.yaml` contains plaintext `admin:admin` credentials for three real-IP cameras (CF-2)
- Fallback to SHA-256 password hashing if bcrypt not installed (HP-3)
- JWT secret defaults to `"change-me"` in two places (HP-4)
- Snapshot directory served without auth (CF-6)
- `_DEMO_ACCOUNTS` with hardcoded password `demo1234` in `auth_router.py:127-138` — acceptable for demo but should be gated by `VANTAG_ENV != production`
- SQL injection risk: **None found** — SQLAlchemy ORM used throughout; parameterized queries in SQLite store (line 99 incident_store.py)
- File upload: no file upload endpoints found; base64 snapshot accepted in edge_router — no size cap enforced

### 2. Multi-tenancy Correctness

**Strengths**: `get_current_user_id` / `get_current_tenant_id` used consistently on SaaS DB endpoints; all `tenants_router` queries filter by `user["tenant_id"]`; edge agent verified by `agent.tenant_id`.

**Issues**:
- WebSocket endpoints have no authentication — all tenants share the same broadcast (CF-3, HP-7)
- `GET /api/cameras` and `GET /api/cameras/{id}` read from shared in-memory pipeline registry, not tenant-scoped DB (HP-7)
- `GET /api/stores` and `GET /api/stores/{store_id}/incidents` also read from pipeline `recent_events` dict, not tenant-scoped — in multi-tenant SaaS mode, one tenant could see another's live events
- MQTT topics (`vantag/events/{store_id}`) use store_id derived from location names, not tenant_id — potential collision if two tenants name a store identically
- Snapshot URLs are `/snapshots/{tenant_id}/{camera_id}/{uuid}.jpg` — well-structured, but served without auth check (CF-6)

### 3. Payment Integrity

**Strengths**: `verify_webhook_signature` uses `hmac.compare_digest` (timing-safe); currency is derived from tenant's country, not client input; invoice created at order time; `billing_router` checks tenant ownership before creating orders.

**Issues**:
- Webhook idempotency missing (HP-2) — `razorpay_event_id` not checked for duplicates before insert
- Onboarding step 3 payment bypass: no signature verification if `razorpay_payment_id` is falsy (CF-4)
- Webhook processing is fire-and-forget — events logged to `PaymentEvent` but `processed=False` forever; no background worker processes them
- `verify_payment_signature` / `verify_webhook_signature` return `True` when keys not configured (MP-4)
- Grace period for failed payments: not implemented; no `payment.failed` handler wired
- `razorpay_plan_ids` all empty — subscription auto-renewal will not work (MP-5)

### 4. AI / Inference Reliability

**Strengths**: `YOLOEngine._load_model()` gracefully degrades on missing file or missing `ultralytics` package; `detect()` falls back from `track()` to `predict()` on tracker failure; returns `[]` on errors (never crashes); ByteTrack tracking provides temporal smoothing; `model.to(device)` warms up on load.

**Issues**:
- `yolo_conf_threshold: 0.25` in `cameras.yaml:9` is very low; at 0.25 confidence, high false-positive rate is expected for shoplifting/fall detection
- No GPU auto-detection: `yolo_device: cpu` hardcoded in YAML; backend could check `torch.cuda.is_available()` at startup
- Analyzers run synchronously in the pipeline loop — no per-camera thread isolation confirmed (one slow camera potentially blocks others; need to verify `model_scheduler.py`)
- No model warm-up inference call on startup (only `model.to(device)` — first inference will be slow)
- TRT engine (`trt_engine.py`) exists but not wired into the main pipeline by default

### 5. Edge Agent Architecture

**Strengths**: API key authentication for the "real" edge agent endpoints; `_verify_agent` looks up key in DB; heartbeat updates camera status in DB; config polling endpoint present.

**Issues**:
- Duplicate route conflict: two `POST /api/edge/register` in same router (CF-5)
- Unauthenticated simple endpoints accept arbitrary `tenant_id` (MP-7)
- `vantag_agent.py` is a minimal Python script; no auto-update mechanism, no offline queue, no CPU/memory limits
- Agent scans network synchronously (blocking, 254 × 0.3s = ~75s)
- Snapshot base64 from edge is not actually saved to disk (`edge_router.py:145`) — URL is computed but file is never written
- No Windows/Linux installer; just a raw Python script requiring manual `pip install requests`

### 6. Observability / Ops

**Strengths**: Docker Compose files per region; nginx with access logging; backup script (`backup.sh`) uses `pg_dump | gzip`, retains 30 days; Mosquitto persistence enabled.

**Issues**:
- Standard Python `logging` only; no JSON formatter, no Sentry, no Prometheus metrics (MP-6)
- Health check returns only version/uptime, not DB/Redis/MQTT status (LP-3)
- No log rotation configured for application logs
- Backup script runs on-demand only — no cron wiring shown
- No disaster recovery plan or secondary DB replica
- `ecosystem.config.js` (PM2) conflicts with Docker Compose approach — deployment tooling unclear

### 7. UX / Onboarding Gaps

**Strengths**: 5-step onboarding wizard with DB persistence and resumability; email OTP with 10-min TTL; `secrets.compare_digest` for OTP; `is_dev_mode()` check prevents OTP exposure in production; trial period and plan gating.

**Issues**:
- No forgot-password flow (MP-1) — biggest UX gap
- No session timeout / auto-logout logic in frontend or backend
- No `/api/auth/refresh-token` endpoint despite `refresh_token` being issued — token refresh not implemented
- Email templates are English-only (not using i18n); `send_verification_email` hardcodes English strings
- Unsubscribe link in email footer is a dead `#` link

### 8. Business Logic Gaps

- Incident retention hard-coded to 30 days regardless of plan (MP-2)
- No RBAC beyond `owner/admin` — no `manager`, `guard` roles (Missing Features)
- No scheduled reports (Missing Features)
- `invoice_number` uses random hex, not a sequential/formatted number (e.g., `INV-2026-0001`)
- No GST tax line item on invoices for India (Missing Features)
- No GDPR deletion endpoint (Missing Features)
- Audit log: no `AuditLog` table — no record of "who changed what, when"
- Notification preferences: only email configurable; no push/SMS/WhatsApp (Missing Features)

### 9. Internationalization Completeness

**Strengths**: 12 locale files loaded (`en`, `hi`, `ta`, `te`, `kn`, `ml`, `mr`, `gu`, `bn`, `pa`, `ms`, `zh`); `fallbackLng: 'en'`; language selector component present; `LanguageSelector.tsx` exists.

**Issues**:
- Email templates (`email_service.py`) are English-only — verification OTP, trial expiry, payment success are not translated
- No RTL support for languages that may need it (none of the current 12 require RTL, but Arabic/Urdu expansion would break layout)
- Date/currency formatting: regions.py defines symbols (`₹`, `S$`, `RM`) but frontend i18n does not appear to use `Intl.NumberFormat` with locale
- Language preference stored in DB but the i18n `lng` at init time uses `'en'` by default — requires frontend to read `language` from login response and call `i18n.changeLanguage()`

### 10. Developer Experience / Code Quality

**Strengths**: Good docstrings on most modules; Pydantic models for all request/response; `from __future__ import annotations`; pytest test suite covers 5 key areas (analyzers, risk scorer, webhooks, POS); Docker Compose for dev.

**Issues**:
- No CI/CD pipeline (no `.github/workflows/`, no `Jenkinsfile`)
- No Alembic migrations — `init_db()` uses `create_all`, which is dev-only and will silently fail if schema already exists
- Blanket `except Exception` catches throughout (`BLE001` noqa markers) mask real bugs
- `cameras_router.py:855-870` duplicates `set_pipeline()`/`_get_pipeline()` (also at lines 51-63)
- Test coverage: 4 backend test files, 2 e2e — authentication, billing, edge, multi-tenancy have zero test coverage
- TypeScript: `(navigation as any)` casts indicate type escaping; no evidence of `strict: true` in tsconfig

### 11. Performance

**Strengths**: `asyncpg` for async Postgres; connection pool (size=10, overflow=20); SQLAlchemy ORM avoids raw SQL injection; nginx gzip enabled; WebSocket connection manager deduplicates store broadcasts.

**Issues**:
- `pipeline.recent_events` is an in-memory dict — at 100 cameras × 100 events each, this grows unbounded; no eviction policy visible
- Snapshot serving via `StaticFiles` serves full-res JPEGs without thumbnail generation — high bandwidth for mobile clients
- No Redis caching of hot-path DB queries (e.g., `/api/tenants/me`)
- N+1 risk: `tenants_router.get_my_cameras()` queries all cameras per request; no pagination
- WebSocket: global broadcast sends every event to every connected client — at 100 cameras × 30fps, this is untenable; should use per-tenant rooms
- Frontend bundle: no evidence of code splitting or lazy loading beyond Vite defaults
- `scan_cameras()` in edge agent: 254 sequential socket calls in Python (not asyncio) takes ~75s

### 12. Competitive / Feature Gaps

Vantag differentiates well on **price** (vs. Verkada at $300+/camera/year) and **local-language support**. Missing versus top competitors:

| Feature | Verkada | Rhombus | Vantag | Gap |
|---|---|---|---|---|
| Cloud-stored video | ✓ | ✓ | ✗ | High — needed for evidence |
| AI video search | ✓ | ✓ | ✗ | High |
| Scheduled PDF reports | ✓ | ✓ | ✗ | Medium |
| Mobile biometric login | ✓ | ✓ | ✗ | Medium |
| Incident escalation workflow | ✓ | ✓ | ✗ | Medium |
| Multi-site management | ✓ | ✓ | Partial | Medium |
| WhatsApp alerts | ✗ | ✗ | ✗ | High for India/MY market |
| POS integration (sweethearting) | Partial | ✗ | ✓ | **Vantag advantage** |
| Edge-only / offline mode | ✗ | ✗ | Partial | Medium |

### 13. Mobile App

**Strengths**: Expo push notifications with FCM channel setup; deep linking from notification tap to specific store or alerts screen; WebSocket hook for real-time events; Zustand state management; region-aware backend URL.

**Issues**:
- No biometric login (`expo-local-authentication` not referenced)
- No offline mode — `useMobileStore` does not persist to AsyncStorage
- Camera feed on mobile uses MJPEG stream — very bandwidth-heavy; no adaptive quality or HLS alternative
- `axios.post` to `/api/devices/register` is fire-and-forget with silent failure — device tokens may not be registered
- No APNs configuration visible (only Android channel setup) — iOS notifications may not work

---

## Recommended Roadmap

### Week 1 (Critical Security + Blockers)
- [ ] Rotate JWT secret, add to `.gitignore`, purge from git history (`git filter-repo`)
- [ ] Remove RTSP credentials from `cameras.yaml`; add to `.gitignore`
- [ ] Add JWT authentication to all WebSocket endpoints (CF-3)
- [ ] Fix duplicate route in `edge_router.py`; add `tenant_id` validation to simple endpoints (CF-5, MP-7)
- [ ] Gate `StaticFiles` snapshot mount behind auth middleware (CF-6)
- [ ] Make bcrypt a hard requirement; remove SHA-256 fallback (HP-3)
- [ ] Assert JWT secret is non-default at startup (HP-4)

### Week 2 (Payment + Core UX)
- [ ] Add idempotency check to webhook handler using `razorpay_event_id` (HP-2)
- [ ] Fix onboarding step 3 payment bypass (CF-4)
- [ ] Make `verify_payment_signature` return `False` when key not configured (MP-4)
- [ ] Move OTP store to Redis with TTL (HP-1)
- [ ] Implement forgot-password email + reset endpoint (MP-1)
- [ ] Add login brute-force protection (HP-5)

### Month 2 (Operational Quality)
- [ ] Add Sentry error tracking + structured JSON logging
- [ ] Wire Alembic for database migrations
- [ ] Implement per-plan incident retention in Postgres (MP-2)
- [ ] Add GDPR deletion endpoint
- [ ] Configure MQTT TLS (MP-3)
- [ ] Add CI/CD pipeline (GitHub Actions: lint → test → docker build → deploy)
- [ ] Add health check sub-checks for DB/Redis/MQTT
- [ ] Implement token refresh endpoint
- [ ] Multi-store model for enterprise plan

### Quarter 2 (Feature Parity + Growth)
- [ ] Cloud video clip storage (Cloudflare R2 / AWS S3) for evidence
- [ ] Scheduled weekly email reports
- [ ] WhatsApp/SMS alerts via Twilio/MSG91
- [ ] RBAC (manager, guard roles)
- [ ] GST invoice generation for India
- [ ] Mobile: biometric login, offline mode with AsyncStorage
- [ ] AI confidence threshold auto-tuning per camera

---

## Strengths

1. **Architecture is clean and well-layered**: Backend (FastAPI) → Middleware (JWT) → Services → DB → Analyzers separation is clear and well-documented.
2. **YOLO inference pipeline is production-grade**: ByteTrack tracking, graceful fallback on model load failure, per-camera configuration, 14 specialized analyzers.
3. **Excellent onboarding UX**: 5-step wizard with DB persistence, resumability, QR code for edge agent, and plan-gating on camera count.
4. **Multi-region payment architecture**: INR/SGD/MYR currency routing, per-region Razorpay key isolation, HMAC signature verification.
5. **Good i18n foundation**: 12 locale files loaded at startup, fallback chain, language stored per tenant.
6. **Test suite for core analyzers**: DwellTime, Queue, RiskScorer, Webhook, POS tests provide confidence in ML logic.
7. **Docker Compose per region**: Clean separation of India/SG/MY deployments.
8. **POS sweethearting detection** is a genuine competitive differentiator not found in mainstream competitors.
9. **Push notifications with deep linking** are fully wired in mobile (Expo + FCM).
10. **Nginx config** has HSTS, rate limits, TLS 1.2/1.3, and correct WebSocket upgrade headers.
