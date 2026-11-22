-- Expire unrotated staff credentials after a short onboarding window.
BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS temporary_password_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS mfa_enrollment_expires_at TIMESTAMPTZ;

COMMIT;
