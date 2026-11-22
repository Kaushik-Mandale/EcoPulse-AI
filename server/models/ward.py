from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from server.database.db import Base


class Ward(Base):
    __tablename__ = "wards"
    __table_args__ = (
        UniqueConstraint("municipality_id", "ward_number", name="uq_wards_municipality_number"),
    )

    id = Column(Integer, primary_key=True)
    municipality_id = Column(Integer, ForeignKey("municipalities.id", ondelete="RESTRICT"), nullable=False, index=True)
    ward_number = Column(String(30), nullable=False)
    display_name = Column(String(120), nullable=False)
    locality_description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
