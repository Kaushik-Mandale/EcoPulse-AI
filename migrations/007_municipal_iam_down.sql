-- Reversal for migrations/007_municipal_iam.sql.
-- DESTRUCTIVE: permanently drops security_audit_events and account_invitations,
-- including legacy verification approvals, and removes every IAM column from
-- users (invalidating session_version-based revocation). Stop the application
-- and export any records that must be retained before running this file.

BEGIN;

ALTER TABLE users ALTER COLUMN eco_coins SET DEFAULT 100;

DROP TABLE IF EXISTS security_audit_events;
DROP TABLE IF EXISTS account_invitations;

ALTER TABLE users
    DROP COLUMN IF EXISTS mfa_enrolled_at,
    DROP COLUMN IF EXISTS deactivated_at,
    DROP COLUMN IF EXISTS suspended_at,
    DROP COLUMN IF EXISTS activated_at,
    DROP COLUMN IF EXISTS verified_at,
    DROP COLUMN IF EXISTS approved_by_id,
    DROP COLUMN IF EXISTS created_by_id,
    DROP COLUMN IF EXISTS vehicle_assignment,
    DROP COLUMN IF EXISTS account_status,
    DROP COLUMN IF EXISTS session_version,
    DROP COLUMN IF EXISTS mfa_last_verified_step,
    DROP COLUMN IF EXISTS mfa_enabled,
    DROP COLUMN IF EXISTS mfa_secret_enc,
    DROP COLUMN IF EXISTS is_super_admin,
    DROP COLUMN IF EXISTS is_verified;

COMMIT;
