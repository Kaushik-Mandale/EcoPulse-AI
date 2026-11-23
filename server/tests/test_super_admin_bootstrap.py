from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from types import SimpleNamespace
import time
from cryptography.fernet import Fernet
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

import server.models  # register all tables for isolated disposable SQLite databases
from server.database.db import Base
from server.models.user import User
from server.routes.auth import (
    MfaEnrollmentConfirmRequest,
    MfaEnrollmentStartRequest,
    change_initial_super_admin_password,
    confirm_mfa_enrollment,
    start_mfa_enrollment,
)
from server.scripts import bootstrap_super_admin
from server.scripts.bootstrap_super_admin import BootstrapConflict, provision_super_admin
from server.scripts.recover_super_admin import reissue_expired_bootstrap_password
from server.schemas.auth import InitialPasswordChangeRequest, LoginRequest
from server.services.auth_service import AuthService
from server.services.iam_service import _totp_code
from server.utils.security import hash_password


def _database(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'bootstrap-test.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _identity(employee_id="OFFICIAL-SUP-04"):
    return {
        "employee_id": employee_id,
        "login_id": "SUP04",
        "full_name": "supreme",
        "email": "sup04@example.test",
        "phone": "9876500044",
        "password": "OneTimeBootstrapPassword!9",
    }


def test_bootstrap_password_prompt_refuses_non_tty(monkeypatch):
    monkeypatch.setattr(bootstrap_super_admin.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(
        bootstrap_super_admin.getpass,
        "getpass",
        lambda _: pytest.fail("Password prompt must not fall back to echoing stdin."),
    )
    with pytest.raises(RuntimeError, match="terminal is required"):
        bootstrap_super_admin._read_password_no_echo("password: ")


@pytest.mark.parametrize("conflict_field", ["employee_id", "login_id", "email", "phone"])
def test_bootstrap_refuses_identity_conflicts_without_mutating_citizen(tmp_path, monkeypatch, conflict_field):
    engine, sessions = _database(tmp_path)
    identity = _identity()
    monkeypatch.setenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", identity["employee_id"])
    db = sessions()
    existing_data = {
        "full_name": "Existing Citizen",
        "email": "other@example.test",
        "phone": "9876500001",
        "employee_id": None,
        "login_id": None,
        "role": "citizen",
        "hashed_password": hash_password("CitizenPassword123!"),
        "is_super_admin": False,
    }
    existing_data[conflict_field] = {
        "employee_id": identity["employee_id"],
        "login_id": identity["login_id"],
        "email": identity["email"],
        "phone": "+91 98765-00044",
    }[conflict_field]
    citizen = User(**existing_data)
    db.add(citizen)
    db.commit()
    original = (citizen.full_name, citizen.role, citizen.hashed_password, citizen.phone, citizen.employee_id)

    with pytest.raises(BootstrapConflict):
        provision_super_admin(db, **identity)

    db.expire_all()
    persisted = db.query(User).filter(User.id == citizen.id).one()
    assert (persisted.full_name, persisted.role, persisted.hashed_password, persisted.phone, persisted.employee_id) == original
    assert db.query(User).filter(User.is_super_admin.is_(True)).count() == 0
    db.close()
    engine.dispose()


def test_bootstrap_is_idempotent_and_never_resets_password(tmp_path, monkeypatch):
    engine, sessions = _database(tmp_path)
    identity = _identity()
    monkeypatch.setenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", identity["employee_id"])
    db = sessions()
    assert provision_super_admin(db, **identity) is True
    account = db.query(User).filter(User.is_super_admin.is_(True)).one()
    original_hash = account.hashed_password
    assert account.must_change_password is True
    assert account.temporary_password_expires_at is not None
    assert account.role == "admin"
    assert account.login_id == "SUP04"

    rerun = {**identity, "password": "DifferentPassword!123"}
    assert provision_super_admin(db, **rerun) is False
    db.refresh(account)
    assert account.hashed_password == original_hash
    assert db.query(User).filter(User.is_super_admin.is_(True)).count() == 1
    db.close()
    engine.dispose()


def test_concurrent_bootstrap_creates_at_most_one_super_admin(tmp_path, monkeypatch):
    engine, sessions = _database(tmp_path)
    identity = _identity()
    monkeypatch.setenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", identity["employee_id"])
    barrier = Barrier(2)

    def attempt():
        db = sessions()
        try:
            barrier.wait(timeout=5)
            try:
                return provision_super_admin(db, **identity)
            except (BootstrapConflict, OperationalError):
                db.rollback()
                return False
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt(), range(2)))
    verify = sessions()
    assert sum(result is True for result in results) == 1
    assert verify.query(User).filter(User.is_super_admin.is_(True)).count() == 1
    verify.close()
    engine.dispose()


def test_first_login_requires_rotation_before_mfa_or_session(tmp_path):
    engine, sessions = _database(tmp_path)
    db = sessions()
    account = User(
        full_name="supreme", employee_id="OFFICIAL-SUP-04", login_id="SUP04",
        email="sup04@example.test", phone="9876500044", role="admin",
        is_super_admin=True, must_change_password=True,
        temporary_password_expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        hashed_password=hash_password("OneTimeBootstrapPassword!9"),
        is_active=True, is_verified=True, account_status="active",
    )
    db.add(account)
    db.commit()
    initial_session_version = account.session_version
    with pytest.raises(HTTPException) as login_error:
        AuthService.login_user(db, LoginRequest(
            email="SUP04", password="OneTimeBootstrapPassword!9", role="admin",
        ))
    assert login_error.value.status_code == 428
    assert login_error.value.detail["code"] == "PASSWORD_CHANGE_REQUIRED"

    changed = change_initial_super_admin_password(
        InitialPasswordChangeRequest(
            login_id="SUP04",
            current_password="OneTimeBootstrapPassword!9",
            new_password="RotatedSecurePassword!456",
        ),
        db,
    )
    assert changed["success"] is True
    assert "access_token" not in changed
    assert account.temporary_password_expires_at is None

    with pytest.raises(HTTPException) as old_password:
        AuthService.login_user(db, LoginRequest(
            email="SUP04", password="OneTimeBootstrapPassword!9", role="admin",
        ))
    assert old_password.value.status_code == 401
    with pytest.raises(HTTPException) as new_password:
        AuthService.login_user(db, LoginRequest(
            email="SUP04", password="RotatedSecurePassword!456", role="admin",
        ))
    assert new_password.value.status_code == 403  # MFA remains mandatory; no access token is issued.

    db.refresh(account)
    assert account.must_change_password is False
    assert account.session_version == initial_session_version + 1
    db.close()
    engine.dispose()


def test_super_admin_first_login_rotates_password_then_enrolls_and_authenticates_mfa(tmp_path, monkeypatch):
    engine, sessions = _database(tmp_path)
    identity = _identity()
    monkeypatch.setenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", identity["employee_id"])
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    db = sessions()
    provision_super_admin(db, **identity)
    account = db.query(User).filter(User.login_id == "SUP04").one()

    # Bootstrap stores a verifiable password hash and login lookup accepts the
    # generated login ID, while the first login is held at forced rotation.
    from server.utils.security import verify_password
    assert account.hashed_password != identity["password"]
    assert verify_password(identity["password"], account.hashed_password)
    with pytest.raises(HTTPException) as pending_rotation:
        AuthService.login_user(db, LoginRequest(email="SUP04", password=identity["password"], role="admin"))
    assert pending_rotation.value.status_code == 428
    assert pending_rotation.value.detail["code"] == "PASSWORD_CHANGE_REQUIRED"

    # The pre-rotation MFA action gives an actionable challenge state only to
    # the holder of the correct temporary password and cannot enroll MFA yet.
    with pytest.raises(HTTPException) as mfa_before_rotation:
        start_mfa_enrollment(
            MfaEnrollmentStartRequest(employee_id="SUP04", password=identity["password"]), db,
        )
    assert mfa_before_rotation.value.status_code == 428
    assert mfa_before_rotation.value.detail["code"] == "PASSWORD_CHANGE_REQUIRED"
    with pytest.raises(HTTPException) as wrong_password:
        start_mfa_enrollment(
            MfaEnrollmentStartRequest(employee_id="SUP04", password="WrongPassword!123"), db,
        )
    assert wrong_password.value.status_code == 401

    new_password = "RotatedSuperAdminPassword!456"
    initial_version = account.session_version
    change_initial_super_admin_password(
        InitialPasswordChangeRequest(
            login_id="SUP04", current_password=identity["password"], new_password=new_password,
        ),
        db,
    )
    db.refresh(account)
    assert account.session_version == initial_version + 1
    with pytest.raises(HTTPException) as old_password:
        AuthService.login_user(db, LoginRequest(email="SUP04", password=identity["password"], role="admin"))
    assert old_password.value.status_code == 401
    with pytest.raises(HTTPException) as mfa_required:
        AuthService.login_user(db, LoginRequest(email="SUP04", password=new_password, role="admin"))
    assert mfa_required.value.status_code == 403

    # Missing Fernet configuration is reported as an actionable service error
    # and must not leave partially persisted enrollment state.
    monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
    with pytest.raises(HTTPException) as missing_key:
        start_mfa_enrollment(
            MfaEnrollmentStartRequest(employee_id="SUP04", password=new_password), db,
        )
    assert missing_key.value.status_code == 503
    assert missing_key.value.detail == "Administrator MFA is not configured."
    db.refresh(account)
    assert account.mfa_secret_enc is None
    assert account.mfa_enrollment_expires_at is None
    assert account.mfa_enabled is False

    monkeypatch.setenv("MFA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    enrollment = start_mfa_enrollment(
        MfaEnrollmentStartRequest(employee_id="SUP04", password=new_password), db,
    )
    db.refresh(account)
    assert account.mfa_secret_enc is not None
    assert account.mfa_enrollment_expires_at is not None
    assert account.mfa_enabled is False

    current_step = int(time.time() // 30)
    with pytest.raises(HTTPException) as invalid_code:
        confirm_mfa_enrollment(
            MfaEnrollmentConfirmRequest(employee_id="SUP04", password=new_password, code="invalid"),
            db,
        )
    assert invalid_code.value.status_code == 400
    db.refresh(account)
    assert account.mfa_enabled is False

    confirmation = confirm_mfa_enrollment(
        MfaEnrollmentConfirmRequest(
            employee_id="SUP04", password=new_password,
            code=_totp_code(enrollment["secret"], current_step),
        ),
        db,
    )
    assert confirmation["success"] is True
    db.refresh(account)
    assert account.mfa_enabled is True
    assert account.mfa_enrollment_expires_at is None

    fresh_code = _totp_code(enrollment["secret"], current_step + 1)
    authenticated = AuthService.login_user(
        db,
        LoginRequest(email="SUP04", password=new_password, role="admin", mfa_code=fresh_code),
    )
    assert authenticated.access_token
    assert authenticated.user.is_super_admin is True
    db.close()
    engine.dispose()


def test_expired_super_admin_bootstrap_password_requires_approved_reissue(tmp_path, monkeypatch):
    engine, sessions = _database(tmp_path)
    identity = _identity()
    monkeypatch.setenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", identity["employee_id"])
    db = sessions()
    provision_super_admin(db, **identity)
    account = db.query(User).filter(User.is_super_admin.is_(True)).one()
    initial_hash = account.hashed_password
    initial_version = account.session_version
    account.temporary_password_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    with pytest.raises(HTTPException) as expired:
        AuthService.login_user(db, LoginRequest(
            email="SUP04", password=identity["password"], role="admin",
        ))
    assert expired.value.detail["code"] == "TEMPORARY_CREDENTIAL_EXPIRED"

    account.is_locked = True
    db.commit()

    result = reissue_expired_bootstrap_password(
        db, employee_id=identity["employee_id"], password="ReissuedBootstrapPassword!9",
    )
    db.refresh(account)
    assert result == "SUP04"
    assert account.hashed_password != initial_hash
    assert account.must_change_password is True
    assert account.session_version == initial_version + 1
    assert account.is_locked is False
    assert account.temporary_password_expires_at is not None
    with pytest.raises(HTTPException) as rotation_required:
        AuthService.login_user(db, LoginRequest(
            email="SUP04", password="ReissuedBootstrapPassword!9", role="admin",
        ))
    assert rotation_required.value.detail["code"] == "PASSWORD_CHANGE_REQUIRED"
    db.close()
    engine.dispose()
