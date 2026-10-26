from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from server.database.db import Base


def ensure_notification_schema(engine):
    """Legacy compatibility hook for notification schema upgrades.

    This helper intentionally does not mutate the database at application startup.
    A legacy PostgreSQL foreign-key on ``notifications.recipient_id`` is a destructive
    schema change; if that constraint still exists in an old deployment, it should be
    removed only through an explicit, reviewed migration that preserves notification data
    and the privacy filtering rules in ``AdminService.get_public_broadcasts``.

    Recommended migration (run outside app startup, after backup):
        ALTER TABLE notifications
        DROP CONSTRAINT IF EXISTS notifications_recipient_id_fkey;

    This keeps the public notification privacy model intact: public broadcasts remain
    ``recipient_id IS NULL`` and private notifications remain filtered out of the public API.
    """
    return


class Notification(Base):
    """System notification / broadcast model for admin alerts."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(20), default="Info")   # Critical, Warning, Info
    audience = Column(String(100), default="All")            # All Drivers, All Citizens, etc.
    priority = Column(String(50), default="Standard")        # Standard, High, Emergency
    icon = Column(String(50), default="notifications")       # Material icon name
    is_broadcast = Column(Boolean, default=False)            # True = admin broadcast
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Private notifications are intentionally allowed to target a user ID that may not yet
    # exist or may be an out-of-band system alert. The public API must filter these out
    # without requiring a hard database foreign-key dependency for every notification.
    recipient_id = Column(Integer, nullable=True)  # None = all
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
