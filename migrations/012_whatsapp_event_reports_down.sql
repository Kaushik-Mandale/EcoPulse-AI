-- Refuse to drop event_reports table if citizen event reports exist to prevent silent data loss.
BEGIN;

DO $$
DECLARE
    has_reports BOOLEAN := FALSE;
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = current_schema() 
          AND table_name = 'event_reports'
    ) THEN
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM event_reports)' INTO has_reports;
        IF has_reports THEN
            RAISE EXCEPTION 'Cannot downgrade 012 while event reports exist in event_reports table';
        END IF;
    END IF;
END $$;

DROP INDEX IF EXISTS ix_event_reports_whatsapp_citizen_id;
DROP INDEX IF EXISTS ix_event_reports_citizen_id;
DROP INDEX IF EXISTS ix_event_reports_reference_id;
DROP TABLE IF EXISTS event_reports CASCADE;

COMMIT;
