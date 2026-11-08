-- Migration 004: Mobile-First OTP Authentication Schema
-- 1. Create mobile_otp_tokens table for secure hashed OTP verification
CREATE TABLE IF NOT EXISTS mobile_otp_tokens (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    otp_hash VARCHAR(64) NOT NULL,
    purpose VARCHAR(20) NOT NULL DEFAULT 'login',
    ip_address VARCHAR(50),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_mobile_otp_tokens_phone ON mobile_otp_tokens(phone);
CREATE INDEX IF NOT EXISTS ix_mobile_otp_tokens_created_at ON mobile_otp_tokens(created_at);

-- 2. Make email and hashed_password nullable in users table
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;
ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;

-- 3. Add unique index on non-empty phone numbers
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone ON users(phone) WHERE phone IS NOT NULL AND phone != '';
