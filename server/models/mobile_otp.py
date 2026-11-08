from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from server.database.db import Base

class MobileOtpToken(Base):
    __tablename__ = "mobile_otp_tokens"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), index=True, nullable=False)
    otp_hash = Column(String(64), nullable=False) # SHA-256 of 6-digit OTP
    purpose = Column(String(20), default="login", nullable=False) # "login", "register"
    ip_address = Column(String(50), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=5, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
