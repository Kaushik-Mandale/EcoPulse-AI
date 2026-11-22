from sqlalchemy import Column, Integer, String, DateTime, text
from sqlalchemy.sql import func
from server.database.db import Base


class MobileOtpToken(Base):
    __tablename__ = "mobile_otp_tokens"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), index=True, nullable=False)
    otp_hash = Column(String(64), nullable=False)  # SHA-256 of 6-digit OTP
    purpose = Column(String(20), default="login", server_default=text("'login'"), nullable=False)  # "login", "register"
    ip_address = Column(String(50), nullable=True)
    attempts = Column(Integer, default=0, server_default=text("0"), nullable=False)
    max_attempts = Column(Integer, default=5, server_default=text("5"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Observability & Meta WhatsApp status tracking (authoritative migration: migrations/005_meta_otp_delivery_observability.sql)
    provider_message_id = Column(String(100), index=True, nullable=True)  # Meta wamid
    delivery_status = Column(String(30), default="PENDING", server_default=text("'PENDING'"), index=True, nullable=True)  # PENDING, ACCEPTED, SENT, DELIVERED, READ, FAILED
    delivery_error_code = Column(String(50), nullable=True)
    delivery_error_message = Column(String(255), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)


def check_mobile_otp_tokens_schema(engine) -> bool:
    """
    Read-only validation checking whether migration 005_meta_otp_delivery_observability.sql
    has been applied. Does NOT execute ALTER TABLE or CREATE INDEX at runtime.
    Raises SchemaValidationError if required schema objects are missing or cannot
    be inspected. Does not mutate the database.
    """
    from server.database.initialization import verify_migration_contracts

    return verify_migration_contracts(engine, ("005",))
