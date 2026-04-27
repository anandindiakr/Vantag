"""
backend/db/migrations/001_payment_event_idempotency.sql
=======================================================
Ensures the ``payment_events.razorpay_event_id`` column has a unique index
for webhook idempotency.

This migration is safe to run multiple times (IF NOT EXISTS).

Run via psql:
    psql $POSTGRES_URL -f backend/db/migrations/001_payment_event_idempotency.sql

Or execute programmatically on startup (see database.py apply_migrations()).
"""

-- Ensure the column exists (backwards-compat for older schemas)
ALTER TABLE payment_events
    ADD COLUMN IF NOT EXISTS razorpay_event_id VARCHAR(200);

-- Create unique index (idempotency key)
CREATE UNIQUE INDEX IF NOT EXISTS ix_payment_events_razorpay_event_id
    ON payment_events (razorpay_event_id)
    WHERE razorpay_event_id IS NOT NULL;
