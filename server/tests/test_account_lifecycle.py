import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from server.database.db import SessionLocal
from server.models.account_invitation import AccountInvitation
from server.models.complaint import Complaint
from server.models.security_audit_event import SecurityAuditEvent
from server.models.task import DriverTask
from server.models.task_evidence import TaskEvidence
from server.models.task_event import TaskEvent
from server.models.user import User
from server.models.mobile_otp import MobileOtpToken
from server.models.whatsapp_link_token import WhatsAppLinkToken
from server.models.whatsapp_registration_challenge import WhatsAppRegistrationChallenge
from server.models.whatsapp_session import WhatsAppCitizen
from server.routes.admin import get_account_details, get_account_history, update_account_status
from server.services.admin_service import AdminService
from server.schemas.admin import AccountStatusRequest
from server.schemas.auth import LoginRequest
from server.services.auth_service import AuthService, hash_otp
from server.services.iam_service import get_valid_invitation, issue_invitation
from server.services.staff_provisioning_service import reset_staff_password
from server.services.whatsapp_link_service import WhatsAppLinkService
from server.services.whatsapp_service import WhatsAppService
from server.services.whatsapp_verification_service import WhatsAppVerificationService
from server.tests.iam_test_helpers import admin_access_token
from server.utils.security import get_current_user_optional, hash_password


@pytest.fixture
def lifecycle_context():
    db = SessionLocal()
    super_admin = db.query(User).filter(User.email == "super-admin@example.test").one()
    created_ids = []

    def create(role, **kwargs):
        key = uuid.uuid4().hex[:12]
        values = {
            "full_name": f"Lifecycle {role.title()}",
            "email": f"lifecycle-{key}@example.test",
            "employee_id": f"LIFE-{role[:3].upper()}-{key}",
            "login_id": f"LIFE-{key}",
            "phone": f"8{int(key[:9], 16) % 1_000_000_000:09d}",
            "hashed_password": hash_password("ValidPassword123!"),
            "role": role,
            "ward": "Ward A",
            "is_active": True,
            "is_verified": True,
            "account_status": "active",
        }
        values.update(kwargs)
        user = User(**values)
        db.add(user)
        db.commit()
        db.refresh(user)
        created_ids.append(user.id)
        return user

    try:
        yield db, create, super_admin
    finally:
        if created_ids:
            db.query(SecurityAuditEvent).filter(SecurityAuditEvent.target_user_id.in_(created_ids)).delete(synchronize_session=False)
            db.query(AccountInvitation).filter(AccountInvitation.user_id.in_(created_ids)).delete(synchronize_session=False)
            db.query(WhatsAppCitizen).filter(WhatsAppCitizen.user_id.in_(created_ids)).delete(synchronize_session=False)
            db.query(WhatsAppLinkToken).filter(WhatsAppLinkToken.user_id.in_(created_ids)).delete(synchronize_session=False)
            db.query(MobileOtpToken).filter(MobileOtpToken.phone.in_(db.query(User.phone).filter(User.id.in_(created_ids)))).delete(synchronize_session=False)
            db.query(WhatsAppRegistrationChallenge).filter(WhatsAppRegistrationChallenge.phone.in_(db.query(User.phone).filter(User.id.in_(created_ids)))).delete(synchronize_session=False)
            db.query(TaskEvidence).filter(TaskEvidence.driver_id.in_(created_ids)).delete(synchronize_session=False)
            db.query(TaskEvent).filter(TaskEvent.actor_user_id.in_(created_ids)).delete(synchronize_session=False)
            db.query(DriverTask).filter(DriverTask.driver_id.in_(created_ids)).delete(synchronize_session=False)
            db.query(Complaint).filter(Complaint.citizen_id.in_(created_ids)).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(created_ids)).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_suspension_revokes_sessions_and_reactivation_is_controlled(lifecycle_context):
    db, create, super_admin = lifecycle_context
    target = create("driver")
    stale_token = admin_access_token(target)
    result = update_account_status(
        target.id, AccountStatusRequest(account_status="suspended", reason="Safety review"), db, super_admin,
    )
    assert result["account_status"] == "suspended"
    db.refresh(target)
    assert not target.is_active and target.session_version == 1
    assert get_current_user_optional(stale_token, db) is None
    assert db.query(SecurityAuditEvent).filter_by(target_user_id=target.id, action="account_suspended").one().details == "Safety review"
    with pytest.raises(HTTPException) as suspended_login:
        AuthService.login_user(db, LoginRequest(email=target.employee_id, password="ValidPassword123!", role="driver"))
    assert suspended_login.value.status_code == 403
    resumed = update_account_status(target.id, AccountStatusRequest(account_status="active"), db, super_admin)
    assert resumed["account_status"] == "active"
    db.refresh(target)
    assert target.account_status == "active" and target.is_active and target.session_version == 2
    assert get_current_user_optional(stale_token, db) is None


def test_retirement_is_irreversible_blocks_auth_and_preserves_history(lifecycle_context, monkeypatch):
    db, create, super_admin = lifecycle_context
    citizen = create("citizen")
    complaint = Complaint(
        tracking_number=f"LIFE-{uuid.uuid4().hex[:12]}", tracking_secret="test-secret",
        citizen_id=citizen.id, ward="Ward A", location_address="Historic location",
        waste_type="Mixed Waste", status="Pending",
    )
    db.add(complaint)
    db.flush()
    driver = create("driver")
    task = DriverTask(driver_id=driver.id, complaint_id=complaint.id, location_name="Historic task")
    db.add(task)
    db.flush()
    evidence = TaskEvidence(task_id=task.id, complaint_id=complaint.id, driver_id=driver.id, after_image_ref="test/evidence.jpg", status="submitted")
    task_event = TaskEvent(task_id=task.id, actor_user_id=driver.id, actor_role="driver", event_type="evidence_submitted")
    db.add_all([evidence, task_event])
    otp = MobileOtpToken(phone=citizen.phone, otp_hash="f" * 64, purpose="login", attempts=0, max_attempts=5, expires_at=datetime.now(timezone.utc) + timedelta(minutes=3))
    challenge = WhatsAppRegistrationChallenge(phone=citizen.phone, otp_hash="f" * 64, status="PENDING", expires_at=datetime.now(timezone.utc) + timedelta(minutes=3))
    db.add_all([otp, challenge])
    link = WhatsAppLinkService.generate_link_code(db, citizen)
    db.add(WhatsAppCitizen(phone_number=f"91{citizen.phone}", user_id=citizen.id, is_authorized=True))
    db.commit()
    stale_token = admin_access_token(citizen)

    retired = update_account_status(
        citizen.id, AccountStatusRequest(account_status="retired", reason="Data retention request"), db, super_admin,
    )
    assert retired["account_status"] == "retired"
    db.refresh(citizen)
    assert citizen.account_status == "retired" and not citizen.is_active
    assert get_current_user_optional(stale_token, db) is None
    assert db.query(Complaint).filter(Complaint.id == complaint.id).one().citizen_id == citizen.id
    assert db.query(DriverTask).filter(DriverTask.id == task.id).one().complaint_id == complaint.id
    assert db.query(TaskEvidence).filter_by(id=evidence.id).one().driver_id == driver.id
    assert db.query(TaskEvent).filter_by(id=task_event.id).one().event_type == "evidence_submitted"
    assert db.query(MobileOtpToken).filter_by(id=otp.id).one().consumed_at is not None
    assert db.query(WhatsAppRegistrationChallenge).filter_by(id=challenge.id).one().status == "EXPIRED"
    assert db.query(WhatsAppCitizen).filter_by(user_id=citizen.id).one().is_authorized is False
    monkeypatch.setattr(WhatsAppService, "send_meta_whatsapp", staticmethod(lambda *args, **kwargs: None))
    verify_command = WhatsAppService.handle_incoming_message(
        db, sender_phone=f"+91{citizen.phone}", message_type="text", text_body="VERIFY 123456",
    )
    assert verify_command["status"] == "account_unavailable"
    assert WhatsAppLinkService.redeem_link_code(db, link["link_code"], f"91{citizen.phone}") is None
    with pytest.raises(HTTPException) as otp_error:
        AuthService.send_otp(db, citizen.phone, purpose="login")
    assert otp_error.value.status_code == 403
    with pytest.raises(HTTPException) as login_error:
        AuthService.login_user(db, LoginRequest(email=citizen.login_id, password="ValidPassword123!", role="citizen"))
    assert login_error.value.status_code == 403
    assert db.query(SecurityAuditEvent).filter_by(target_user_id=citizen.id, action="account_retired").count() == 1
    assert db.query(User).filter_by(employee_id=driver.employee_id, login_id=driver.login_id).count() == 1
    assert db.query(AccountInvitation).filter_by(user_id=driver.id).count() == 0
    details = get_account_details(citizen.id, db, super_admin)
    assert "hashed_password" not in details and "mfa_secret_enc" not in details
    history = get_account_history(citizen.id, db, super_admin)
    assert history[0]["action"] == "account_retired"
    with pytest.raises(HTTPException) as cannot_reactivate:
        update_account_status(citizen.id, AccountStatusRequest(account_status="active"), db, super_admin)
    assert cannot_reactivate.value.status_code == 409


def test_municipal_admin_lifecycle_access_is_ward_scoped(lifecycle_context):
    db, create, super_admin = lifecycle_context
    admin = create("admin", ward="Ward A")
    local_driver = create("driver", ward="Ward A")
    local_collector = create("collector", ward="Ward A")
    remote_collector = create("collector", ward="Ward B")
    other_admin = create("admin", ward="Ward A")
    citizen = create("citizen", ward="Ward A")
    collector = create("collector", ward="Ward A")
    result = update_account_status(
        local_driver.id, AccountStatusRequest(account_status="suspended", reason="Ward review"), db, admin,
    )
    assert result["account_status"] == "suspended"
    staff_rows = AdminService.get_all_drivers(db, ward_scope=admin.ward, include_collectors=True)
    assert {row.id for row in staff_rows} == {local_driver.id, local_collector.id, collector.id}
    with pytest.raises(HTTPException) as denied:
        update_account_status(remote_collector.id, AccountStatusRequest(account_status="suspended", reason="Ward review"), db, admin)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as details_denied:
        get_account_details(remote_collector.id, db, admin)
    assert details_denied.value.status_code == 403
    with pytest.raises(HTTPException) as collector_denied:
        update_account_status(local_driver.id, AccountStatusRequest(account_status="suspended", reason="Not an admin"), db, collector)
    assert collector_denied.value.status_code == 403
    for protected in (other_admin, citizen, super_admin):
        with pytest.raises(HTTPException) as protected_denied:
            update_account_status(protected.id, AccountStatusRequest(account_status="suspended", reason="Not in scope"), db, admin)
        assert protected_denied.value.status_code == 403


def test_retired_account_cannot_activate_from_existing_invitation(lifecycle_context):
    db, create, super_admin = lifecycle_context
    target = create("collector", is_active=False, account_status="pending")
    raw_token = issue_invitation(db, target, "collector", super_admin)
    db.commit()
    update_account_status(target.id, AccountStatusRequest(account_status="retired", reason="Invitation withdrawn"), db, super_admin)
    assert db.query(AccountInvitation).filter_by(user_id=target.id).one().revoked_at is not None
    with pytest.raises(HTTPException) as reset_error:
        reset_staff_password(db, super_admin, target)
    assert reset_error.value.status_code == 409
    with pytest.raises(HTTPException) as activation_error:
        get_valid_invitation(db, raw_token, role="collector")
    assert activation_error.value.status_code == 400


def test_active_citizen_whatsapp_verify_and_link_still_work(lifecycle_context):
    db, create, _ = lifecycle_context
    citizen = create("citizen")
    code = "123456"
    challenge = WhatsAppRegistrationChallenge(
        phone=citizen.phone, otp_hash=hash_otp(code), status="PENDING",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=3),
    )
    challenge.set_profile({"full_name": citizen.full_name, "email": citizen.email, "ward": citizen.ward})
    db.add(challenge)
    db.commit()
    verify_result = WhatsAppVerificationService.process_verification_message(
        db, sender_phone=f"+91{citizen.phone}", raw_code=code, preferred_language="en",
    )
    assert verify_result["verified"] is True
    linked_identity = db.query(WhatsAppCitizen).filter_by(user_id=citizen.id).one()
    assert linked_identity.is_authorized is True
    link = WhatsAppLinkService.generate_link_code(db, citizen)
    assert WhatsAppLinkService.redeem_link_code(db, link["link_code"], f"91{citizen.phone}").id == citizen.id
