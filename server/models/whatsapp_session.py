from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, func
from server.database.db import Base

class WhatsAppCitizen(Base):
    __tablename__ = 'whatsapp_citizens'

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(30), unique=True, index=True, nullable=False)
    full_name = Column(String(100), default='Shirpur Resident')
    ward = Column(String(50), default='Ward 12')
    household_id = Column(String(50), index=True, nullable=True)
    is_authorized = Column(Boolean, default=False)
    preferred_language = Column(String(10), default='mr') # 'mr' (Marathi) or 'en' (English)
    eco_coins = Column(Integer, default=100)
    conversation_state = Column(String(50), default='IDLE') # IDLE, AWAITING_PHOTO, AWAITING_LOCATION, AWAITING_QR
    pending_complaint_data = Column(Text, nullable=True) # JSON string for multi-step report flow
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class WhatsAppProcessedMessage(Base):
    __tablename__ = 'whatsapp_processed_messages'

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(100), unique=True, index=True, nullable=False)
    phone_number = Column(String(30), nullable=True)
    message_type = Column(String(30), nullable=True)
    status = Column(String(20), default='COMPLETED', index=True) # 'PROCESSING', 'COMPLETED', 'FAILED'
    complaint_id = Column(Integer, nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def ensure_whatsapp_processed_messages_schema(engine):
    """
    Lightweight, backward-compatible schema helper ensuring 'status', 'complaint_id',
    'error_message', and 'updated_at' exist in existing SQLite/PostgreSQL tables without requiring manual migration.
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
