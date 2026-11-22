"""Citizen-submitted public events received through WhatsApp."""
from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func

from server.database.db import Base


class EventReport(Base):
    __tablename__ = "event_reports"
    __table_args__ = (
        UniqueConstraint("reference_id", name="uq_event_reports_reference_id"),
        UniqueConstraint("source_message_id", name="uq_event_reports_source_message_id"),
    )

    id = Column(Integer, primary_key=True)
    reference_id = Column(String(32), nullable=False, index=True)
    source_message_id = Column(String(100), nullable=True)
    citizen_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    whatsapp_citizen_id = Column(Integer, ForeignKey("whatsapp_citizens.id", ondelete="RESTRICT"), nullable=False, index=True)
    category = Column(String(80), nullable=False)
    event_date = Column(Date, nullable=False)
    event_time = Column(String(8), nullable=False)
    location_address = Column(String(512), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="submitted", server_default="submitted")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
