BEGIN;

CREATE TABLE IF NOT EXISTS municipalities (
    id SERIAL PRIMARY KEY,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(120) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_municipalities_code UNIQUE (code)
);
CREATE INDEX IF NOT EXISTS ix_municipalities_code ON municipalities (code);

CREATE TABLE IF NOT EXISTS wards (
    id SERIAL PRIMARY KEY,
    municipality_id INTEGER NOT NULL REFERENCES municipalities(id) ON DELETE RESTRICT,
    ward_number VARCHAR(30) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    locality_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_wards_municipality_number UNIQUE (municipality_id, ward_number)
);
CREATE INDEX IF NOT EXISTS ix_wards_municipality_id ON wards (municipality_id);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS municipality_id INTEGER REFERENCES municipalities(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS ward_id INTEGER REFERENCES wards(id) ON DELETE RESTRICT;
ALTER TABLE users ALTER COLUMN ward TYPE VARCHAR(120);
CREATE INDEX IF NOT EXISTS ix_users_municipality_id ON users (municipality_id);
CREATE INDEX IF NOT EXISTS ix_users_ward_id ON users (ward_id);

INSERT INTO municipalities (code, name)
VALUES ('DHULE', 'Dhule')
ON CONFLICT (code) DO NOTHING;

INSERT INTO wards (municipality_id, ward_number, display_name)
SELECT m.id, n::text, 'Ward ' || n::text
FROM municipalities AS m
CROSS JOIN generate_series(1, 19) AS n
WHERE m.code = 'DHULE'
ON CONFLICT (municipality_id, ward_number) DO NOTHING;

-- Backfill only unambiguous legacy display values for this initial municipality.
-- Historical complaint/task rows are deliberately not rewritten.
UPDATE users AS u
SET ward_id = w.id, municipality_id = w.municipality_id
FROM wards AS w
JOIN municipalities AS m ON m.id = w.municipality_id AND m.code = 'DHULE'
WHERE u.ward_id IS NULL
  AND (u.municipality_id IS NULL OR u.municipality_id = w.municipality_id)
  AND lower(trim(u.ward)) = lower(w.display_name);

COMMIT;
