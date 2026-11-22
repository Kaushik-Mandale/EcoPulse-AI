-- Secure one-time Super Admin bootstrap identity and forced first-login rotation.
-- Existing municipal employee IDs remain unchanged and continue to be checked
-- against MUNICIPAL_EMPLOYEE_ALLOWLIST by the bootstrap utility.
BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS login_id VARCHAR(50),
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_login_id
    ON users (login_id)
    WHERE login_id IS NOT NULL AND login_id <> '';

-- A partial unique index on the boolean true value serializes concurrent
-- provisioning and prevents more than one Super Admin account.
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_single_super_admin
    ON users (is_super_admin)
    WHERE is_super_admin;

COMMIT;
