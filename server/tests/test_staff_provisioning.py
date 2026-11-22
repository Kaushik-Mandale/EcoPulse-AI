import base64
import hashlib
import hmac
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import server.models
from server.database.db import Base
from server.models.mobile_otp import MobileOtpToken
from server.models.security_audit_event import SecurityAuditEvent
from server.models.user import User
from server.models.municipality import Municipality
from server.models.ward import Ward
from server.routes.auth import (
    MfaEnrollmentConfirmRequest,
    MfaEnrollmentStartRequest,
    StaffPhoneVerificationConfirmRequest,
    StaffPhoneVerificationStartRequest,
    change_initial_super_admin_password,
    confirm_mfa_enrollment,
    confirm_provisioned_driver_phone_verification,
    send_provisioned_driver_phone_verification,
    start_mfa_enrollment,
)
from server.schemas.admin import StaffProvisionRequest
from server.schemas.auth import InitialPasswordChangeRequest, LoginRequest
from server.services.admin_service import AdminService
from server.services.auth_service import AuthService, hash_otp
from server.services.iam_service import _totp_code
from server.services.staff_provisioning_service import (
    _temporary_password,
    provision_staff_account,
    reset_staff_password,
)
from server.utils.config import config
from server.utils.security import create_access_token, get_current_user_optional, hash_password, verify_password


@pytest.fixture
def staff_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'staff-provisioning.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    municipality = Municipality(code="TEST", name="Test Municipality", is_active=True)
    db.add(municipality)
    db.flush()
    db.add_all([
        Ward(municipality_id=municipality.id, ward_number="A", display_name="Ward A", is_active=True),
        Ward(municipality_id=municipality.id, ward_number="B", display_name="Ward B", is_active=True),
    ])
    db.commit()
    try:
        yield db, factory, engine
    finally:
        db.close()
        engine.dispose()


def _actor(db, role="admin", *, super_admin=False, ward=None):
    actor = User(
        full_name="Provisioning Operator",
        email=f"operator-{role}-{int(super_admin)}-{ward or 'global'}@example.test",
        employee_id=f"OP-{role.upper()}-{int(super_admin)}-{(ward or 'GLOBAL').upper().replace(' ', '')}",
        hashed_password=hash_password("OperatorSecurePassword!"),
        role=role,
        is_super_admin=super_admin,
        is_active=True,
        is_verified=True,
        account_status="active",
        mfa_enabled=role in {"admin", "collector"},
        ward=ward,
    )
    db.add(actor)
    db.commit()
    return actor


def _payload(role, suffix, *, employee_id=None, ward="Ward A"):
    return StaffProvisionRequest(
        full_name=f"New {role.title()} {suffix}",
        role=role,
        phone=f"987650{int(suffix[-4:], 16) % 10000:04d}",
        email=f"{role}-{suffix}@example.test",
        employee_id=employee_id,
        ward_id=(2 if ward == "Ward B" else 1) if role in {"driver", "collector"} and ward.strip() else None,
        municipality_id=1 if role == "admin" else None,
    )


def test_temporary_password_is_16_characters_with_all_required_classes_and_random_variation():
    passwords = [_temporary_password() for _ in range(64)]

    assert all(len(password) == 16 for password in passwords)
    assert all(any(char.isupper() for char in password) for password in passwords)
    assert all(any(char.islower() for char in password) for password in passwords)
    assert all(any(char.isdigit() for char in password) for password in passwords)
    assert all(any(not char.isalnum() for char in password) for password in passwords)
    assert len(set(passwords)) > 60
    assert len({password[0] for password in passwords}) > 8


def test_temporary_password_randomizes_final_character_order_with_system_random(monkeypatch):
    class ShuffleSpy:
        before_shuffle = None

        def shuffle(self, values):
            self.before_shuffle = list(values)
            values.reverse()

    spy = ShuffleSpy()
    monkeypatch.setattr(secrets, "SystemRandom", lambda: spy)

    password = _temporary_password()

    assert spy.before_shuffle is not None
    assert password == "".join(reversed(spy.before_shuffle))


@pytest.mark.parametrize("role", ["admin", "driver", "collector"])
def test_super_admin_can_provision_all_staff_roles(staff_db, monkeypatch, role):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    official_id = f"OFFICIAL-{role.upper()}-01" if role == "admin" else None
    if official_id:
        monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)
    result = provision_staff_account(db, actor, _payload(role, "a101", employee_id=official_id))
    account = db.query(User).filter(User.id == result["id"]).one()

    assert account.role == role
    assert account.is_super_admin is False
    assert account.login_id.startswith({"admin": "ADM", "driver": "DRV", "collector": "COL"}[role])
    assert account.must_change_password is True
    assert account.employee_id == official_id
    assert len(result["temporary_password"]) == 16
    assert any(char.isupper() for char in result["temporary_password"])
    assert any(char.islower() for char in result["temporary_password"])
    assert any(char.isdigit() for char in result["temporary_password"])
    assert any(not char.isalnum() for char in result["temporary_password"])
    assert verify_password(result["temporary_password"], account.hashed_password)
    assert account.hashed_password != result["temporary_password"]
    assert all("temporary_password" not in row.model_dump() for row in AdminService.get_all_users(db))


@pytest.mark.parametrize("role", ["driver", "collector"])
def test_municipal_admin_can_provision_driver_and_collector_in_ward(staff_db, role):
    db, _, _ = staff_db
    actor = _actor(db, ward="Ward A")
    result = provision_staff_account(db, actor, _payload(role, "a201", ward="ward a"))
    account = db.query(User).filter(User.id == result["id"]).one()
    assert result["login_id"].startswith({"driver": "DRV", "collector": "COL"}[role])
    assert account.ward == "Ward A"
    assert account.is_verified is False if role == "driver" else account.is_verified is True


def test_municipal_admin_cannot_provision_admin_or_other_ward(staff_db, monkeypatch):
    db, _, _ = staff_db
    actor = _actor(db, ward="Ward A")
    admin_id = "ALLOWLISTED-ADMIN-01"
    monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)
    with pytest.raises(HTTPException) as denied_admin:
        provision_staff_account(db, actor, _payload("admin", "a301", employee_id=admin_id))
    assert denied_admin.value.status_code == 403
    with pytest.raises(HTTPException) as denied_ward:
        provision_staff_account(db, actor, _payload("driver", "a302", ward="Ward B"))
    assert denied_ward.value.status_code == 403
    assert db.query(User).filter(User.role == "driver").count() == 0


@pytest.mark.parametrize("role", ["driver", "collector", "citizen"])
def test_non_admin_roles_cannot_provision_staff(staff_db, role):
    db, _, _ = staff_db
    actor = _actor(db, role=role)
    with pytest.raises(HTTPException) as denied:
        provision_staff_account(db, actor, _payload("driver", "a401"))
    assert denied.value.status_code == 403


def test_arbitrary_unique_official_employee_id_and_required_ward(staff_db, monkeypatch):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)
    created = provision_staff_account(
        db, actor, _payload("admin", "a501", employee_id="ARBITRARY-OFFICIAL-EMPLOYEE-77"),
    )
    assert db.query(User).filter(User.id == created["id"]).one().employee_id == "ARBITRARY-OFFICIAL-EMPLOYEE-77"
    with pytest.raises(HTTPException) as missing_ward:
        provision_staff_account(db, actor, _payload("driver", "a502", ward=" "))
    assert missing_ward.value.status_code == 422
    assert db.query(User).filter(User.id != actor.id, User.role == "driver").count() == 0


def test_duplicate_official_employee_id_is_rejected_case_insensitively(staff_db, monkeypatch):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)
    provision_staff_account(db, actor, _payload("admin", "a511", employee_id="OFFICIAL-NEW-900"))

    with pytest.raises(HTTPException) as duplicate:
        provision_staff_account(db, actor, _payload("admin", "a512", employee_id="official-new-900"))

    assert duplicate.value.status_code == 409
    assert db.query(User).filter(func.lower(User.employee_id) == "official-new-900").count() == 1


def test_duplicate_contact_values_are_rejected(staff_db):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    db.add(User(
        full_name="Existing Citizen", role="citizen", email="taken@example.test",
        phone="+91 98765-01001", hashed_password=hash_password("CitizenPassword!123"),
    ))
    db.commit()
    with pytest.raises(HTTPException) as duplicate:
        provision_staff_account(db, actor, StaffProvisionRequest(
            full_name="Duplicate Phone", role="driver", phone="9876501001",
            email="new@example.test", ward_id=1,
        ))
    assert duplicate.value.status_code == 409
    assert db.query(User).filter(User.role == "driver").count() == 0


def test_login_ids_are_unique_and_account_audit_is_committed(staff_db):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    first = provision_staff_account(db, actor, _payload("driver", "a601"))
    second = provision_staff_account(db, actor, _payload("driver", "a602"))
    assert (first["login_id"], second["login_id"]) == ("DRV001", "DRV002")
    assert db.query(SecurityAuditEvent).filter(SecurityAuditEvent.action == "driver_account_provisioned").count() == 2


def test_super_admin_generated_municipal_admin_login_ids_are_unique_without_allowlist(staff_db, monkeypatch):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)

    first = provision_staff_account(db, actor, _payload("admin", "a611", employee_id="OFFICIAL-ADMIN-A"))
    second = provision_staff_account(db, actor, _payload("admin", "a612", employee_id="OFFICIAL-ADMIN-B"))

    assert first["login_id"] == "ADM001"
    assert second["login_id"] == "ADM002"
    assert first["login_id"] != first["employee_id"]
    assert db.query(User).filter(User.role == "admin", User.is_super_admin.is_(False)).count() == 2


def test_concurrent_staff_creation_retries_unique_login_collision(staff_db):
    db, factory, engine = staff_db
    actor = _actor(db, super_admin=True)
    actor_id = actor.id
    barrier = Barrier(2)

    def create(suffix):
        session = factory()
        try:
            operator = session.query(User).filter(User.id == actor_id).one()
            barrier.wait(timeout=5)
            return provision_staff_account(session, operator, _payload("driver", suffix))
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, ["a701", "a702"]))
    assert {result["login_id"] for result in results} == {"DRV001", "DRV002"}
    verify = factory()
    try:
        assert verify.query(User).filter(User.role == "driver").count() == 2
    finally:
        verify.close()


def test_reset_issues_one_time_credentials_and_revokes_sessions(staff_db):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    created = provision_staff_account(db, actor, _payload("collector", "a801"))
    target = db.query(User).filter(User.id == created["id"]).one()
    target.session_version = 4
    db.commit()

    reset = reset_staff_password(db, actor, target)

    assert reset["temporary_password"] != created["temporary_password"]
    assert target.must_change_password is True
    assert target.session_version == 5
    assert verify_password(reset["temporary_password"], target.hashed_password)
    assert db.query(SecurityAuditEvent).filter(SecurityAuditEvent.action == "staff_temporary_password_issued").count() == 1
    assert "temporary_password" not in AdminService.get_all_drivers(db)[0].model_dump()


def test_expired_temporary_password_is_rejected_and_reset_starts_new_window(staff_db):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    created = provision_staff_account(db, actor, _payload("driver", "a811"))
    driver = db.query(User).filter(User.id == created["id"]).one()
    driver.temporary_password_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    with pytest.raises(HTTPException) as expired_login:
        AuthService.login_user(db, LoginRequest(
            email=created["login_id"], password=created["temporary_password"], role="driver",
        ))
    assert expired_login.value.status_code == 403
    assert expired_login.value.detail["code"] == "TEMPORARY_CREDENTIAL_EXPIRED"

    with pytest.raises(HTTPException) as expired_rotation:
        change_initial_super_admin_password(InitialPasswordChangeRequest(
            login_id=created["login_id"], current_password=created["temporary_password"],
            new_password="DriverRotatedPassword!9",
        ), db)
    assert expired_rotation.value.detail["code"] == "TEMPORARY_CREDENTIAL_EXPIRED"

    renewed = reset_staff_password(db, actor, driver)
    renewed_expiry = renewed["temporary_password_expires_at"]
    if renewed_expiry.tzinfo is None:
        renewed_expiry = renewed_expiry.replace(tzinfo=timezone.utc)
    assert renewed_expiry > datetime.now(timezone.utc)
    with pytest.raises(HTTPException) as required_rotation:
        AuthService.login_user(db, LoginRequest(
            email=created["login_id"], password=renewed["temporary_password"], role="driver",
        ))
    assert required_rotation.value.detail["code"] == "PASSWORD_CHANGE_REQUIRED"


@pytest.mark.parametrize("role", ["admin", "driver", "collector"])
def test_suspended_staff_cannot_continue_onboarding(staff_db, monkeypatch, role):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    employee_id = f"ALLOW-{role.upper()}-SUSP" if role == "admin" else None
    if employee_id:
        monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)
    created = provision_staff_account(
        db, actor, _payload(role, "a821", employee_id=employee_id),
    )
    target = db.query(User).filter(User.id == created["id"]).one()
    target.is_active = False
    target.account_status = "suspended"
    db.commit()

    with pytest.raises(HTTPException) as login_denied:
        AuthService.login_user(db, LoginRequest(
            email=created["login_id"], password=created["temporary_password"], role=role,
        ))
    assert login_denied.value.status_code == 403
    with pytest.raises(HTTPException) as rotation_denied:
        change_initial_super_admin_password(InitialPasswordChangeRequest(
            login_id=created["login_id"], current_password=created["temporary_password"],
            new_password="ValidOnboardingPassword!9",
        ), db)
    assert rotation_denied.value.status_code == 401


def test_client_cannot_choose_a_different_account_role(staff_db):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    created = provision_staff_account(db, actor, _payload("driver", "a831"))
    with pytest.raises(HTTPException) as denied:
        AuthService.login_user(db, LoginRequest(
            email=created["login_id"], password=created["temporary_password"], role="collector",
        ))
    assert denied.value.status_code == 401


@pytest.mark.parametrize("role", ["admin", "collector"])
def test_direct_api_token_is_rejected_until_privileged_onboarding_completes(staff_db, monkeypatch, role):
    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    employee_id = f"ALLOW-{role.upper()}-TOKEN" if role == "admin" else None
    if employee_id:
        monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)
    created = provision_staff_account(
        db, actor, _payload(role, "a841", employee_id=employee_id),
    )
    user = db.query(User).filter(User.id == created["id"]).one()
    token = create_access_token({
        "sub": created["login_id"], "id": user.id, "role": role,
        "sv": user.session_version, "sid": "privileged-onboarding-bypass-test",
        "mfa": True,
    })

    assert get_current_user_optional(token, db) is None


def test_driver_phone_verification_then_required_password_rotation(staff_db):
    db, _, engine = staff_db
    actor = _actor(db, super_admin=True)
    created = provision_staff_account(db, actor, _payload("driver", "a901"))
    driver = db.query(User).filter(User.id == created["id"]).one()
    with pytest.raises(HTTPException) as rotation_required:
        AuthService.login_user(db, LoginRequest(email=created["login_id"], password=created["temporary_password"], role="driver"))
    assert rotation_required.value.status_code == 428
    assert rotation_required.value.detail["code"] == "PASSWORD_CHANGE_REQUIRED"
    bypass_token = create_access_token({
        "sub": created["login_id"], "id": driver.id, "role": "driver",
        "sv": driver.session_version, "sid": "onboarding-bypass-test",
    })
    assert get_current_user_optional(bypass_token, db) is None

    # Direct phone-verification requests cannot skip the required password rotation.
    with pytest.raises(HTTPException) as otp_too_early:
        send_provisioned_driver_phone_verification(
            StaffPhoneVerificationStartRequest(login_id=created["login_id"], password=created["temporary_password"]),
            SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")),
            db,
        )
    assert otp_too_early.value.status_code == 401

    with pytest.raises(HTTPException) as weak_password:
        change_initial_super_admin_password(InitialPasswordChangeRequest(
            login_id=created["login_id"], current_password=created["temporary_password"],
            new_password="alllowercasepassword!",
        ), db)
    assert weak_password.value.status_code == 400
    assert driver.must_change_password is True

    new_password = "DriverRotatedPassword!9"
    changed = change_initial_super_admin_password(
        InitialPasswordChangeRequest(login_id=created["login_id"], current_password=created["temporary_password"], new_password=new_password),
        db,
    )
    assert changed["success"] is True
    assert driver.must_change_password is False
    assert driver.temporary_password_expires_at is None
    with pytest.raises(HTTPException) as old_password:
        AuthService.login_user(db, LoginRequest(email=created["login_id"], password=created["temporary_password"], role="driver"))
    assert old_password.value.status_code == 401
    with pytest.raises(HTTPException) as not_verified:
        AuthService.login_user(db, LoginRequest(email=created["login_id"], password=new_password, role="driver"))
    assert not_verified.value.detail["code"] == "PHONE_VERIFICATION_REQUIRED"

    otp = "123456"
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = MobileOtpToken(
        phone=driver.phone, otp_hash=hash_otp(otp), purpose="activation",
        attempts=0, max_attempts=5, expires_at=expires,
    )
    db.add(token)
    db.flush()
    driver.created_by_id = actor.id
    token_id = str(token.id)
    expires_seconds = str(int(expires.timestamp()))
    challenge_payload = f"{token_id}:{driver.phone}:activation:{expires_seconds}"
    signature = hmac.new(
        (config.SECRET_KEY or "ecopulse-default-secret-key-change-in-prod").encode(),
        challenge_payload.encode(), hashlib.sha256,
    ).hexdigest()[:24]
    challenge_id = base64.urlsafe_b64encode(f"{challenge_payload}:{signature}".encode()).decode()
    db.commit()

    with pytest.raises(HTTPException) as invalid_otp:
        confirm_provisioned_driver_phone_verification(
            StaffPhoneVerificationConfirmRequest(
                login_id=created["login_id"], password=new_password,
                otp="000000", challenge_id=challenge_id,
            ),
            db,
        )
    assert invalid_otp.value.status_code == 400

    verified = confirm_provisioned_driver_phone_verification(
        StaffPhoneVerificationConfirmRequest(
            login_id=created["login_id"], password=new_password,
            otp=otp, challenge_id=challenge_id,
        ),
        db,
    )
    assert verified["success"] is True
    assert driver.is_verified is True
    with pytest.raises(HTTPException) as replayed_challenge:
        confirm_provisioned_driver_phone_verification(
            StaffPhoneVerificationConfirmRequest(
                login_id=created["login_id"], password=new_password,
                otp=otp, challenge_id=challenge_id,
            ),
            db,
        )
    assert replayed_challenge.value.status_code == 401
    response = AuthService.login_user(db, LoginRequest(email=created["login_id"], password=new_password, role="driver"))
    assert response.access_token


def test_locked_provisioned_driver_cannot_request_activation_otp(staff_db):
    db, _, _ = staff_db
    driver = User(
        full_name="Locked Driver",
        role="driver",
        login_id="DRV998",
        phone="9876509998",
        hashed_password=hash_password("TemporaryPassword!9"),
        must_change_password=True,
        is_active=True,
        is_verified=False,
        is_locked=True,
        account_status="active",
    )
    db.add(driver)
    db.commit()

    with pytest.raises(HTTPException) as rejected:
        AuthService.send_otp(db, driver.phone, purpose="activation")

    assert rejected.value.status_code == 404


@pytest.mark.parametrize("role", ["admin", "collector"])
def test_privileged_staff_must_rotate_password_and_enroll_mfa(staff_db, monkeypatch, role):
    from cryptography.fernet import Fernet

    db, _, _ = staff_db
    actor = _actor(db, super_admin=True)
    employee_id = f"OFFICIAL-{role.upper()}-MFA" if role == "admin" else None
    monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    created = provision_staff_account(
        db, actor,
        _payload(role, "ab01", employee_id=employee_id if role == "admin" else None),
    )
    with pytest.raises(HTTPException) as rotation_required:
        AuthService.login_user(db, LoginRequest(email=created["login_id"], password=created["temporary_password"], role=role))
    assert rotation_required.value.status_code == 428

    password = "PrivilegedRotatedPassword!9"
    change_initial_super_admin_password(
        InitialPasswordChangeRequest(login_id=created["login_id"], current_password=created["temporary_password"], new_password=password),
        db,
    )
    with pytest.raises(HTTPException) as mfa_required:
        AuthService.login_user(db, LoginRequest(email=created["login_id"], password=password, role=role))
    assert mfa_required.value.status_code == 403

    with pytest.raises(HTTPException) as onboarding_guard:
        start_mfa_enrollment(MfaEnrollmentStartRequest(employee_id=created["login_id"], password=created["temporary_password"]), db)
    assert onboarding_guard.value.status_code == 401

    enrollment = start_mfa_enrollment(MfaEnrollmentStartRequest(employee_id=created["login_id"], password=password), db)
    current_step = int(datetime.now(timezone.utc).timestamp() // 30)
    code = _totp_code(enrollment["secret"], current_step)

    account = db.query(User).filter(User.id == created["id"]).one()
    account.mfa_enrollment_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    with pytest.raises(HTTPException) as expired_enrollment:
        confirm_mfa_enrollment(
            MfaEnrollmentConfirmRequest(employee_id=created["login_id"], password=password, code=code), db,
        )
    assert expired_enrollment.value.status_code == 410
    assert account.mfa_secret_enc is None

    enrollment = start_mfa_enrollment(MfaEnrollmentStartRequest(employee_id=created["login_id"], password=password), db)
    current_step = int(datetime.now(timezone.utc).timestamp() // 30)
    code = _totp_code(enrollment["secret"], current_step)
    with pytest.raises(HTTPException) as invalid_code:
        confirm_mfa_enrollment(
            MfaEnrollmentConfirmRequest(employee_id=created["login_id"], password=password, code="invalid"), db,
        )
    assert invalid_code.value.status_code == 400
    assert db.query(User).filter(User.id == created["id"]).one().mfa_enabled is False
    confirmation = confirm_mfa_enrollment(
        MfaEnrollmentConfirmRequest(employee_id=created["login_id"], password=password, code=code), db,
    )
    assert confirmation["success"] is True
    with pytest.raises(HTTPException) as replayed_enrollment:
        confirm_mfa_enrollment(
            MfaEnrollmentConfirmRequest(employee_id=created["login_id"], password=password, code=code), db,
        )
    assert replayed_enrollment.value.status_code == 401
    fresh_code = _totp_code(enrollment["secret"], current_step + 1)
    login = AuthService.login_user(db, LoginRequest(email=created["login_id"], password=password, role=role, mfa_code=fresh_code))
    assert login.access_token
    with pytest.raises(HTTPException) as replayed_login_code:
        AuthService.login_user(db, LoginRequest(email=created["login_id"], password=password, role=role, mfa_code=fresh_code))
    assert replayed_login_code.value.status_code == 401
