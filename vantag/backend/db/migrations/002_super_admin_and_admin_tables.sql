-- Migration: 002_super_admin_and_admin_tables.sql
-- Run this against your PostgreSQL database.
--
-- 1. Add is_super_admin column to tenant_users
ALTER TABLE tenant_users
  ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Add deleted_at column to tenants (for soft-delete)
ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- 3. Create system_alerts table
CREATE TABLE IF NOT EXISTS system_alerts (
    id              VARCHAR(36)   PRIMARY KEY,
    level           VARCHAR(20)   NOT NULL,  -- info / warning / critical
    title           VARCHAR(200)  NOT NULL,
    detail          TEXT,
    source          VARCHAR(100),
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ
);

-- 4. Create admin_audit_log table
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id              VARCHAR(36)   PRIMARY KEY,
    admin_user_id   VARCHAR(36)   NOT NULL,
    admin_email     VARCHAR(200),
    action          VARCHAR(100)  NOT NULL,
    target_type     VARCHAR(50),
    target_id       VARCHAR(36),
    detail          TEXT,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- 5. Index for faster alert queries
CREATE INDEX IF NOT EXISTS idx_system_alerts_acknowledged
    ON system_alerts (acknowledged_at)
    WHERE acknowledged_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_created
    ON admin_audit_log (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_tenants_deleted_at
    ON tenants (deleted_at)
    WHERE deleted_at IS NULL;

-- ── HOW TO CREATE YOUR FIRST SUPER-ADMIN ────────────────────────────────────
--
-- After running this migration, mark your account as super-admin:
--
--   UPDATE tenant_users
--      SET is_super_admin = TRUE
--    WHERE email = 'anandindiakr@gmail.com';
--
-- Then log in via the normal /login endpoint — the JWT will contain
-- is_super_admin=true and the Admin Panel link will appear in the sidebar.
-- ────────────────────────────────────────────────────────────────────────────
