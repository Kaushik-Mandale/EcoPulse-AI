from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from server.database.db import Base

class DriverTask(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"), nullable=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    location_name = Column(String(255), nullable=False)
    status = Column(String(20), default="Pending") # Pending, Accepted, In Progress, Evidence Submitted, Pending Verification, Completed, Requires Rework, Cancelled
    proof_image_url = Column(String(255), nullable=True)
    route_order = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
