from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from server.database.db import get_db
from server.schemas.complaint import ComplaintCreate, ComplaintResponse
from server.services.complaint_service import ComplaintService
from server.utils.security import get_current_user_optional
from server.models.user import User

router = APIRouter(prefix="/api/complaints", tags=["Complaints"])

@router.get("", response_model=List[ComplaintResponse])
def get_complaints(db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user_optional)):
    return ComplaintService.get_all_complaints(db)

@router.get("/my", response_model=List[ComplaintResponse])
def get_my_complaints(db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user_optional)):
    user_id = current_user.id if current_user else None
    return ComplaintService.get_user_complaints(db, user_id)

@router.post("", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
@router.post("/report", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
def create_complaint(
    payload: ComplaintCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    try:
        return ComplaintService.create_complaint(db, payload, current_user)
    except RuntimeError:
        # Retry exhaustion after max attempts — return 503 without leaking internals
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Complaint could not be created at this time. Please try again."
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/track/{tracking_id}", response_model=ComplaintResponse)
def track_complaint(tracking_id: str, db: Session = Depends(get_db)):
    result = ComplaintService.get_complaint_by_tracking_or_id(db, tracking_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint with reference '{tracking_id}' not found."
        )
    return result

@router.get("/{complaint_id}", response_model=ComplaintResponse)
def get_complaint(complaint_id: str, db: Session = Depends(get_db)):
    result = ComplaintService.get_complaint_by_tracking_or_id(db, complaint_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint with ID '{complaint_id}' not found."
        )
    return result
