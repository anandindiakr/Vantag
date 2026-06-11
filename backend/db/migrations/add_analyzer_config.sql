-- Migration: add analyzer_config column to camera_configs table
-- Run this ONCE on the VPS Postgres DB.
-- It is safe to run again (IF NOT EXISTS guard).

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name = 'camera_configs'
        AND    column_name = 'analyzer_config'
    ) THEN
        ALTER TABLE camera_configs
            ADD COLUMN analyzer_config JSONB;
        RAISE NOTICE 'analyzer_config column added.';
    ELSE
        RAISE NOTICE 'analyzer_config column already exists — skipping.';
    END IF;
END;
$$;
