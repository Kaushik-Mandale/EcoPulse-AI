-- Migration 006: Website-Generated WhatsApp Registration Verification Schema
-- Dedicated tracking table for website-generated verification challenges validated via inbound WhatsApp webhook

CREATE TABLE IF NOT EXISTS whatsapp_registration_challenges (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    otp_hash VARCHAR(64) NOT NULL,
    secret_hash VARCHAR(64),
    purpose VARCHAR(50) NOT NULL DEFAULT 'citizen_registration',
    profile_data TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    expires_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    ip_address VARCHAR(50),
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_whatsapp_reg_challenges_phone ON whatsapp_registration_challenges(phone);
CREATE INDEX IF NOT EXISTS ix_whatsapp_reg_challenges_status ON whatsapp_registration_challenges(status);
CREATE INDEX IF NOT EXISTS ix_whatsapp_reg_challenges_created_at ON whatsapp_registration_challenges(created_at);
CREATE INDEX IF NOT EXISTS ix_whatsapp_reg_challenges_user_id ON whatsapp_registration_challenges(user_id);
