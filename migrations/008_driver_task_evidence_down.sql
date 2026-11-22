-- Destructive rollback: removes collection evidence and its audit history.
BEGIN;
DROP TABLE IF EXISTS task_events;
DROP TABLE IF EXISTS task_evidence;
COMMIT;
