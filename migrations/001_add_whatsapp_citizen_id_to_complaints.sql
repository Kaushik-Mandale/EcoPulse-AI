-- ============================================================================
-- Migration: 001_add_whatsapp_citizen_id_to_complaints.sql
-- Description: Adds nullable foreign key column `whatsapp_citizen_id` and index
--              to `complaints` table to support WhatsApp citizen relationship.
-- Target DB:   PostgreSQL 11+ (Neon)
-- Safety:      Metadata-only update (O(1)). Non-blocking on PostgreSQL 11+.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Forward Migration (Apply)
-- ----------------------------------------------------------------------------
BEGIN;

-- Add column with foreign key constraint (nullable, on delete set null)
ALTER TABLE complaints
ADD COLUMN IF NOT EXISTS whatsapp_citizen_id INTEGER
REFERENCES whatsapp_citizens(id) ON DELETE SET NULL;

-- Create index for foreign key performance
CREATE INDEX IF NOT EXISTS ix_complaints_whatsapp_citizen_id
ON complaints (whatsapp_citizen_id);

COMMIT;

-- ----------------------------------------------------------------------------
-- 2. Verification Query
-- ----------------------------------------------------------------------------
-- Run this query after migration to verify column and index presence:
--
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'complaints' AND column_name = 'whatsapp_citizen_id';
--
-- Expected result:
-- column_name          | data_type | is_nullable
-- ---------------------+-----------+------------
-- whatsapp_citizen_id  | integer   | YES
--
-- Verify index:
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'complaints' AND indexname = 'ix_complaints_whatsapp_citizen_id';

-- ----------------------------------------------------------------------------
-- 3. Rollback Query (Revert)
-- ----------------------------------------------------------------------------
-- WARNING: Executing rollback will drop the column and all associated data.
-- Only execute if a roll-back of the feature is explicitly required.
--
-- BEGIN;
-- DROP INDEX IF EXISTS ix_complaints_whatsapp_citizen_id;
-- ALTER TABLE complaints DROP COLUMN IF EXISTS whatsapp_citizen_id;
-- COMMIT;
