-- ============================================================================
-- Migration: 002_add_tracking_secret_to_complaints.sql
-- Description: Adds nullable column `tracking_secret` to `complaints` table
--              for optional explicit persistent tracking secrets.
-- Target DB:   PostgreSQL 11+ (Neon)
-- Safety:      Metadata-only update (O(1)). Non-blocking on PostgreSQL 11+.
-- Note:        The backend supports cryptographic HMAC tracking tokens out of
--              the box without requiring this migration to be run immediately.
--              Do not apply without review/approval.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Forward Migration (Apply)
-- ----------------------------------------------------------------------------
BEGIN;

-- Add column for optional explicit persistent tracking secrets
ALTER TABLE complaints
ADD COLUMN IF NOT EXISTS tracking_secret VARCHAR(64);

-- Optional index if lookups by tracking_secret are needed
CREATE INDEX IF NOT EXISTS ix_complaints_tracking_secret
ON complaints (tracking_secret);

COMMIT;

-- ----------------------------------------------------------------------------
-- 2. Verification Query
-- ----------------------------------------------------------------------------
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'complaints' AND column_name = 'tracking_secret';

-- ----------------------------------------------------------------------------
-- 3. Rollback Query (Revert)
-- ----------------------------------------------------------------------------
-- BEGIN;
-- DROP INDEX IF EXISTS ix_complaints_tracking_secret;
-- ALTER TABLE complaints DROP COLUMN IF EXISTS tracking_secret;
-- COMMIT;
