import re
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from typing import List

from server.database.db import get_db
from server.schemas.admin import (
    AdminMetricsResponse, AssignTaskRequest,
    AdminDriverCreate, AdminDriverResponse, DriverStatusUpdate,
    ComplaintStatusUpdate,
    BinTelemetrySummary, BinFillUpdate, BinResponse,
    AnalyticsResponse,
    NotificationResponse, BroadcastRequest,
    AdminUserResponse, AdminProvisionRequest,
    AccountStatusRequest, StaffProvisionRequest, StaffCredentialResponse,
    MunicipalityCreateRequest, WardCreateRequest, WardUpdateRequest, StaffWardAssignmentRequest,
)
from server.schemas.complaint import ComplaintResponse
from server.services.admin_service import AdminService
from server.services.complaint_service import ComplaintService
from server.utils.security import (
    get_current_admin_user,
    get_current_super_admin_user,
    require_collector_ward,
    require_municipal_admin,
)
from server.models.user import User
from server.models.municipality import Municipality
from server.models.ward import Ward
from server.models.complaint import Complaint
from server.models.account_invitation import AccountInvitation
from server.models.security_audit_event import SecurityAuditEvent
from server.services.iam_service import audit
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from server.models.task import DriverTask
from server.services.task_lifecycle_service import review_evidence, verification_detail
from server.services.staff_provisioning_service import provision_staff_account, reset_staff_password
from server.services.ward_service import actor_municipality_ids, ensure_staff_scope, resolve_active_ward
from server.models.whatsapp_session import WhatsAppCitizen
from server.models.mobile_otp import MobileOtpToken
from server.models.whatsapp_link_token import WhatsAppLinkToken
from server.models.whatsapp_registration_challenge import WhatsAppRegistrationChallenge
from sqlalchemy import func

router = APIRouter(prefix="/api/admin", tags=["Admin Operations"])


class EvidenceRejection(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


@router.get("/tasks/verification")
def list_task_verification(status_filter: str = "Pending Verification", db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    require_municipal_admin(current_admin)
    allowed = {"Pending Verification", "Requires Rework", "Completed"}
    if status_filter not in allowed:
        raise HTTPException(422, "Unsupported task verification status.")
    tasks = db.query(DriverTask).filter(DriverTask.status == status_filter).order_by(DriverTask.updated_at.desc(), DriverTask.id.desc()).all()
    return [verification_detail(db, task) for task in tasks]


@router.get("/tasks/{task_id}/verification")
def get_task_verification(task_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    require_municipal_admin(current_admin)
    task = db.query(DriverTask).filter(DriverTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found.")
    return verification_detail(db, task)


@router.post("/tasks/{task_id}/approve")
def approve_task_evidence(task_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    require_municipal_admin(current_admin)
    task = review_evidence(db, task_id, current_admin, True)
    return verification_detail(db, task)


@router.post("/tasks/{task_id}/reject")
def reject_task_evidence(task_id: int, payload: EvidenceRejection, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    require_municipal_admin(current_admin)
    reason = payload.reason.strip()
    if len(reason) < 3:
        raise HTTPException(422, "A rejection reason of at least 3 characters is required.")
    task = review_evidence(db, task_id, current_admin, False, reason)
    return verification_detail(db, task)


def _collector_ward(user: User):
    return require_collector_ward(user) if user.role.lower() == "collector" else None


def _staff_ward_scope(user: User):
    if user.role.lower() == "collector":
        return require_collector_ward(user)
    if user.is_super_admin:
        return None
    ward = (user.ward or "").strip()
    return ward or None


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Metrics
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/metrics", response_model=AdminMetricsResponse)
def get_admin_metrics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Returns real-time dashboard KPIs: complaint counts, resolution rate, active trucks, ward performance."""
    return AdminService.get_dashboard_metrics(db, ward_scope=_collector_ward(current_admin))


# ─────────────────────────────────────────────────────────────────────────────
# Complaints Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/complaints", response_model=List[ComplaintResponse])
def get_admin_complaints(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Returns all complaints visible to admin (all statuses, all wards)."""
    ward = _collector_ward(current_admin)
    if ward is not None:
        return ComplaintService.get_complaints_for_ward(db, ward)
    return ComplaintService.get_all_complaints(db)


@router.get("/complaints/{complaint_db_id}/operations")
def get_complaint_operations(
    complaint_db_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """Return complaint details and lifecycle evidence without exposing citizen credentials."""
    ward = _collector_ward(current_admin)
    query = db.query(Complaint).filter(Complaint.id == complaint_db_id)
    if ward is not None:
        query = query.filter(Complaint.ward == ward)
    complaint = query.first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found.")
    response = ComplaintService._to_response(complaint).model_dump()
    response["description"] = complaint.description
    task = db.query(DriverTask).filter(DriverTask.complaint_id == complaint.id).order_by(DriverTask.id.desc()).first()
    if task is None:
        task_detail = None
    elif current_admin.role.lower() == "collector":
        task_detail = {"id": task.id, "status": task.status, "location_name": task.location_name}
    else:
        task_detail = verification_detail(db, task)
    return {"complaint": response, "task": task_detail}


@router.post("/assign-task", response_model=ComplaintResponse)
def assign_task(
    payload: AssignTaskRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Assigns a driver to a complaint, updates status to In Progress."""
    try:
        return ComplaintService.assign_driver(
            db, payload.complaint_id, payload.driver_name,
            ward_scope=_collector_ward(current_admin),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/complaints/{complaint_db_id}/status", response_model=ComplaintResponse)
def update_complaint_status(
    complaint_db_id: int,
    payload: ComplaintStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Admin updates the status of any complaint (Pending → In Progress → Completed)."""
    valid_statuses = ["Pending", "In Progress", "Completed"]
    ward = _collector_ward(current_admin)
    complaint_scope = db.query(Complaint).filter(Complaint.id == complaint_db_id)
    if ward is not None:
        complaint_scope = complaint_scope.filter(Complaint.ward == ward)
    if not complaint_scope.first():
        raise HTTPException(status_code=404, detail="Complaint not found.")
    if payload.status == "Completed":
        raise HTTPException(status_code=409, detail="Complaint completion requires approved Driver evidence through task verification.")
    if ward is not None and payload.status not in {"In Progress", "Completed"}:
        raise HTTPException(status_code=403, detail="Collectors may only update operational complaint statuses.")
    if payload.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    updated = AdminService.update_complaint_status(db, complaint_db_id, payload.status, ward_scope=ward)
    # Re-use existing complaint response serializer
    return ComplaintService._to_response(updated)


@router.get("/export-csv")
def export_complaints_csv(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Generates and downloads a full complaints audit CSV report."""
    require_municipal_admin(current_admin)
    try:
        csv_data = AdminService.generate_complaints_csv(db)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=municipal_complaints_report.csv"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating CSV report: {str(e)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Driver Management
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/staff", response_model=StaffCredentialResponse, status_code=status.HTTP_201_CREATED)
def provision_staff(
    payload: StaffProvisionRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """Create one municipal staff account and return its one-time credentials."""
    return provision_staff_account(db, current_admin, payload)


@router.post("/accounts/{user_id}/temporary-password", response_model=StaffCredentialResponse)
def issue_staff_temporary_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    target = db.query(User).filter(
        User.id == user_id,
        User.role.in_(["admin", "driver", "collector"]),
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Staff account not found.")
    return reset_staff_password(db, current_admin, target)

@router.get("/drivers", response_model=List[AdminDriverResponse])
def get_all_drivers(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Returns staff within a Municipal Admin's ward; Collectors see Drivers in their ward."""
    allowed_municipalities = actor_municipality_ids(db, current_admin)
    scoped_ward_id = current_admin.ward_id if not current_admin.is_super_admin else None
    municipality_id = None
    if allowed_municipalities is not None:
        municipality_id = next(iter(allowed_municipalities)) if len(allowed_municipalities) == 1 else None
    return AdminService.get_all_drivers(
        db,
        ward_scope=None if scoped_ward_id else _staff_ward_scope(current_admin),
        include_collectors=current_admin.role.lower() == "admin",
        ward_id=scoped_ward_id,
        municipality_id=municipality_id,
    )


def _ward_payload(db: Session, ward: Ward) -> dict:
    municipality = db.query(Municipality).filter(Municipality.id == ward.municipality_id).first()
    assigned = db.query(User).filter(User.ward_id == ward.id).order_by(User.role, User.full_name).all()
    counts = {role: sum(user.role == role for user in assigned) for role in ("admin", "driver", "collector")}
    return {
        "id": ward.id,
        "municipality_id": ward.municipality_id,
        "municipality_name": municipality.name if municipality else "Unavailable",
        "ward_number": ward.ward_number,
        "display_name": ward.display_name,
        "locality_description": ward.locality_description,
        "is_active": bool(ward.is_active),
        "created_at": ward.created_at,
        "updated_at": ward.updated_at,
        "staff_counts": counts,
        "assigned_staff": [{"id": user.id, "full_name": user.full_name, "role": user.role,
                            "login_id": user.login_id, "account_status": user.account_status}
                           for user in assigned if user.role in {"admin", "driver", "collector"}],
    }


def _assert_super_admin(actor: User) -> None:
    if actor.role.casefold() != "admin" or not actor.is_super_admin:
        raise HTTPException(status_code=403, detail="Only a Super Admin may manage the ward registry.")


@router.get("/wards/municipalities")
def list_ward_municipalities(db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    allowed = actor_municipality_ids(db, current_admin)
    query = db.query(Municipality)
    if allowed is not None:
        query = query.filter(Municipality.id.in_(allowed), Municipality.is_active.is_(True))
    return [{"id": row.id, "code": row.code, "name": row.name, "is_active": bool(row.is_active)}
            for row in query.order_by(Municipality.name).all()]


@router.post("/wards/municipalities", status_code=status.HTTP_201_CREATED)
def create_ward_municipality(payload: MunicipalityCreateRequest, db: Session = Depends(get_db),
                             current_admin: User = Depends(get_current_super_admin_user)):
    _assert_super_admin(current_admin)
    municipality = Municipality(code=payload.code.strip().upper(), name=payload.name.strip(), is_active=True)
    db.add(municipality)
    try:
        db.flush()
        audit(db, "municipality_created", actor=current_admin, details=f"municipality_id={municipality.id}; code={municipality.code}")
        db.commit()
    except Exception as exc:
        db.rollback()
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail="That municipality code already exists.") from exc
        raise
    return {"id": municipality.id, "code": municipality.code, "name": municipality.name, "is_active": True}


@router.get("/wards")
def list_wards(municipality_id: int | None = None, active: bool | None = None, q: str = "",
               db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    allowed = actor_municipality_ids(db, current_admin)
    query = db.query(Ward)
    if allowed is not None:
        query = query.filter(Ward.municipality_id.in_(allowed))
        if active is True:
            query = query.filter(Ward.is_active.is_(True))
    elif municipality_id is not None:
        query = query.filter(Ward.municipality_id == municipality_id)
    if municipality_id is not None and allowed is not None and municipality_id not in allowed:
        raise HTTPException(status_code=403, detail="You may view wards only in your municipality.")
    if active is not None:
        query = query.filter(Ward.is_active.is_(active))
    if q.strip():
        term = f"%{q.strip().casefold()}%"
        query = query.filter((func.lower(Ward.display_name).like(term)) | (func.lower(Ward.ward_number).like(term)))
    return [_ward_payload(db, ward) for ward in query.order_by(Ward.municipality_id, Ward.ward_number).all()]


@router.post("/wards", status_code=status.HTTP_201_CREATED)
def create_ward(payload: WardCreateRequest, db: Session = Depends(get_db),
                current_admin: User = Depends(get_current_super_admin_user)):
    _assert_super_admin(current_admin)
    municipality = db.query(Municipality).filter(Municipality.id == payload.municipality_id,
                                                  Municipality.is_active.is_(True)).first()
    if not municipality:
        raise HTTPException(status_code=422, detail="Select an active municipality from the registry.")
    ward = Ward(municipality_id=municipality.id, ward_number=payload.ward_number.strip(),
                display_name=payload.display_name.strip(), locality_description=(payload.locality_description or "").strip() or None)
    db.add(ward)
    try:
        db.flush()
        audit(db, "ward_created", actor=current_admin,
              details=f"ward_id={ward.id}; municipality_id={municipality.id}; ward_number={ward.ward_number}")
        db.commit()
    except Exception as exc:
        db.rollback()
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail="That ward number already exists in this municipality.") from exc
        raise
    return _ward_payload(db, ward)


@router.patch("/wards/{ward_id}")
def update_ward(ward_id: int, payload: WardUpdateRequest, db: Session = Depends(get_db),
                current_admin: User = Depends(get_current_super_admin_user)):
    _assert_super_admin(current_admin)
    ward = db.query(Ward).filter(Ward.id == ward_id).first()
    if not ward:
        raise HTTPException(status_code=404, detail="Ward not found.")
    was_active = bool(ward.is_active)
    ward_number = payload.ward_number.strip()
    display_name = payload.display_name.strip()
    locality = (payload.locality_description or "").strip() or None
    if db.query(Ward.id).filter(Ward.municipality_id == ward.municipality_id,
                                Ward.ward_number == ward_number, Ward.id != ward.id).first():
        raise HTTPException(status_code=409, detail="That ward number already exists in this municipality.")
    ward.ward_number = ward_number
    ward.display_name = display_name
    ward.locality_description = locality
    ward.is_active = payload.is_active
    event = "ward_activated" if not was_active and payload.is_active else "ward_deactivated" if was_active and not payload.is_active else "ward_updated"
    audit(db, event, actor=current_admin,
          details=f"ward_id={ward.id}; municipality_id={ward.municipality_id}; ward_number={ward_number}; display_name={display_name}")
    db.commit()
    db.refresh(ward)
    return _ward_payload(db, ward)


@router.patch("/staff/{user_id}/ward")
def assign_staff_ward(user_id: int, payload: StaffWardAssignmentRequest,
                       db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    require_municipal_admin(current_admin)
    target = db.query(User).filter(User.id == user_id, User.role.in_(["driver", "collector"])).first()
    if not target:
        raise HTTPException(status_code=404, detail="Driver or Collector account not found.")
    if not current_admin.is_super_admin:
        ensure_staff_scope(db, current_admin, target)
    ward = resolve_active_ward(db, current_admin, payload.ward_id)
    old_ward = target.ward
    target.ward_id = ward.id
    target.municipality_id = ward.municipality_id
    target.ward = ward.display_name
    audit(db, "staff_ward_reassigned", actor=current_admin, target=target,
          details=f"from={old_ward or 'unassigned'}; to={ward.display_name}; ward_id={ward.id}")
    db.commit()
    return {"id": target.id, "ward": target.ward, "ward_id": target.ward_id,
            "municipality_id": target.municipality_id}


@router.post("/drivers", status_code=status.HTTP_410_GONE)
def create_driver(
    payload: AdminDriverCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Legacy issuance route is disabled; raw tokens are delivered only by the offline CLI."""
    require_municipal_admin(current_admin)
    raise HTTPException(status_code=410, detail="Staff invitations are issued offline. Use `python -m server.scripts.issue_invitation_offline --help`.")


@router.post("/collectors", status_code=status.HTTP_410_GONE)
def create_collector(
    payload: AdminProvisionRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Legacy issuance route is disabled; raw tokens are delivered only by the offline CLI."""
    require_municipal_admin(current_admin)
    raise HTTPException(status_code=410, detail="Staff invitations are issued offline. Use `python -m server.scripts.issue_invitation_offline --help`.")


@router.patch("/drivers/{driver_id}/status", response_model=AdminDriverResponse)
def update_driver_status(
    driver_id: int,
    payload: DriverStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Admin activates or deactivates a driver account."""
    require_municipal_admin(current_admin)
    driver = db.query(User).filter(User.id == driver_id, User.role == "driver").first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")
    if driver.account_status in {"retired", "deactivated"}:
        raise HTTPException(status_code=409, detail="Retired accounts cannot be reactivated or changed.")
    if not current_admin.is_super_admin:
        ensure_staff_scope(db, current_admin, driver)
    if payload.is_active and not driver.is_verified:
        raise HTTPException(status_code=409, detail="A driver must complete mobile verification before activation.")
    if not payload.is_active and not (getattr(payload, "reason", None) or "").strip():
        raise HTTPException(status_code=422, detail="A reason is required to suspend an account.")
    if payload.is_active and driver.account_status != "suspended":
        raise HTTPException(status_code=409, detail="Only suspended accounts can be reactivated here.")
    driver.account_status = "active" if payload.is_active else "suspended"
    driver.is_active = payload.is_active
    driver.suspended_at = None if payload.is_active else datetime.now(timezone.utc)
    if payload.is_active:
        driver.is_locked = False
        driver.failed_attempts = 0
    driver.session_version = (driver.session_version or 0) + 1
    audit(db, "account_reactivated" if payload.is_active else "account_suspended", actor=current_admin, target=driver,
          details=(getattr(payload, "reason", None) or "").strip() or None)
    db.commit()
    db.refresh(driver)
    return AdminService.driver_to_response(driver, db)


@router.post("/admins/invitations", status_code=status.HTTP_410_GONE)
def invite_administrator(
    payload: AdminProvisionRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin_user),
):
    raise HTTPException(status_code=410, detail="Staff invitations are issued offline. Use `python -m server.scripts.issue_invitation_offline --help`.")


@router.get("/admins")
def list_administrators(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin_user),
):
    admins = db.query(User).filter(User.role == "admin").order_by(User.created_at.desc()).all()
    admin_ids = [admin.id for admin in admins]
    invitations = []
    if admin_ids:
        invitations = db.query(AccountInvitation).filter(
            AccountInvitation.user_id.in_(admin_ids),
            AccountInvitation.role == "admin",
        ).order_by(AccountInvitation.created_at.desc()).all()
    latest_invitations = {}
    for invitation in invitations:
        latest_invitations.setdefault(invitation.user_id, invitation)

    now = datetime.now(timezone.utc)

    def invitation_state(invitation):
        if invitation is None:
            return "not_invited"
        if invitation.revoked_at is not None:
            return "revoked"
        if invitation.consumed_at is not None:
            return "used"
        expires_at = invitation.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is None or expires_at <= now:
            return "expired"
        return "pending"

    return [
        {
            "id": admin.id,
            "full_name": admin.full_name,
            "employee_id": admin.employee_id,
            "login_id": admin.login_id,
            "email": admin.email,
            "phone": admin.phone,
            "ward_id": admin.ward_id,
            "municipality_id": admin.municipality_id,
            "is_super_admin": bool(admin.is_super_admin),
            "is_active": bool(admin.is_active),
            "is_verified": bool(admin.is_verified),
            "mfa_enabled": bool(admin.mfa_enabled),
            "account_status": admin.account_status,
            "created_by_id": admin.created_by_id,
            "approved_by_id": admin.approved_by_id,
            "created_at": admin.created_at,
            "activated_at": admin.activated_at,
            "suspended_at": admin.suspended_at,
            "deactivated_at": admin.deactivated_at,
            "invitation_status": invitation_state(latest_invitations.get(admin.id)),
            "invitation_expires_at": (
                latest_invitations[admin.id].expires_at
                if admin.id in latest_invitations
                else None
            ),
        }
        for admin in admins
    ]


@router.post("/admins/{admin_id}/reset-invitation", status_code=status.HTTP_410_GONE)
def reset_admin_invitation(
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin_user),
):
    raise HTTPException(status_code=410, detail="Invitation resets are issued offline. Use `python -m server.scripts.issue_invitation_offline --help`.")


@router.post("/drivers/{driver_id}/reset-invitation", status_code=status.HTTP_410_GONE)
def reset_driver_invitation(
    driver_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    require_municipal_admin(current_admin)
    raise HTTPException(status_code=410, detail="Invitation resets are issued offline. Use `python -m server.scripts.issue_invitation_offline --help`.")


@router.patch("/accounts/{user_id}/status")
def update_account_status(
    user_id: int,
    payload: AccountStatusRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    require_municipal_admin(current_admin)
    target = db.query(User).filter(User.id == user_id, User.role.in_(["admin", "collector", "driver", "citizen"])).first()
    if not target:
        raise HTTPException(status_code=404, detail="Account not found.")
    is_super_admin = bool(current_admin.is_super_admin)
    if target.id == current_admin.id or target.is_super_admin:
        raise HTTPException(status_code=403, detail="A Super Admin cannot change their own status or another Super Admin.")
    if not is_super_admin:
        if target.role not in {"driver", "collector"}:
            raise HTTPException(status_code=403, detail="Municipal Admins may manage only Drivers and Collectors.")
        ensure_staff_scope(db, current_admin, target)
    if target.account_status in {"retired", "deactivated"}:
        raise HTTPException(status_code=409, detail="Retired accounts cannot be reactivated or changed.")
    reason = (payload.reason or "").strip()
    if payload.account_status in {"suspended", "retired"} and len(reason) < 3:
        raise HTTPException(status_code=422, detail="Provide a reason of at least 3 characters.")
    if payload.account_status == "active" and target.account_status != "suspended":
        raise HTTPException(status_code=409, detail="Only suspended accounts can be reactivated.")
    if payload.account_status == "suspended" and target.account_status == "suspended":
        raise HTTPException(status_code=409, detail="Account is already suspended.")
    now = datetime.now(timezone.utc)
    target.account_status = payload.account_status
    target.is_active = payload.account_status == "active"
    target.session_version = (target.session_version or 0) + 1
    target.suspended_at = now if payload.account_status == "suspended" else None
    if payload.account_status == "active":
        target.is_locked = False
        target.failed_attempts = 0
    if payload.account_status == "retired":
        target.deactivated_at = now
        # Revoke all activation and linking material while retaining its audit/history rows.
        db.query(AccountInvitation).filter(
            AccountInvitation.user_id == target.id,
            AccountInvitation.consumed_at.is_(None),
            AccountInvitation.revoked_at.is_(None),
        ).update({"revoked_at": now}, synchronize_session=False)
        digits = re.sub(r"\D", "", target.phone or "")
        short_phone = digits[2:] if digits.startswith("91") and len(digits) == 12 else digits[1:] if digits.startswith("0") and len(digits) == 11 else digits
        phone_values = {value for value in (target.phone, digits, short_phone, f"91{short_phone}", f"+91{short_phone}", f"0{short_phone}") if value}
        if phone_values:
            db.query(MobileOtpToken).filter(MobileOtpToken.phone.in_(phone_values), MobileOtpToken.consumed_at.is_(None)).update({"consumed_at": now}, synchronize_session=False)
            db.query(WhatsAppRegistrationChallenge).filter(WhatsAppRegistrationChallenge.phone.in_(phone_values), WhatsAppRegistrationChallenge.status.in_(["PENDING", "VERIFIED"])).update({"status": "EXPIRED", "consumed_at": now}, synchronize_session=False)
        db.query(WhatsAppLinkToken).filter(WhatsAppLinkToken.user_id == target.id, WhatsAppLinkToken.consumed_at.is_(None)).update({"consumed_at": now}, synchronize_session=False)
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.user_id == target.id).update({"is_authorized": False}, synchronize_session=False)
        audit(db, "account_retired", actor=current_admin, target=target, details=reason)
    else:
        target.deactivated_at = None
        action = "account_suspended" if payload.account_status == "suspended" else "account_reactivated"
        audit(db, action, actor=current_admin, target=target, details=reason or None)
    db.commit()
    return {"success": True, "account_status": target.account_status}


def _authorize_account_view(db: Session, actor: User, target: User) -> None:
    if actor.is_super_admin:
        if target.is_super_admin and actor.id != target.id:
            raise HTTPException(status_code=403, detail="Super Admin accounts are not available through this endpoint.")
        return
    require_municipal_admin(actor)
    if target.role not in {"driver", "collector"}:
        raise HTTPException(status_code=403, detail="Municipal Admins may view only Drivers and Collectors.")
    ensure_staff_scope(db, actor, target)


@router.get("/accounts/{user_id}")
def get_account_details(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    require_municipal_admin(current_admin)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Account not found.")
    _authorize_account_view(db, current_admin, target)
    return {"id": target.id, "full_name": target.full_name, "employee_id": target.employee_id,
            "login_id": target.login_id, "email": target.email, "phone": target.phone, "role": target.role,
            "ward": target.ward, "account_status": target.account_status, "is_active": bool(target.is_active),
            "is_verified": bool(target.is_verified), "mfa_enabled": bool(target.mfa_enabled),
            "created_at": target.created_at, "activated_at": target.activated_at,
            "suspended_at": target.suspended_at, "deactivated_at": target.deactivated_at}


@router.get("/accounts/{user_id}/history")
def get_account_history(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)):
    require_municipal_admin(current_admin)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Account not found.")
    _authorize_account_view(db, current_admin, target)
    events = db.query(SecurityAuditEvent).filter(SecurityAuditEvent.target_user_id == target.id).order_by(SecurityAuditEvent.created_at.desc()).limit(250).all()
    return [{"id": event.id, "actor_employee_id": event.actor_employee_id, "action": event.action,
             "details": event.details, "created_at": event.created_at} for event in events]


@router.get("/audit")
def get_security_audit(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin_user),
):
    limit = min(max(limit, 1), 500)
    events = db.query(SecurityAuditEvent).order_by(SecurityAuditEvent.created_at.desc()).limit(limit).all()
    return [
        {
            "id": event.id, "actor_employee_id": event.actor_employee_id,
            "target_employee_id": event.target_employee_id, "action": event.action,
            "details": event.details, "created_at": event.created_at,
        }
        for event in events
    ]


@router.get("/super-admin/citizens")
def list_governance_citizens(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin_user),
):
    """Return a safe citizen directory for the Super Admin governance portal."""
    citizens = db.query(User).filter(User.role == "citizen").order_by(User.created_at.desc()).all()
    linked_ids = {
        user_id for (user_id,) in db.query(WhatsAppCitizen.user_id)
        .filter(WhatsAppCitizen.user_id.isnot(None), WhatsAppCitizen.is_authorized.is_(True))
        .all()
    }
    complaint_counts = dict(
        db.query(Complaint.citizen_id, func.count(Complaint.id))
        .filter(Complaint.citizen_id.isnot(None))
        .group_by(Complaint.citizen_id)
        .all()
    )
    return [
        {
            "id": citizen.id,
            "full_name": citizen.full_name,
            "email": citizen.email,
            "phone": citizen.phone,
            "login_id": citizen.login_id,
            "ward": citizen.ward,
            "account_status": citizen.account_status,
            "is_active": bool(citizen.is_active),
            "is_verified": bool(citizen.is_verified),
            "whatsapp_linked": citizen.id in linked_ids,
            "complaint_count": complaint_counts.get(citizen.id, 0),
            "created_at": citizen.created_at,
        }
        for citizen in citizens
    ]


@router.get("/super-admin/citizens/{citizen_id}/complaints")
def list_governance_citizen_complaints(
    citizen_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin_user),
):
    """Return the citizen's own complaint history without tracking credentials."""
    citizen = db.query(User).filter(User.id == citizen_id, User.role == "citizen").first()
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found.")
    return ComplaintService.get_user_complaints(db, citizen.id)


@router.get("/super-admin/tasks")
def list_governance_tasks(
    status_filter: str = "all",
    limit: int = 500,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin_user),
):
    """Read-only task monitoring, including lifecycle state counts and history."""
    allowed = {
        "Pending", "Accepted", "In Progress", "Evidence Submitted",
        "Pending Verification", "Requires Rework", "Completed", "Cancelled",
    }
    if status_filter != "all" and status_filter not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported task status.")
    limit = min(max(limit, 1), 1000)
    counts = dict(
        db.query(DriverTask.status, func.count(DriverTask.id))
        .group_by(DriverTask.status)
        .all()
    )
    query = db.query(DriverTask)
    if status_filter != "all":
        query = query.filter(DriverTask.status == status_filter)
    tasks = query.order_by(DriverTask.updated_at.desc(), DriverTask.id.desc()).limit(limit).all()
    return {
        "counts": {status: counts.get(status, 0) for status in sorted(allowed)},
        "total": sum(counts.values()),
        "tasks": [verification_detail(db, task) for task in tasks],
        "limit": limit,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Smart Bin Telemetry
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/bins", response_model=BinTelemetrySummary)
def get_bin_telemetry(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Returns smart bin telemetry: fill levels, capacities, locations, critical alerts."""
    return AdminService.get_bin_telemetry(db, ward_scope=_collector_ward(current_admin))


@router.patch("/bins/{bin_id}", response_model=BinResponse)
def update_bin(
    bin_id: int,
    payload: BinFillUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Admin updates a bin's fill level (e.g., after manual collection or sensor sync)."""
    if current_admin.role.lower() == "collector" and payload.is_active is not None:
        raise HTTPException(status_code=403, detail="Collectors may report fill levels but cannot change bin activation.")
    return AdminService.update_bin_fill(
        db, bin_id, payload.fill_level_pct, payload.is_active,
        ward_scope=_collector_ward(current_admin),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Returns aggregated analytics: ward breakdown, monthly trends, waste type distribution."""
    return AdminService.get_analytics(db, ward_scope=_collector_ward(current_admin))


# ─────────────────────────────────────────────────────────────────────────────
# Notifications & Broadcasts
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/notifications", response_model=List[NotificationResponse])
def get_notifications(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Returns system notifications and broadcast history for admin view."""
    require_municipal_admin(current_admin)
    return AdminService.get_notifications(db)


@router.post("/notifications/broadcast", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
def send_broadcast(
    payload: BroadcastRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Admin sends a broadcast notification to drivers or all users."""
    require_municipal_admin(current_admin)
    try:
        return AdminService.send_broadcast(
            db,
            sender_id=current_admin.id,
            title=payload.title,
            message=payload.message,
            audience=payload.audience,
            priority=payload.priority
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Marks a notification as read."""
    require_municipal_admin(current_admin)
    from server.models.notification import Notification
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    notif.is_read = True
    db.commit()
    return {"success": True, "id": notification_id}


# ─────────────────────────────────────────────────────────────────────────────
# User Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[AdminUserResponse])
def get_all_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Returns all users in the system (citizens, drivers, collectors, admins)."""
    require_municipal_admin(current_admin)
    return AdminService.get_all_users(db)
