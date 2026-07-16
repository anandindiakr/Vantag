-- Migration: add alert_settings column to tenants table
-- Stores per-tenant Alert Dispatch config (SMS/WhatsApp via Twilio, Email).
-- Run ONCE on the VPS Postgres database.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name = 'tenants'
        AND    column_name = 'alert_settings'
    ) THEN
        ALTER TABLE tenants
            ADD COLUMN alert_settings JSONB;
        RAISE NOTICE 'tenants.alert_settings column added.';
    ELSE
        RAISE NOTICE 'tenants.alert_settings already exists.';
    END IF;
END;
$$;
