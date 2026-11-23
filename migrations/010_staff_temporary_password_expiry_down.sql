-- Refuse to remove expiry enforcement while any account still needs rotation.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM users
        WHERE must_change_password IS TRUE
          AND temporary_password_expires_at IS NOT NULL
    ) OR EXISTS (
        SELECT 1 FROM users WHERE mfa_enrollment_expires_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Cannot downgrade 010 while a temporary credential or MFA enrollment is active';
    END IF;
END $$;

ALTER TABLE users
    DROP COLUMN IF EXISTS mfa_enrollment_expires_at,
    DROP COLUMN IF EXISTS temporary_password_expires_at;

COMMIT;
