from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database.db import get_db
from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.models.task_evidence import TaskEvidence
from server.models.user import User
from server.utils.security import get_current_user, require_collector_ward

router = APIRouter(prefix="/api/collector", tags=["Collector Portal"])


@router.get("/tasks")
def list_ward_collection_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read-only ward task board; task execution remains assigned-Driver only."""
    if current_user.role.casefold() != "collector":
        raise HTTPException(status_code=403, detail="Collector privileges are required.")
    ward = require_collector_ward(current_user)
    rows = (
        db.query(DriverTask, Complaint, User)
        .join(Complaint, DriverTask.complaint_id == Complaint.id)
        .outerjoin(User, DriverTask.driver_id == User.id)
        .filter(Complaint.ward == ward)
        .order_by(DriverTask.updated_at.desc(), DriverTask.id.desc())
        .all()
    )
    result = []
    for task, complaint, driver in rows:
        evidence_rows = (
            db.query(TaskEvidence)
            .filter(TaskEvidence.task_id == task.id)
            .order_by(TaskEvidence.id.desc())
            .all()
        )
        evidence = evidence_rows[0] if evidence_rows else None
        last_rejection = next((row for row in evidence_rows if row.status == "rejected"), None)
        result.append({
            "id": task.id,
            "status": task.status,
            "updated_at": task.updated_at,
            "driver_name": driver.full_name if driver else None,
            "complaint": {
                "id": complaint.id,
                "tracking_number": complaint.tracking_number,
                "ward": complaint.ward,
                "location": complaint.location_address,
                "waste_type": complaint.waste_type,
                "description": complaint.description,
                "status": complaint.status,
                "latitude": complaint.latitude,
                "longitude": complaint.longitude,
            },
            "evidence_status": evidence.status if evidence else None,
            "rejection_reason": last_rejection.rejection_reason if last_rejection else None,
            "collection_notes": evidence.collection_notes if evidence else None,
            "collected_at": evidence.collected_at if evidence else None,
            "evidence_history": [
                {
                    "status": row.status,
                    "rejection_reason": row.rejection_reason,
                    "collected_at": row.collected_at,
                    "submitted_at": row.submitted_at,
                }
                for row in evidence_rows
            ],
        })
    return result
