-- Refuse rollback if provisioning data or a rotation requirement would be lost.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM users
        WHERE login_id IS NOT NULL AND login_id <> ''
    ) OR EXISTS (
        SELECT 1 FROM users WHERE must_change_password IS TRUE
    ) THEN
        RAISE EXCEPTION 'Cannot downgrade 009 while a login ID or forced password rotation is in use';
    END IF;
END $$;

DROP INDEX IF EXISTS uq_users_single_super_admin;
DROP INDEX IF EXISTS uq_users_login_id;
ALTER TABLE users DROP COLUMN IF EXISTS must_change_password;
ALTER TABLE users DROP COLUMN IF EXISTS login_id;

COMMIT;
