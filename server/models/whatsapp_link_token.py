"""WhatsAppLinkToken model — secure one-time linking tokens."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from server.database.db import Base


class WhatsAppLinkToken(Base):
    """
    Stores a hashed, single-use, time-limited token that lets a registered
    website citizen link their WhatsApp number to their account.

    Security properties:
    - Only the SHA-256 hash of the token is persisted; the plaintext is
      returned once to the authenticated website session and never stored.
    - expires_at is set to 10 minutes from creation.
    - consumed_at is set atomically when the token is redeemed.
    - attempt_count tracks failed redemption attempts for rate-limiting.
    - Previous unused tokens for the same user are invalidated (consumed_at
      set) when a new token is issued.
    """

    __tablename__ = "whatsapp_link_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    whatsapp_phone = Column(String(30), nullable=True)   # filled on redemption
    attempt_count = Column(Integer, default=0, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship (optional — for ORM convenience)
    user = relationship("User", foreign_keys=[user_id])

