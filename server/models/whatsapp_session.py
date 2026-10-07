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
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
