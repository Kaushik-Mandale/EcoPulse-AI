"""WhatsApp session models — citizen conversation state and idempotency."""
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, func, UniqueConstraint
from server.database.db import Base


class WhatsAppCitizen(Base):
    """
    Represents a WhatsApp conversation identity.

    After account linking, user_id points to the canonical User record and
    is_authorized=True. Complaints submitted via WhatsApp use this record's
    user_id as Complaint.citizen_id.

    A unique partial constraint (enforced at migration level and app logic)
    ensures one User can have at most one active WhatsApp identity.
    """
    __tablename__ = 'whatsapp_citizens'

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(30), unique=True, index=True, nullable=False)

    # Canonical website identity — set when citizen links via LINK command
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        unique=True,   # one website account → at most one WhatsApp identity
    )

    full_name = Column(String(100), default='Dhule Citizen')
    ward = Column(String(50), nullable=True)
    household_id = Column(String(50), index=True, nullable=True)  # kept for legacy records
    is_authorized = Column(Boolean, default=False)  # True when user_id is set (linked)
    preferred_language = Column(String(10), default='mr')   # 'mr' or 'en'
    eco_coins = Column(Integer, default=0)
    conversation_state = Column(String(50), default='IDLE')  # IDLE, AWAITING_PHOTO, AWAITING_LOCATION
    pending_complaint_data = Column(Text, nullable=True)     # JSON for multi-step report flow
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WhatsAppProcessedMessage(Base):
    """Idempotency table — prevents duplicate processing of Meta webhook deliveries."""
    __tablename__ = 'whatsapp_processed_messages'

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(100), unique=True, index=True, nullable=False)
    phone_number = Column(String(30), nullable=True)
    message_type = Column(String(30), nullable=True)
    status = Column(String(20), default='COMPLETED', index=True)   # PROCESSING, COMPLETED, FAILED
    complaint_id = Column(Integer, nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def ensure_whatsapp_processed_messages_schema(engine):
    """
    Lightweight, backward-compatible schema helper ensuring required columns
    exist in already-deployed tables without requiring a full migration.
    Safe to call multiple times (idempotent).
    """
    from sqlalchemy import inspect, text
    try:
        insp = inspect(engine)
        if 'whatsapp_processed_messages' in insp.get_table_names():
            cols = {col['name'] for col in insp.get_columns('whatsapp_processed_messages')}
            with engine.connect() as conn:
                if 'status' not in cols:
                    conn.execute(text("ALTER TABLE whatsapp_processed_messages ADD COLUMN status VARCHAR(20) DEFAULT 'COMPLETED'"))
                if 'complaint_id' not in cols:
                    conn.execute(text("ALTER TABLE whatsapp_processed_messages ADD COLUMN complaint_id INTEGER"))
                if 'error_message' not in cols:
                    conn.execute(text("ALTER TABLE whatsapp_processed_messages ADD COLUMN error_message TEXT"))
                if 'updated_at' not in cols:
                    conn.execute(text("ALTER TABLE whatsapp_processed_messages ADD COLUMN updated_at TIMESTAMP"))
                conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[SCHEMA] WhatsApp processed messages schema check warning: {e}")
