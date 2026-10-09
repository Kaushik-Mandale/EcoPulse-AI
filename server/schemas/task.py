from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional

VALID_TASK_STATUSES = {"Pending", "In Progress", "Completed"}

class DriverTaskStatusUpdate(BaseModel):
    status: str # Pending, In Progress, Completed
    proof_image_url: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_TASK_STATUSES:
            raise ValueError(f"Invalid status '{v}'. Allowed statuses: {', '.join(sorted(VALID_TASK_STATUSES))}")
        return v

class DriverTaskResponse(BaseModel):
    id: int
    name: str
    status: str
    statusColor: str
    location_name: str
    complaint_id: Optional[int] = None
    proof_image_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
