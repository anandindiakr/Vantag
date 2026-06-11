-- Migration: add network_settings column to tenants table
-- Also adds analyzer_config column to camera_configs table.
-- Run ONCE on the VPS Postgres database.

DO $$
BEGIN
    -- tenants.network_settings
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name = 'tenants'
        AND    column_name = 'network_settings'
    ) THEN
        ALTER TABLE tenants
            ADD COLUMN network_settings JSONB;
        RAISE NOTICE 'tenants.network_settings column added.';
    ELSE
        RAISE NOTICE 'tenants.network_settings already exists.';
    END IF;

    -- camera_configs.analyzer_config
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name = 'camera_configs'
        AND    column_name = 'analyzer_config'
    ) THEN
        ALTER TABLE camera_configs
            ADD COLUMN analyzer_config JSONB;
        RAISE NOTICE 'camera_configs.analyzer_config column added.';
    ELSE
        RAISE NOTICE 'camera_configs.analyzer_config already exists.';
    END IF;
END;
$$;
