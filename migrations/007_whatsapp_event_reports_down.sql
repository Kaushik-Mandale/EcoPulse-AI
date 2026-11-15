-- Revert migration 007_whatsapp_event_reports.sql

BEGIN;

DROP TABLE IF EXISTS event_reports CASCADE;

COMMIT;
