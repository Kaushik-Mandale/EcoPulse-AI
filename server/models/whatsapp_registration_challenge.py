"""
WhatsAppRegistrationChallenge model — website-generated verification code tracking.

Security Model:
- Plaintext 6-digit OTP code is returned once to the website registration response and never stored.
- Only HMAC-SHA256(code) is stored (otp_hash).
- High-entropy challenge secret (256 bits) is returned once to the originating client.
- Only SHA-256(challenge_secret) is stored (secret_hash). Possession of challenge_id alone cannot claim JWT.
- Challenges expire after 300 seconds (5 minutes).
- Single-use session issuance: once claimed, status is marked CONSUMED and cannot be claimed again.
- Bound strictly to normalized 10-digit Indian mobile number.
- Inbound WhatsApp sender phone must match challenge mobile number.
- Verified status is only granted upon authoritative inbound webhook validation.
"""

from datetime import datetime, timezone
import json
from typing import Optional, Dict, Any

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import relationship

from server.database.db import Base


class WhatsAppRegistrationChallenge(Base):
    __tablename__ = "whatsapp_registration_challenges"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), index=True, nullable=False)
    otp_hash = Column(String(64), nullable=False)
    secret_hash = Column(String(64), nullable=True)  # SHA-256 of high-entropy challenge secret
    purpose = Column(String(50), default="citizen_registration", nullable=False)
    profile_data = Column(Text, nullable=True)  # JSON-encoded draft profile (name, email, password_hash, ward)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=5, nullable=False)
    status = Column(String(30), default="PENDING", index=True, nullable=False)  # PENDING, VERIFIED, CONSUMED, EXPIRED, FAILED
    expires_at = Column(DateTime(timezone=True), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    user = relationship("User", foreign_keys=[user_id])

    def get_profile(self) -> Dict[str, Any]:
        """Safely parses JSON-encoded profile data."""
        if not self.profile_data:
            return {}
        try:
            return json.loads(self.profile_data)
        except Exception:
            return {}

    def set_profile(self, data: Dict[str, Any]) -> None:
        """Serializes dictionary to JSON string."""
        self.profile_data = json.dumps(data) if data else None


def check_whatsapp_registration_challenges_schema(engine) -> bool:
    """
    Read-only validation checking whether migration 006_whatsapp_registration_verification.sql
    has been applied. Does NOT execute ALTER TABLE or CREATE INDEX at runtime.
    Logs a clear schema compatibility error if required table/columns are missing.
    """
    from sqlalchemy import inspect
    import logging
    log = logging.getLogger(__name__)
    try:
        insp = inspect(engine)
        if "whatsapp_registration_challenges" not in insp.get_table_names():
            log.warning(
                "[SCHEMA COMPATIBILITY] Table 'whatsapp_registration_challenges' not found. "
                "Authoritative migration required: execute migrations/006_whatsapp_registration_verification.sql."
            )
            return False
        cols = {col["name"] for col in insp.get_columns("whatsapp_registration_challenges")}
        required = {
            "id", "phone", "otp_hash", "secret_hash", "purpose", "profile_data",
            "attempts", "max_attempts", "status", "expires_at",
            "verified_at", "consumed_at", "ip_address", "user_id", "created_at"
        }
        missing = required - cols
        if missing:
            log.error(
                "[SCHEMA COMPATIBILITY ERROR] Table 'whatsapp_registration_challenges' missing columns: %s. "
                "Authoritative migration required: execute migrations/006_whatsapp_registration_verification.sql.",
                sorted(missing)
            )
            return False
        return True
    except Exception as e:
        log.warning("[SCHEMA] Error inspecting whatsapp_registration_challenges schema: %s", e)
        return True
