from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, CheckConstraint, Index
from sqlalchemy.sql import func
from server.database.db import Base


class TaskEvidence(Base):
    __tablename__ = "task_evidence"
    __table_args__ = (
        CheckConstraint("status IN ('submitted', 'pending', 'approved', 'rejected')", name="ck_task_evidence_status"),
        Index("ix_task_evidence_task_created", "task_id", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id", ondelete="RESTRICT"), nullable=False, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    before_image_ref = Column(String(512), nullable=True)
    after_image_ref = Column(String(512), nullable=False)
    collection_notes = Column(Text, nullable=True)
    collected_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="submitted")
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
