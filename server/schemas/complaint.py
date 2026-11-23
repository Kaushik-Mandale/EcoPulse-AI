from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class ComplaintCreate(BaseModel):
    location: str
    type: str
    ward: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_url: Optional[str] = None

class ComplaintResponse(BaseModel):
    id: str # Tracking ID, e.g., EP-2026-00123
    db_id: int
    location: str
    type: str
    ward: str
    status: str
    assignedTo: Optional[str] = "Unassigned"
    time: Optional[str] = None
    statusColor: str
    image_url: Optional[str] = None
    ai_status: Optional[str] = None
    ai_confidence: Optional[float] = None
    created_at: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


class CitizenComplaintResponse(BaseModel):
    """Fields needed by an authenticated citizen for their own complaint history."""
    id: str
    location: str
    type: str
    ward: str
    status: str
    time: Optional[str] = None
    statusColor: str
    has_image: bool = False
    created_at: Optional[datetime] = None


class PublicComplaintTrackingResponse(BaseModel):
    """Minimal citizen-facing status response; no internal IDs or assignment data."""
    id: str
    location: str
    type: str
    ward: str
    status: str
    time: Optional[str] = None
    statusColor: str
    created_at: Optional[datetime] = None


class ComplaintSubmissionResponse(BaseModel):
    """Safe submission receipt. Anonymous submissions include a tracking capability once."""
    id: str
    location: str
    type: str
    ward: str
    status: str
    created_at: Optional[datetime] = None
    tracking_token: Optional[str] = None

class ComplaintImageResponse(BaseModel):
    url: str
    complaint_id: str
    storage_type: str
    expires_in: Optional[int] = None
