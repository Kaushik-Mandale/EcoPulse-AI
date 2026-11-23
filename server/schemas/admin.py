from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Literal
from datetime import datetime


# ────────────────────────────────────────────────
# Shared / Basic
# ────────────────────────────────────────────────

class AssignTaskRequest(BaseModel):
    complaint_id: int
    driver_name: str


class WardPerformance(BaseModel):
    name: str
    percent: int


# ────────────────────────────────────────────────
# Dashboard Metrics
# ────────────────────────────────────────────────

class AdminMetricsResponse(BaseModel):
    total_complaints: int
    pending_complaints: int
    in_progress_complaints: int
    completed_complaints: int
    resolution_rate: float
    active_trucks: int
    total_drivers: int
    total_citizens: int
    top_wards: List[WardPerformance]


# ────────────────────────────────────────────────
# Driver Management
# ────────────────────────────────────────────────

class AdminDriverCreate(BaseModel):
    full_name: str
    employee_id: str
    email: Optional[str] = None
    phone: str
    ward: Optional[str] = None
    vehicle_assignment: Optional[str] = None


class AdminDriverResponse(BaseModel):
    id: int
    full_name: str
    email: Optional[str] = None
    employee_id: Optional[str] = None
    login_id: Optional[str] = None
    ward: Optional[str] = None
    ward_id: Optional[int] = None
    municipality_id: Optional[int] = None
    phone: Optional[str] = None
    role: str
    is_active: bool
    is_verified: bool = False
    mfa_enabled: bool = False
    account_status: str = "pending"
    vehicle_assignment: Optional[str] = None
    eco_coins: int
    tasks_completed: int
    tasks_in_progress: int
    tasks_pending: int
    created_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    invitation_status: Optional[str] = None
    invitation_expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DriverStatusUpdate(BaseModel):
    is_active: bool
    reason: Optional[str] = Field(default=None, max_length=2000)


class AccountStatusRequest(BaseModel):
    account_status: Literal["active", "suspended", "retired"]
    reason: Optional[str] = Field(default=None, max_length=2000)


class AdminProvisionRequest(BaseModel):
    full_name: str
    employee_id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    ward: Optional[str] = None


# ────────────────────────────────────────────────
# Complaint Management (Admin view)
# ────────────────────────────────────────────────

class ComplaintStatusUpdate(BaseModel):
    status: str   # Pending | In Progress | Completed


# ────────────────────────────────────────────────
# Smart Bin Telemetry
# ────────────────────────────────────────────────

class BinResponse(BaseModel):
    id: int
    bin_code: str
    location_name: str
    ward: str
    bin_type: str
    capacity_liters: int
    fill_level_pct: int
    is_active: bool
    last_collected_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BinFillUpdate(BaseModel):
    fill_level_pct: int
    is_active: Optional[bool] = None


class BinTelemetrySummary(BaseModel):
    total_bins: int
    critical_bins: int       # fill_level >= 80%
    warning_bins: int        # fill_level 60-79%
    normal_bins: int         # fill_level < 60%
    avg_fill_level: float
    bins: List[BinResponse]


# ────────────────────────────────────────────────
# Analytics
# ────────────────────────────────────────────────

class WardComplaintBar(BaseModel):
    ward: str
    total: int
    resolved: int
    pending: int


class MonthlyTrend(BaseModel):
    month: str
    complaints: int
    resolved: int


class AnalyticsResponse(BaseModel):
    resolution_rate: float
    avg_response_hours: Optional[float] = None
    citizen_satisfaction: Optional[float] = None
    waste_collected_tonnes: Optional[float] = None
    ward_breakdown: List[WardComplaintBar]
    monthly_trends: List[MonthlyTrend]
    top_waste_types: List[dict]
    active_drivers: int
    total_drivers: int


# ────────────────────────────────────────────────
# Notifications / Broadcasts
# ────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    notification_type: str
    audience: str
    priority: str
    icon: str
    is_broadcast: bool
    is_read: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class BroadcastRequest(BaseModel):
    title: str = "Admin Broadcast"
    message: str
    audience: str = "All Drivers (Active Shift)"
    priority: str = "Standard (App Notification)"


# ────────────────────────────────────────────────
# User Management (Admin)
# ────────────────────────────────────────────────

class AdminUserResponse(BaseModel):
    id: int
    full_name: str
    email: Optional[str] = None
    role: str
    ward: Optional[str] = None
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    login_id: Optional[str] = None
    account_status: str = "active"
    is_verified: bool = False
    eco_coins: int
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StaffProvisionRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    role: Literal["admin", "driver", "collector"]
    phone: str = Field(min_length=10, max_length=20)
    email: Optional[str] = Field(default=None, max_length=120)
    employee_id: Optional[str] = Field(default=None, max_length=50)
    ward_id: Optional[int] = Field(default=None, gt=0)
    municipality_id: Optional[int] = Field(default=None, gt=0)

    model_config = ConfigDict(extra="forbid")


class StaffCredentialResponse(BaseModel):
    id: int
    full_name: str
    role: str
    employee_id: Optional[str] = None
    login_id: str
    temporary_password: str
    ward: Optional[str] = None
    ward_id: Optional[int] = None
    municipality_id: Optional[int] = None
    account_status: str
    is_verified: bool
    temporary_password_expires_at: Optional[datetime] = None


class StaffPasswordResetRequest(BaseModel):
    """Intentionally empty: reset actions generate credentials server-side."""

    model_config = ConfigDict(extra="forbid")


class MunicipalityCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=120)

    model_config = ConfigDict(extra="forbid")


class WardCreateRequest(BaseModel):
    municipality_id: int = Field(gt=0)
    ward_number: str = Field(min_length=1, max_length=30)
    display_name: str = Field(min_length=1, max_length=120)
    locality_description: Optional[str] = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid")


class WardUpdateRequest(BaseModel):
    ward_number: str = Field(min_length=1, max_length=30)
    display_name: str = Field(min_length=1, max_length=120)
    locality_description: Optional[str] = Field(default=None, max_length=2000)
    is_active: bool

    model_config = ConfigDict(extra="forbid")


class StaffWardAssignmentRequest(BaseModel):
    ward_id: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid")
