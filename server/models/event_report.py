"""Citizen-submitted public events received through WhatsApp."""
from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
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


def check_event_reports_schema(engine) -> bool:
    """
    Read-only validation checking whether migration 007_whatsapp_event_reports.sql
    has been applied. Does NOT execute ALTER TABLE or CREATE INDEX at runtime.
    Logs a clear schema compatibility error if required table/columns are missing.
    """
    from sqlalchemy import inspect
    import logging
    log = logging.getLogger(__name__)
    try:
        insp = inspect(engine)
        if "event_reports" not in insp.get_table_names():
            log.warning(
                "[SCHEMA COMPATIBILITY] Table 'event_reports' not found. "
                "Authoritative migration required: execute migrations/007_whatsapp_event_reports.sql."
            )
            return False
        cols = {col["name"] for col in insp.get_columns("event_reports")}
        required = {
            "id", "reference_id", "source_message_id", "citizen_id",
            "whatsapp_citizen_id", "category", "event_date", "event_time",
            "location_address", "latitude", "longitude", "status", "created_at"
        }
        missing = required - cols
        if missing:
            log.error(
                "[SCHEMA COMPATIBILITY ERROR] Table 'event_reports' missing columns: %s. "
                "Authoritative migration required: execute migrations/007_whatsapp_event_reports.sql.",
                sorted(missing)
            )
            return False
        return True
    except Exception as e:
        log.warning("[SCHEMA] Error inspecting event_reports schema: %s", e)
        return False
