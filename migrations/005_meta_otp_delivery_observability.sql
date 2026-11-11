-- Migration 005: Meta WhatsApp OTP Delivery Observability
-- Adds delivery tracking and status correlation columns to mobile_otp_tokens

ALTER TABLE mobile_otp_tokens ADD COLUMN IF NOT EXISTS provider_message_id VARCHAR(100);
ALTER TABLE mobile_otp_tokens ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(30) DEFAULT 'PENDING';
ALTER TABLE mobile_otp_tokens ADD COLUMN IF NOT EXISTS delivery_error_code VARCHAR(50);
ALTER TABLE mobile_otp_tokens ADD COLUMN IF NOT EXISTS delivery_error_message VARCHAR(255);
ALTER TABLE mobile_otp_tokens ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ;
ALTER TABLE mobile_otp_tokens ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;

CREATE INDEX IF NOT EXISTS ix_mobile_otp_tokens_provider_message_id ON mobile_otp_tokens(provider_message_id);
CREATE INDEX IF NOT EXISTS ix_mobile_otp_tokens_delivery_status ON mobile_otp_tokens(delivery_status);

