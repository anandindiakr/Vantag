# Changelog

All notable changes to the Vantag / Nazar Retail AI platform are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-06-22

### Pricing — new 4-tier structure

The old 3-tier line-up (`Starter` / `Growth` / `Enterprise`) has been replaced
with a 4-tier structure that adds a clearer mid/upper split (`Pro` and
`Pro Plus`) and a lower entry price.

| Tier | Cameras | India (₹/mo) | Singapore (S$/mo) | Malaysia (RM/mo) |
|------|---------|--------------|-------------------|------------------|
| **Starter**  | 4  | 1,999  | 39  | 59  |
| **Growth**   | 10 | 4,999  | 99  | 149 |
| **Pro**      | 20 | 9,500  | 189 | 299 |
| **Pro Plus** | 30 | 15,000 | 289 | 449 |

- Entry price lowered: **Starter ₹2,999 → ₹1,999** (S$49 → S$39, RM149 → RM59),
  now capped at **4 cameras**.
- `Enterprise` is removed and superseded by **Pro** (20 cams) and
  **Pro Plus** (30 cams), giving customers a defined upgrade path instead of a
  custom-quote tier.
- Plan IDs are now consistent across frontend and backend:
  `starter` / `growth` / `pro` / `proplus`.

### Trial — shortened from 14 days to 3 days

- New sign-ups now get a **3-day free trial** (was 14 days). No credit card
  required, unchanged.
- Applies across onboarding, registration, dashboard, and all locale strings.

### Changed
- `backend/config/plans.py` — rebuilt with the 4 tiers above, per-region
  pricing, placeholder Razorpay plan IDs, and `trial_days: 3` on every tier.
- `backend/api/onboarding_router.py` — trial window `timedelta(days=14)` →
  `timedelta(days=3)`.
- `backend/services/tenant_service.py` — default trial fallback `14` → `3`.
- `frontend/web/src/pages/onboarding/Onboarding.tsx` — `PLANS` updated to the
  new tiers, camera counts and prices.
- `frontend/web/src/config/regions.ts` — plan type union now
  `starter | growth | pro | proplus`.
- `frontend/web/src/pages/AccountPage.tsx` — `planLabel` map updated to the new
  plan IDs (removed stale `basic` / `enterprise`).
- `frontend/web/src/pages/auth/Register.tsx` — trial copy "14-day" → "3-day".
- `frontend/web/src/i18n/locales/en.json` — trial strings "14-day" → "3-day".

### Migration
- Added `backend/scripts/migrate_trial_14_to_3.py` to re-base existing
  active-trial tenants onto the 3-day schedule
  (`trial_ends_at = created_at + 3 days`). Dry-run by default; pass `--commit`
  to apply. Idempotent — skips tenants already on the 3-day window and never
  changes `status`.

### Action required (ops)
- **Fill in Razorpay plan IDs** in `backend/config/plans.py`
  (`razorpay_plan_ids` is empty for every tier) before enabling live billing.
- Run the trial migration on each regional database:
  ```bash
  # preview
  python -m backend.scripts.migrate_trial_14_to_3
  # apply
  python -m backend.scripts.migrate_trial_14_to_3 --commit
  ```

### Notes
- Legal / Terms references to "14 days" were intentionally left unchanged — they
  refer to notice periods, not the trial duration.
