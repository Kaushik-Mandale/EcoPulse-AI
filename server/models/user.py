from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from server.database.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=True) # Optional in mobile-first auth
    employee_id = Column(String(50), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=True) # Optional for pure OTP users
    role = Column(String(20), nullable=False, default="citizen") # citizen, driver, collector, admin
    ward = Column(String(50), nullable=True)
    phone = Column(String(20), unique=True, index=True, nullable=True) # Primary mobile account identifier
    eco_coins = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    failed_attempts = Column(Integer, default=0)
    is_locked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
