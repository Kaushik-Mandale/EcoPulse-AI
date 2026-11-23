import csv
import io
import datetime
from fastapi import HTTPException
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import case, func

from server.models.complaint import Complaint
from server.models.user import User
from server.models.task import DriverTask
from server.models.bin import SmartBin
from server.models.notification import Notification
from server.schemas.admin import (
    AdminMetricsResponse, WardPerformance,
    AdminDriverResponse, BinResponse, BinTelemetrySummary,
    AnalyticsResponse, WardComplaintBar, MonthlyTrend,
    NotificationResponse
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: derive task stats for a driver
# ─────────────────────────────────────────────────────────────────────────────
def _task_stats(db: Session, driver_id: int, ward_scope: Optional[str] = None):
    query = db.query(DriverTask).filter(DriverTask.driver_id == driver_id)
    if ward_scope is not None:
        query = query.join(Complaint, DriverTask.complaint_id == Complaint.id).filter(
            Complaint.ward == ward_scope
        )
    tasks = query.all()
    completed = sum(1 for t in tasks if t.status == "Completed")
    in_progress = sum(1 for t in tasks if t.status == "In Progress")
    pending = sum(1 for t in tasks if t.status == "Pending")
    return completed, in_progress, pending


def _driver_to_response(
    driver: User, db: Session, ward_scope: Optional[str] = None
) -> AdminDriverResponse:
    completed, in_progress, pending = _task_stats(db, driver.id, ward_scope=ward_scope)
    return AdminDriverResponse(
        id=driver.id,
        full_name=driver.full_name,
        email=driver.email,
        employee_id=driver.employee_id,
        login_id=driver.login_id,
        ward=driver.ward,
        ward_id=driver.ward_id,
        municipality_id=driver.municipality_id,
        phone=driver.phone,
        role=driver.role,
        is_active=driver.is_active,
        is_verified=driver.is_verified,
        mfa_enabled=bool(driver.mfa_enabled),
        account_status=driver.account_status,
        vehicle_assignment=driver.vehicle_assignment,
        eco_coins=driver.eco_coins if driver.eco_coins is not None else 0,
        tasks_completed=completed,
        tasks_in_progress=in_progress,
        tasks_pending=pending,
        created_at=driver.created_at
    )


def _driver_response(driver: User, db: Session) -> AdminDriverResponse:
    return _driver_to_response(driver, db)


# ─────────────────────────────────────────────────────────────────────────────
class AdminService:
    driver_to_response = staticmethod(_driver_response)

    # ── Dashboard Metrics ──────────────────────────────────────────────────
    @staticmethod
    def get_dashboard_metrics(db: Session, ward_scope: Optional[str] = None) -> AdminMetricsResponse:
        complaints = db.query(Complaint)
        if ward_scope is not None:
            complaints = complaints.filter(Complaint.ward == ward_scope)
        total = complaints.count()
        pending = complaints.filter(Complaint.status == "Pending").count()
        in_progress = complaints.filter(Complaint.status == "In Progress").count()
        completed = complaints.filter(Complaint.status == "Completed").count()

        drivers = db.query(User).filter(User.role == "driver")
        if ward_scope is not None:
            drivers = drivers.filter(User.ward == ward_scope)
        active_drivers = drivers.filter(User.is_active.is_(True)).count()
        total_drivers = drivers.count()
        total_citizens = 0 if ward_scope is not None else db.query(User).filter(User.role == "citizen").count()
        truck_query = db.query(func.count(func.distinct(User.vehicle_assignment))).filter(
            User.role == "driver",
            User.is_active.is_(True),
            User.vehicle_assignment.isnot(None),
            User.vehicle_assignment != "",
        )
        if ward_scope is not None:
            truck_query = truck_query.filter(User.ward == ward_scope)
        active_trucks = truck_query.scalar() or 0

        resolution_rate = round((completed / total) * 100, 1) if total else 0

        ward_query = db.query(
            Complaint.ward,
            func.count(Complaint.id),
            func.sum(case((Complaint.status == "Completed", 1), else_=0)),
        ).filter(
            Complaint.ward.isnot(None),
            Complaint.ward != "",
        )
        if ward_scope is not None:
            ward_query = ward_query.filter(Complaint.ward == ward_scope)
        ward_rows = ward_query.group_by(Complaint.ward).all()
        top_wards = [
            WardPerformance(
                name=ward,
                percent=round((completed_count / count) * 100),
            )
            for ward, count, completed_count in ward_rows
        ]
        top_wards.sort(key=lambda x: x.percent, reverse=True)
        top_wards = top_wards[:4]

        return AdminMetricsResponse(
            total_complaints=total,
            pending_complaints=pending,
            in_progress_complaints=in_progress,
            completed_complaints=completed,
            resolution_rate=resolution_rate,
            active_trucks=active_trucks,
            total_drivers=total_drivers,
            total_citizens=total_citizens,
            top_wards=top_wards
        )

    # ── CSV Export ─────────────────────────────────────────────────────────
    @staticmethod
    def generate_complaints_csv(db: Session) -> str:
        complaints = db.query(Complaint).order_by(Complaint.id.desc()).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Tracking ID", "Ward", "Location Address", "Waste Type",
            "Status", "Assigned Driver", "AI Status", "AI Confidence", "Created At"
        ])
        for c in complaints:
            writer.writerow([
                c.tracking_number,
                c.ward,
                c.location_address,
                c.waste_type,
                c.status,
                c.assigned_driver_name or "Unassigned",
                c.ai_status or "",
                f"{int(c.ai_confidence * 100)}%" if c.ai_confidence is not None else "",
                c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "N/A"
            ])
        return output.getvalue()

    # ── Driver Management ─────────────────────────────────────────────────
    @staticmethod
    def get_all_drivers(db: Session, ward_scope: Optional[str] = None, include_collectors: bool = False,
                        ward_id: Optional[int] = None, municipality_id: Optional[int] = None) -> List[AdminDriverResponse]:
        from datetime import datetime, timezone
        from server.models.account_invitation import AccountInvitation
        roles = ("driver", "collector") if ward_scope is None or include_collectors else ("driver",)
        query = db.query(User).filter(User.role.in_(roles))
        if ward_scope is not None:
            query = query.filter(func.lower(func.trim(User.ward)) == ward_scope.strip().casefold())
        if ward_id is not None:
            query = query.filter(User.ward_id == ward_id)
        if municipality_id is not None:
            query = query.filter(User.municipality_id == municipality_id)
        drivers = query.order_by(User.created_at.desc()).all()
        if not drivers:
            return []
        invitations = db.query(AccountInvitation).filter(
            AccountInvitation.user_id.in_([driver.id for driver in drivers]),
            AccountInvitation.role.in_(roles),
        ).order_by(AccountInvitation.created_at.desc(), AccountInvitation.id.desc()).all()
        latest = {}
        for invitation in invitations:
            latest.setdefault(invitation.user_id, invitation)
        now = datetime.now(timezone.utc)
        result = []
        for driver in drivers:
            invitation = latest.get(driver.id)
            state = "not_invited"
            if invitation:
                expires = invitation.expires_at
                if expires and expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if invitation.revoked_at:
                    state = "revoked"
                elif invitation.consumed_at:
                    state = "used"
                elif expires is None or expires <= now:
                    state = "expired"
                else:
                    state = "pending"
            item = _driver_to_response(driver, db, ward_scope=ward_scope)
            item.activated_at = driver.activated_at
            item.invitation_status = state
            item.invitation_expires_at = invitation.expires_at if invitation else None
            result.append(item)
        return result

    @staticmethod
    def create_driver(db: Session, payload) -> AdminDriverResponse:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail="Driver accounts must be provisioned through the authorized invitation workflow.",
        )

    @staticmethod
    def update_driver_status(db: Session, driver_id: int, is_active: bool) -> AdminDriverResponse:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=409,
            detail="Use the authorized account lifecycle endpoint so actor, scope, reason, and audit requirements are enforced.",
        )

    # ── Complaint Status Update ────────────────────────────────────────────
    @staticmethod
    def update_complaint_status(
        db: Session, complaint_db_id: int, new_status: str, *, ward_scope: Optional[str] = None
    ) -> Complaint:
        if new_status == "Completed":
            raise HTTPException(status_code=409, detail="Complaint completion requires approved Driver evidence through task verification.")
        from fastapi import HTTPException, status as http_status
        query = db.query(Complaint).filter(Complaint.id == complaint_db_id)
        if ward_scope is not None:
            query = query.filter(Complaint.ward == ward_scope)
        complaint = query.first()
        if not complaint:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Complaint not found.")
        if complaint.status == "Completed" and new_status != "Completed":
            raise HTTPException(status_code=409, detail="A verified complaint cannot be reopened through status editing.")
        linked_task = db.query(DriverTask).filter(DriverTask.complaint_id == complaint.id).order_by(DriverTask.id.desc()).first()
        if linked_task and new_status != complaint.status:
            raise HTTPException(status_code=409, detail="Complaint status is managed by its assigned task lifecycle.")
        complaint.status = new_status
        db.commit()
        db.refresh(complaint)
        return complaint

    # ── Smart Bin Telemetry ────────────────────────────────────────────────
    @staticmethod
    def get_bin_telemetry(db: Session, ward_scope: Optional[str] = None) -> BinTelemetrySummary:
        query = db.query(SmartBin)
        if ward_scope is not None:
            query = query.filter(SmartBin.ward == ward_scope)
        bins = query.all()

        critical = [b for b in bins if b.fill_level_pct >= 80]
        warning = [b for b in bins if 60 <= b.fill_level_pct < 80]
        normal = [b for b in bins if b.fill_level_pct < 60]
        avg_fill = round(sum(b.fill_level_pct for b in bins) / len(bins), 1) if bins else 0.0

        return BinTelemetrySummary(
            total_bins=len(bins),
            critical_bins=len(critical),
            warning_bins=len(warning),
            normal_bins=len(normal),
            avg_fill_level=avg_fill,
            bins=[BinResponse.model_validate(b) for b in bins]
        )

    @staticmethod
    def update_bin_fill(
        db: Session, bin_id: int, fill_level_pct: int, is_active: Optional[bool] = None,
        *, ward_scope: Optional[str] = None,
    ) -> BinResponse:
        from fastapi import HTTPException, status as http_status
        query = db.query(SmartBin).filter(SmartBin.id == bin_id)
        if ward_scope is not None:
            query = query.filter(SmartBin.ward == ward_scope)
        smart_bin = query.first()
        if not smart_bin:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Bin not found.")
        smart_bin.fill_level_pct = fill_level_pct
        if is_active is not None:
            smart_bin.is_active = is_active
        if fill_level_pct == 0:
            smart_bin.last_collected_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(smart_bin)
        return BinResponse.model_validate(smart_bin)

    # ── Analytics ─────────────────────────────────────────────────────────
    @staticmethod
    def get_analytics(db: Session, ward_scope: Optional[str] = None) -> AnalyticsResponse:
        complaints = db.query(Complaint)
        if ward_scope is not None:
            complaints = complaints.filter(Complaint.ward == ward_scope)
        total = complaints.count()
        completed = complaints.filter(Complaint.status == "Completed").count()
        pending = complaints.filter(Complaint.status == "Pending").count()

        resolution_rate = round((completed / total * 100), 1) if total > 0 else 0.0

        ward_query = db.query(
            Complaint.ward,
            func.count(Complaint.id),
            func.sum(case((Complaint.status == "Completed", 1), else_=0)),
            func.sum(case((Complaint.status == "Pending", 1), else_=0)),
        ).filter(
            Complaint.ward.isnot(None),
            Complaint.ward != "",
        )
        if ward_scope is not None:
            ward_query = ward_query.filter(Complaint.ward == ward_scope)
        ward_rows = ward_query.group_by(Complaint.ward).all()
        ward_breakdown = [
            WardComplaintBar(ward=ward, total=count, resolved=resolved, pending=pending)
            for ward, count, resolved, pending in ward_rows
        ]

        # Monthly trends from real data
        now = datetime.datetime.now(datetime.timezone.utc)
        months = []
        for i in range(5, -1, -1):
            target = now - datetime.timedelta(days=i * 30)
            m_label = target.strftime("%b")
            month_start = target.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = (month_start + datetime.timedelta(days=32)).replace(day=1)
            month_query = db.query(Complaint).filter(
                Complaint.created_at >= month_start,
                Complaint.created_at < next_month
            )
            resolved_query = db.query(Complaint).filter(
                Complaint.created_at >= month_start,
                Complaint.created_at < next_month,
                Complaint.status == "Completed"
            )
            if ward_scope is not None:
                month_query = month_query.filter(Complaint.ward == ward_scope)
                resolved_query = resolved_query.filter(Complaint.ward == ward_scope)
            m_total = month_query.count()
            m_resolved = resolved_query.count()
            months.append(MonthlyTrend(month=m_label, complaints=m_total, resolved=m_resolved))

        # Waste type distribution
        waste_types_query = db.query(
            Complaint.waste_type,
            func.count(Complaint.id).label("count")
        )
        if ward_scope is not None:
            waste_types_query = waste_types_query.filter(Complaint.ward == ward_scope)
        waste_types_query = waste_types_query.group_by(Complaint.waste_type).all()
        top_waste = [{"type": wt, "count": cnt} for wt, cnt in waste_types_query]
        drivers = db.query(User).filter(User.role == "driver")
        if ward_scope is not None:
            drivers = drivers.filter(User.ward == ward_scope)
        active_drivers = drivers.filter(User.is_active.is_(True)).count()
        total_drivers = drivers.count()

        return AnalyticsResponse(
            resolution_rate=resolution_rate,
            avg_response_hours=None,
            citizen_satisfaction=None,
            waste_collected_tonnes=None,
            ward_breakdown=ward_breakdown,
            monthly_trends=months,
            top_waste_types=top_waste,
            active_drivers=active_drivers,
            total_drivers=total_drivers
        )

    # ── Notifications ─────────────────────────────────────────────────────
    @staticmethod
    def get_notifications(db: Session) -> List[NotificationResponse]:
        notifications = db.query(Notification).order_by(Notification.created_at.desc()).all()
        return [NotificationResponse.model_validate(n) for n in notifications]

    @staticmethod
    def get_public_broadcasts(db: Session) -> List[NotificationResponse]:
        """Returns only public broadcast notifications, filtering out internal and private alerts."""
        broadcasts = db.query(Notification).filter(
            Notification.is_broadcast == True,
            Notification.recipient_id == None
        ).order_by(Notification.created_at.desc()).all()
        return [NotificationResponse.model_validate(n) for n in broadcasts]

    @staticmethod
    def send_broadcast(db: Session, sender_id: int, title: str, message: str, audience: str, priority: str) -> NotificationResponse:
        # Determine notification type from priority
        if "Emergency" in priority:
            ntype = "Critical"
            icon = "campaign"
        elif "High" in priority:
            ntype = "Warning"
            icon = "campaign"
        else:
            ntype = "Info"
            icon = "campaign"

        new_notif = Notification(
            title=title,
            message=message,
            notification_type=ntype,
            audience=audience,
            priority=priority,
            icon=icon,
            is_broadcast=True,
            sender_id=sender_id,
            is_read=False,
        )
        db.add(new_notif)
        db.commit()
        db.refresh(new_notif)
        return NotificationResponse.model_validate(new_notif)

    # ── User Management ───────────────────────────────────────────────────
    @staticmethod
    def get_all_users(db: Session):
        from server.schemas.admin import AdminUserResponse
        users = db.query(User).order_by(User.created_at.desc()).all()
        return [
            AdminUserResponse(
                id=u.id,
                full_name=u.full_name,
                email=u.email,
                role=u.role,
                ward=u.ward,
                phone=u.phone,
                employee_id=u.employee_id,
                  login_id=u.login_id,
                  account_status=u.account_status,
                  is_verified=bool(u.is_verified),
                eco_coins=u.eco_coins if u.eco_coins is not None else 0,
                is_active=u.is_active,
                created_at=u.created_at
            )
            for u in users
        ]
