from datetime import datetime, timezone
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.models.task_evidence import TaskEvidence
from server.models.task_event import TaskEvent
from server.models.user import User
from server.services.media_storage import get_media_storage


def _event(db, task, actor, event, target=None, details=None):
    db.add(TaskEvent(task_id=task.id, actor_user_id=actor.id if actor else None,
                     actor_role=actor.role if actor else "system", event_type=event,
                     from_status=task.status, to_status=target or task.status, details=details))


def _owned_task(db, task_id, driver, lock=False):
    q = db.query(DriverTask).filter(DriverTask.id == task_id)
    task = q.with_for_update() if lock else q
    task = task.first()
    if not task:
        raise HTTPException(404, "Task not found.")
    if task.driver_id != driver.id:
        raise HTTPException(403, "Access forbidden: You can only access tasks assigned to you.")
    return task


def transition_driver_task(db: Session, task_id: int, driver: User, action: str):
    task = _owned_task(db, task_id, driver, lock=True)
    allowed = {"Pending": ("accept", "Accepted"), "Accepted": ("start", "In Progress")}
    expected = allowed.get(task.status)
    if not expected or action != expected[0]:
        raise HTTPException(409, f"Cannot {action} a task in {task.status} status.")
    previous = task.status
    task.status = expected[1]
    if task.complaint_id:
        complaint = db.query(Complaint).filter(Complaint.id == task.complaint_id).with_for_update().first()
        if complaint and complaint.status != "Completed":
            complaint.status = "In Progress"
    db.add(TaskEvent(task_id=task.id, actor_user_id=driver.id, actor_role=driver.role,
                     event_type="task_accepted" if action == "accept" else "collection_started",
                     from_status=previous, to_status=task.status))
    db.commit()
    db.refresh(task)
    return task


def add_evidence(db: Session, task_id: int, driver: User, before_ref: str | None,
                 after_ref: str, notes: str | None):
    task = _owned_task(db, task_id, driver, lock=True)
    if task.status not in {"In Progress", "Requires Rework"}:
        raise HTTPException(409, "Evidence can only be submitted for an in-progress task or rework.")
    if not task.complaint_id:
        raise HTTPException(409, "This task is not linked to a complaint.")
    if notes and len(notes) > 4000:
        raise HTTPException(422, "Collection notes must be 4000 characters or fewer.")
    complaint = db.query(Complaint).filter(Complaint.id == task.complaint_id).with_for_update().first()
    if not complaint or complaint.status == "Completed":
        raise HTTPException(409, "Completed or unavailable complaints cannot receive evidence.")
    previous = task.status
    is_resubmission = previous == "Requires Rework"
    evidence = TaskEvidence(task_id=task.id, complaint_id=complaint.id, driver_id=driver.id,
                            before_image_ref=before_ref, after_image_ref=after_ref,
                            collection_notes=(notes or "").strip() or None,
                            collected_at=datetime.now(timezone.utc), status="submitted")
    db.add(evidence)
    task.status = "Evidence Submitted"
    db.add(TaskEvent(task_id=task.id, actor_user_id=driver.id, actor_role=driver.role,
                     event_type="evidence_resubmitted" if is_resubmission else "evidence_submitted",
                     from_status=previous, to_status=task.status))
    db.commit()
    db.refresh(evidence)
    return evidence


def submit_for_verification(db: Session, task_id: int, driver: User):
    task = _owned_task(db, task_id, driver, lock=True)
    if task.status != "Evidence Submitted":
        raise HTTPException(409, "Submit evidence before requesting verification.")
    evidence = db.query(TaskEvidence).filter(TaskEvidence.task_id == task.id, TaskEvidence.status == "submitted").order_by(TaskEvidence.id.desc()).with_for_update().first()
    if not evidence:
        raise HTTPException(409, "No unsubmitted evidence is available.")
    complaint = db.query(Complaint).filter(Complaint.id == task.complaint_id).with_for_update().first()
    if not complaint or complaint.status == "Completed":
        raise HTTPException(409, "Complaint cannot be submitted for verification.")
    previous = task.status
    evidence.status = "pending"
    evidence.submitted_at = datetime.now(timezone.utc)
    task.status = "Pending Verification"
    complaint.status = "Pending Verification"
    db.add(TaskEvent(task_id=task.id, actor_user_id=driver.id, actor_role=driver.role,
                     event_type="submitted_for_verification", from_status=previous, to_status=task.status))
    db.commit()
    db.refresh(task)
    return task


def review_evidence(db: Session, task_id: int, reviewer: User, approve: bool, reason: str | None = None):
    task = db.query(DriverTask).filter(DriverTask.id == task_id).with_for_update().first()
    if not task:
        raise HTTPException(404, "Task not found.")
    if task.status != "Pending Verification":
        raise HTTPException(409, "Task is not pending verification.")
    evidence = db.query(TaskEvidence).filter(TaskEvidence.task_id == task.id, TaskEvidence.status == "pending").order_by(TaskEvidence.id.desc()).with_for_update().first()
    if not evidence:
        raise HTTPException(409, "Pending evidence was not found.")
    if approve and reviewer.id == evidence.driver_id:
        raise HTTPException(403, "A driver cannot approve their own evidence.")
    complaint = db.query(Complaint).filter(Complaint.id == task.complaint_id).with_for_update().first()
    if not complaint or complaint.status == "Completed":
        raise HTTPException(409, "Complaint is already resolved or unavailable.")
    previous = task.status
    now = datetime.now(timezone.utc)
    evidence.reviewed_by_id = reviewer.id
    evidence.reviewed_at = now
    evidence.status = "approved" if approve else "rejected"
    evidence.rejection_reason = None if approve else (reason or "").strip()
    task.status = "Completed" if approve else "Requires Rework"
    complaint.status = "Completed" if approve else "In Progress"
    event = "completion_verified" if approve else "evidence_rejected"
    db.add(TaskEvent(task_id=task.id, actor_user_id=reviewer.id, actor_role=reviewer.role,
                     event_type=event, from_status=previous, to_status=task.status,
                     details=None if approve else evidence.rejection_reason))
    db.commit()
    db.refresh(task)
    return task


def verification_detail(db: Session, task: DriverTask):
    complaint = db.query(Complaint).filter(Complaint.id == task.complaint_id).first()
    driver = db.query(User).filter(User.id == task.driver_id).first()
    evidence_rows = db.query(TaskEvidence).filter(TaskEvidence.task_id == task.id).order_by(TaskEvidence.id.desc()).all()
    storage = get_media_storage()
    evidence = []
    for row in evidence_rows:
        evidence.append({"id": row.id, "before_image_url": storage.get_url(row.before_image_ref) if row.before_image_ref else None,
                         "after_image_url": storage.get_url(row.after_image_ref), "notes": row.collection_notes,
                         "collected_at": row.collected_at, "submitted_at": row.submitted_at,
                         "status": row.status, "reviewed_at": row.reviewed_at,
                         "rejection_reason": row.rejection_reason})
    events = db.query(TaskEvent).filter(TaskEvent.task_id == task.id).order_by(TaskEvent.created_at.asc(), TaskEvent.id.asc()).all()
    return {"id": task.id, "status": task.status, "location_name": task.location_name,
            "driver_name": driver.full_name if driver else None,
            "complaint": ({"id": complaint.id, "tracking_number": complaint.tracking_number,
                           "ward": complaint.ward, "location_address": complaint.location_address,
                           "waste_type": complaint.waste_type, "description": complaint.description,
                           "original_image_url": complaint.image_url, "status": complaint.status}
                          if complaint else None),
            "evidence": evidence,
            "history": [{"event_type": e.event_type, "from_status": e.from_status,
                         "to_status": e.to_status, "details": e.details, "created_at": e.created_at}
                        for e in events]}
