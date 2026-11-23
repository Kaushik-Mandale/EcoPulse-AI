-- Municipal IAM controls. Apply explicitly after taking the required backup.
-- Citizen accounts retain their existing OTP-verified access. Legacy municipal
-- staff remain active in the database but are held unverified until individually
-- approved through 007_municipal_iam_legacy_verification.sql.

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS mfa_secret_enc VARCHAR(512),
    ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS mfa_last_verified_step BIGINT,
    ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS account_status VARCHAR(30) NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS vehicle_assignment VARCHAR(100),
    ADD COLUMN IF NOT EXISTS created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS approved_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS mfa_enrolled_at TIMESTAMPTZ;

-- is_active is nullable in the legacy schema, so treat NULL as active to keep
-- this backfill compatible with the NOT NULL constraint on account_status.
UPDATE users
SET account_status = CASE WHEN is_active IS FALSE THEN 'suspended' ELSE 'active' END
WHERE account_status IS NULL OR account_status = ''
   OR (account_status = 'active' AND is_active IS FALSE);

UPDATE users
SET is_verified = TRUE
WHERE role = 'citizen';

-- Legacy municipal staff are never trusted implicitly. Every staff row without a
-- recorded approval timestamp is held unverified; rows approved by
-- 007_municipal_iam_legacy_verification.sql keep their verification on re-run.
UPDATE users
SET is_verified = FALSE,
    verified_at = NULL
WHERE role IN ('driver', 'admin', 'collector')
  AND verified_at IS NULL;

ALTER TABLE users ALTER COLUMN eco_coins SET DEFAULT 0;

CREATE TABLE IF NOT EXISTS account_invitations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    approved_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_account_invitations_user_id ON account_invitations(user_id);

CREATE TABLE IF NOT EXISTS security_audit_events (
    id SERIAL PRIMARY KEY,
    actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    target_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor_employee_id VARCHAR(50),
    target_employee_id VARCHAR(50),
    action VARCHAR(80) NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_security_audit_events_actor_id ON security_audit_events(actor_id);
CREATE INDEX IF NOT EXISTS ix_security_audit_events_target_user_id ON security_audit_events(target_user_id);
CREATE INDEX IF NOT EXISTS ix_security_audit_events_action ON security_audit_events(action);
CREATE INDEX IF NOT EXISTS ix_security_audit_events_created_at ON security_audit_events(created_at);

COMMIT;
