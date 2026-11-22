BEGIN;

CREATE TABLE IF NOT EXISTS task_evidence (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
    complaint_id INTEGER NOT NULL REFERENCES complaints(id) ON DELETE RESTRICT,
    driver_id INTEGER NOT NULL REFERENCES users(id),
    before_image_ref VARCHAR(512),
    after_image_ref VARCHAR(512) NOT NULL,
    collection_notes TEXT,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','pending','approved','rejected')),
    reviewed_by_id INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_task_evidence_task_id ON task_evidence(task_id);
CREATE INDEX IF NOT EXISTS ix_task_evidence_complaint_id ON task_evidence(complaint_id);
CREATE INDEX IF NOT EXISTS ix_task_evidence_driver_id ON task_evidence(driver_id);
CREATE INDEX IF NOT EXISTS ix_task_evidence_task_created ON task_evidence(task_id, created_at);

CREATE TABLE IF NOT EXISTS task_events (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor_role VARCHAR(30),
    event_type VARCHAR(40) NOT NULL,
    from_status VARCHAR(30),
    to_status VARCHAR(30),
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_task_events_task_id ON task_events(task_id);
CREATE INDEX IF NOT EXISTS ix_task_events_task_created ON task_events(task_id, created_at);

COMMIT;
