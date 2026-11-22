from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint, func

from server.database.db import Base


class Municipality(Base):
    __tablename__ = "municipalities"
    __table_args__ = (UniqueConstraint("code", name="uq_municipalities_code"),)

    id = Column(Integer, primary_key=True)
    code = Column(String(40), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
