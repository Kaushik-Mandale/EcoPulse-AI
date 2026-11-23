-- Refuse to drop wards and municipalities if event_reports table still exists (dependency on 012)
BEGIN;

-- 1. Dependency check: migration 012 must be rolled back prior to migration 011
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = current_schema() 
          AND table_name = 'event_reports'
    ) THEN
        RAISE EXCEPTION 'Cannot downgrade 011 while event_reports (migration 012) is still present. Roll back 012 first.';
    END IF;
END $$;

-- 2. Preserve string representation in users.ward before dropping ward_id column
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'users' AND column_name = 'ward_id'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'wards'
    ) THEN
        EXECUTE 'UPDATE users u SET ward = w.display_name FROM wards w WHERE u.ward_id = w.id';
    END IF;
END $$;

-- 3. Drop columns and foreign key indexes from users
DROP INDEX IF EXISTS ix_users_ward_id;
DROP INDEX IF EXISTS ix_users_municipality_id;
ALTER TABLE users DROP COLUMN IF EXISTS ward_id;
ALTER TABLE users DROP COLUMN IF EXISTS municipality_id;

-- 4. Drop wards and municipalities in reverse dependency order
DROP TABLE IF EXISTS wards CASCADE;
DROP TABLE IF EXISTS municipalities CASCADE;

COMMIT;
