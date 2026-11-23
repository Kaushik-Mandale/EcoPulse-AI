from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Union
from server.database.db import get_db
from server.schemas.complaint import (
    CitizenComplaintResponse,
    ComplaintCreate,
    ComplaintImageResponse,
    ComplaintResponse,
    ComplaintSubmissionResponse,
    PublicComplaintTrackingResponse,
)
from server.services.complaint_service import ComplaintService
from server.utils.security import get_current_user, get_current_user_optional
from server.models.user import User

router = APIRouter(prefix="/api/complaints", tags=["Complaints"])

@router.get("", response_model=List[Union[ComplaintResponse, CitizenComplaintResponse]])
def get_complaints(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = current_user.role.casefold()
    if role == "admin":
        return ComplaintService.get_all_complaints(db)
    if role == "collector":
        ward = (current_user.ward or "").strip()
        if not ward:
            raise HTTPException(status_code=403, detail="Collector has no assigned ward.")
        return ComplaintService.get_complaints_for_ward(db, ward)
    if role == "driver":
        return ComplaintService.get_driver_complaints(db, current_user.id)
    if role == "citizen":
        return ComplaintService.get_user_complaints(db, current_user.id)
    raise HTTPException(status_code=403, detail="Complaint access is not permitted for this account.")

@router.get("/my", response_model=List[CitizenComplaintResponse])
def get_my_complaints(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.casefold() not in {"citizen", "admin"}:
        raise HTTPException(status_code=403, detail="Citizen complaint history is not available to this account.")
    return ComplaintService.get_user_complaints(db, current_user.id)

@router.post("", response_model=ComplaintSubmissionResponse, status_code=status.HTTP_201_CREATED)
@router.post("/report", response_model=ComplaintSubmissionResponse, status_code=status.HTTP_201_CREATED)
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

@router.get("/track/{tracking_id}", response_model=PublicComplaintTrackingResponse)
def track_complaint(
    tracking_id: str,
    x_tracking_token: Optional[str] = Header(None, alias="X-Tracking-Token"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    result = ComplaintService.get_complaint_for_tracking(
        db, tracking_id, current_user, x_tracking_token
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found or tracking access is invalid."
        )
    return result

@router.get("/{complaint_id}/image-url", response_model=ComplaintImageResponse)
def get_complaint_image_url(
    complaint_id: str,
    token: Optional[str] = Query(None, description="Tracking token for anonymous citizen complaints"),
    x_tracking_token: Optional[str] = Header(None, alias="X-Tracking-Token"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Authorized endpoint to resolve a complaint image.
    Enforces role-based and complaint-level access control:
      - Admin / Collector: full administrative visibility
      - Assigned Driver: access to images for complaints linked to their tasks
      - Citizen: access strictly to their own submitted complaint images
      - Anonymous Citizen Tracking: requires high-entropy tracking token
    Generates a short-lived signed URL for Supabase storage or returns local path.
    """
    tracking_token = token or x_tracking_token
    return ComplaintService.authorize_and_resolve_image(db, complaint_id, current_user, tracking_token)

@router.get("/{complaint_id}/image")
def get_complaint_image(
    complaint_id: str,
    token: Optional[str] = Query(None, description="Tracking token for anonymous citizen complaints"),
    x_tracking_token: Optional[str] = Header(None, alias="X-Tracking-Token"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Authorized image redirect endpoint.
    Redirects browser to short-lived signed URL or local path upon successful authorization.
    """
    tracking_token = token or x_tracking_token
    resolved = ComplaintService.authorize_and_resolve_image(db, complaint_id, current_user, tracking_token)
    return RedirectResponse(url=resolved["url"], status_code=status.HTTP_307_TEMPORARY_REDIRECT)

@router.get("/{complaint_id}", response_model=PublicComplaintTrackingResponse)
def get_complaint(
    complaint_id: str,
    x_tracking_token: Optional[str] = Header(None, alias="X-Tracking-Token"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    result = ComplaintService.get_complaint_for_tracking(
        db, complaint_id, current_user, x_tracking_token
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found or tracking access is invalid."
        )
    return result
