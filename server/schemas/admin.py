from pydantic import BaseModel, ConfigDict
from typing import List, Optional
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
    email: str
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    ward: Optional[str] = "Ward 12"
    password: str = "Password123!"


class AdminDriverResponse(BaseModel):
    id: int
    full_name: str
    email: str
    employee_id: Optional[str] = None
    ward: Optional[str] = None
    phone: Optional[str] = None
    role: str
    is_active: bool
    eco_coins: int
    tasks_completed: int
    tasks_in_progress: int
    tasks_pending: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DriverStatusUpdate(BaseModel):
    is_active: bool


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
    avg_response_hours: float
    citizen_satisfaction: float
    waste_collected_tonnes: float
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
    email: str
    role: str
    ward: Optional[str] = None
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    eco_coins: int
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
