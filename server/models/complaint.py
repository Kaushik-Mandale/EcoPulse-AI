from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from server.database.db import Base

class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    tracking_number = Column(String(30), unique=True, index=True, nullable=False)
    citizen_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    whatsapp_citizen_id = Column(
        Integer,
        ForeignKey("whatsapp_citizens.id"),
        nullable=True,
        index=True,
    )
    ward = Column(String(50), nullable=False)
    location_address = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    waste_type = Column(String(50), nullable=False) # Mixed Waste, Plastic Waste, Garbage Overflow, E-Waste
    description = Column(Text, nullable=True)
    image_url = Column(String(255), nullable=True)
    ai_status = Column(String(20), default="Verified") # Pending, Verified, Rejected
    ai_confidence = Column(Float, default=0.95)
    status = Column(String(20), default="Pending") # Pending, In Progress, Resolved / Completed
    assigned_driver_name = Column(String(100), nullable=True)
    assigned_driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
