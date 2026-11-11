from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from server.database.db import Base


class MobileOtpToken(Base):
    __tablename__ = "mobile_otp_tokens"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), index=True, nullable=False)
    otp_hash = Column(String(64), nullable=False)  # SHA-256 of 6-digit OTP
    purpose = Column(String(20), default="login", nullable=False)  # "login", "register"
    ip_address = Column(String(50), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=5, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Observability & Meta WhatsApp status tracking (authoritative migration: migrations/005_meta_otp_delivery_observability.sql)
    provider_message_id = Column(String(100), index=True, nullable=True)  # Meta wamid
    delivery_status = Column(String(30), default="PENDING", index=True, nullable=True)  # PENDING, ACCEPTED, SENT, DELIVERED, READ, FAILED
    delivery_error_code = Column(String(50), nullable=True)
    delivery_error_message = Column(String(255), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)


def check_mobile_otp_tokens_schema(engine) -> bool:
    """
    Read-only validation checking whether migration 005_meta_otp_delivery_observability.sql
    has been applied. Does NOT execute ALTER TABLE or CREATE INDEX at runtime.
    Logs a clear schema compatibility error if required columns are missing.
    """
    from sqlalchemy import inspect
    import logging
    log = logging.getLogger(__name__)
    try:
        insp = inspect(engine)
        if "mobile_otp_tokens" in insp.get_table_names():
            cols = {col["name"] for col in insp.get_columns("mobile_otp_tokens")}
            required = {
                "provider_message_id",
                "delivery_status",
                "delivery_error_code",
                "delivery_error_message",
                "delivered_at",
                "updated_at",
            }
            missing = required - cols
            if missing:
                log.error(
                    "[SCHEMA COMPATIBILITY ERROR] Table 'mobile_otp_tokens' is missing columns: %s. "
                    "Authoritative migration required: execute migrations/005_meta_otp_delivery_observability.sql.",
                    sorted(missing),
                )
                return False
        return True
    except Exception as e:
        log.warning("[SCHEMA] Error inspecting mobile_otp_tokens schema: %s", e)
        return True
