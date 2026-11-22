BEGIN;

CREATE TABLE IF NOT EXISTS event_reports (
    id SERIAL PRIMARY KEY,
    reference_id VARCHAR(32) NOT NULL,
    source_message_id VARCHAR(100),
    citizen_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    whatsapp_citizen_id INTEGER NOT NULL REFERENCES whatsapp_citizens(id) ON DELETE RESTRICT,
    category VARCHAR(80) NOT NULL,
    event_date DATE NOT NULL,
    event_time VARCHAR(8) NOT NULL,
    location_address VARCHAR(512) NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    status VARCHAR(20) NOT NULL DEFAULT 'submitted',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_event_reports_reference_id UNIQUE (reference_id),
    CONSTRAINT uq_event_reports_source_message_id UNIQUE (source_message_id)
);
CREATE INDEX IF NOT EXISTS ix_event_reports_reference_id ON event_reports(reference_id);
CREATE INDEX IF NOT EXISTS ix_event_reports_citizen_id ON event_reports(citizen_id);
CREATE INDEX IF NOT EXISTS ix_event_reports_whatsapp_citizen_id ON event_reports(whatsapp_citizen_id);

COMMIT;
