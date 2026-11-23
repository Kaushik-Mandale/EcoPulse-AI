from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer, String, Boolean, DateTime, false, text
from sqlalchemy.sql import func
from server.database.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=True) # Optional in mobile-first auth
    employee_id = Column(String(50), unique=True, index=True, nullable=True)
    # Separate login handle: never substitutes for the official employee ID.
    login_id = Column(String(50), nullable=True)
    hashed_password = Column(String(255), nullable=True) # Optional for pure OTP users
    role = Column(String(20), nullable=False, default="citizen") # citizen, driver, collector, admin
    ward = Column(String(120), nullable=True)
    municipality_id = Column(Integer, ForeignKey("municipalities.id", ondelete="RESTRICT"), nullable=True, index=True)
    ward_id = Column(Integer, ForeignKey("wards.id", ondelete="RESTRICT"), nullable=True, index=True)
    phone = Column(String(20), nullable=True) # Primary mobile account identifier
    # Deny-by-default: new accounts are unverified until an explicit citizen
    # registration or invitation-activation flow marks them verified.
    eco_coins = Column(Integer, default=0, server_default=text("0"))
    is_active = Column(Boolean, default=True)
    failed_attempts = Column(Integer, default=0)
    is_locked = Column(Boolean, default=False)
    is_verified = Column(Boolean, nullable=False, default=False, server_default=false())
    is_super_admin = Column(Boolean, nullable=False, default=False, server_default=false())
    must_change_password = Column(Boolean, nullable=False, default=False, server_default=false())
    temporary_password_expires_at = Column(DateTime(timezone=True), nullable=True)
    mfa_secret_enc = Column(String(512), nullable=True)
    mfa_enabled = Column(Boolean, nullable=False, default=False, server_default=false())
    mfa_last_verified_step = Column(BigInteger, nullable=True)
    mfa_enrollment_expires_at = Column(DateTime(timezone=True), nullable=True)
    session_version = Column(Integer, nullable=False, default=0, server_default=text("0"))
    account_status = Column(String(30), nullable=False, default="active", server_default=text("'active'"))
    vehicle_assignment = Column(String(100), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    mfa_enrolled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index(
            "uq_users_phone",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL AND phone != ''"),
            sqlite_where=text("phone IS NOT NULL AND phone != ''"),
        ),
        Index(
            "uq_users_login_id",
            "login_id",
            unique=True,
            postgresql_where=text("login_id IS NOT NULL AND login_id != ''"),
            sqlite_where=text("login_id IS NOT NULL AND login_id != ''"),
        ),
        Index(
            "uq_users_single_super_admin",
            "is_super_admin",
            unique=True,
            postgresql_where=text("is_super_admin"),
            sqlite_where=text("is_super_admin = 1"),
        ),
    )
