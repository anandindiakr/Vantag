ALTER TABLE tenant_users ADD COLUMN IF NOT EXISTS refresh_token_hash VARCHAR(128);
ALTER TABLE tenant_users ADD COLUMN IF NOT EXISTS refresh_token_expires_at TIMESTAMPTZ;
