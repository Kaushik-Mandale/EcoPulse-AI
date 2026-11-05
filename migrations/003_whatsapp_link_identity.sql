-- ============================================================================
-- Migration: 003_whatsapp_link_identity.sql
-- Description: Adds secure citizen identity linking:
--              1. user_id FK on whatsapp_citizens (nullable, unique)
--              2. whatsapp_link_tokens table for one-time secure linking
-- Target DB:   PostgreSQL 11+ (Neon)
-- Safety:      All changes are additive (no existing data deleted or modified)
-- Idempotent:  Uses IF NOT EXISTS / IF NOT EXISTS patterns throughout
-- ============================================================================

BEGIN;

-- ============================================================================
-- PART 1: Extend whatsapp_citizens with canonical user identity
-- ============================================================================

-- 1a. Add nullable user_id FK column (existing rows remain with NULL = unlinked)
ALTER TABLE whatsapp_citizens
    ADD COLUMN IF NOT EXISTS user_id INTEGER
    REFERENCES users(id) ON DELETE SET NULL;

-- 1b. Index for FK join performance
CREATE INDEX IF NOT EXISTS ix_whatsapp_citizens_user_id
    ON whatsapp_citizens (user_id);

-- 1c. Unique constraint: one website account ↔ at most one WhatsApp identity.
--     Partial unique index (excludes NULL rows so unlinked citizens don't conflict).
CREATE UNIQUE INDEX IF NOT EXISTS uq_whatsapp_citizens_user_id_notnull
    ON whatsapp_citizens (user_id)
    WHERE user_id IS NOT NULL;

-- 1d. Update default name from 'Shirpur Resident' to 'Dhule Citizen'
--     for future INSERT statements (existing rows unchanged).
ALTER TABLE whatsapp_citizens
    ALTER COLUMN full_name SET DEFAULT 'Dhule Citizen';

-- ============================================================================
-- PART 2: Create whatsapp_link_tokens table
-- ============================================================================

CREATE TABLE IF NOT EXISTS whatsapp_link_tokens (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      VARCHAR(64) NOT NULL,         -- SHA-256 hex of plaintext code
    expires_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_at     TIMESTAMP WITH TIME ZONE,     -- NULL = not yet redeemed
    whatsapp_phone  VARCHAR(30),                  -- set when redeemed
    attempt_count   INTEGER NOT NULL DEFAULT 0,   -- failed redemption attempts
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Index for fast token lookup by hash during webhook processing
CREATE INDEX IF NOT EXISTS ix_whatsapp_link_tokens_token_hash
    ON whatsapp_link_tokens (token_hash);

-- Index for fast lookup of active tokens per user
CREATE INDEX IF NOT EXISTS ix_whatsapp_link_tokens_user_id
    ON whatsapp_link_tokens (user_id);

COMMIT;

-- ============================================================================
-- Verification queries (run after migration to confirm success):
-- ============================================================================
--
-- Check user_id column on whatsapp_citizens:
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'whatsapp_citizens' AND column_name = 'user_id';
--
-- Check whatsapp_link_tokens table:
-- SELECT table_name FROM information_schema.tables
-- WHERE table_name = 'whatsapp_link_tokens';
--
-- Check partial unique index:
-- SELECT indexname, indexdef FROM pg_indexes
-- WHERE tablename = 'whatsapp_citizens'
--   AND indexname = 'uq_whatsapp_citizens_user_id_notnull';

-- ============================================================================
-- Rollback (only if explicit revert is required):
-- ============================================================================
-- BEGIN;
-- DROP TABLE IF EXISTS whatsapp_link_tokens;
-- DROP INDEX IF EXISTS ix_whatsapp_citizens_user_id;
-- DROP INDEX IF EXISTS uq_whatsapp_citizens_user_id_notnull;
-- ALTER TABLE whatsapp_citizens DROP COLUMN IF EXISTS user_id;
-- COMMIT;

