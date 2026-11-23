import hashlib
import re
import sqlite3
import time
import uuid
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from fastapi import HTTPException

from server.database.db import SessionLocal
from server.main import app
from server.models.account_invitation import AccountInvitation
from server.models.bin import SmartBin
from server.models.complaint import Complaint
from server.models.mobile_otp import MobileOtpToken
from server.models.notification import Notification
from server.models.security_audit_event import SecurityAuditEvent
from server.models.task import DriverTask
from server.models.user import User
from server.schemas.auth import LoginRequest
from server.services.auth_service import AuthService
from server.services.complaint_service import ComplaintService
from server.services.iam_service import (
    _totp_code,
    issue_invitation,
    make_access_token,
)
from server.services.otp_delivery.base import OtpDeliveryProvider, OtpDeliveryResult
from server.services.otp_delivery.factory import set_otp_delivery_provider_for_testing
from server.tests.iam_test_helpers import (
    TEST_FERNET_KEY,
    TEST_TOTP_SECRET,
    admin_access_token,
    citizen_access_token,
    prepare_admin_mfa,
)
from server.utils.security import hash_password


client = TestClient(app)


def _create_invited_user(db, actor, role, full_name, employee_id, **fields):
    user = User(
        full_name=full_name,
        employee_id=employee_id,
        role=role,
        is_active=False,
        is_verified=False,
        account_status="pending",
        created_by_id=actor.id,
        approved_by_id=actor.id if role == "admin" else None,
        **fields,
    )
    db.add(user)
    db.flush()
    token = issue_invitation(db, user, role, actor, approved_by=actor if role == "admin" else None)
    db.commit()
    db.refresh(user)
    return user, token


class CapturingOtpProvider(OtpDeliveryProvider):
    def __init__(self):
        self.code = None

    @property
    def provider_name(self):
        return "iam-test"

    def send_otp(self, e164_phone, otp):
        self.code = otp
        return OtpDeliveryResult(
            success=True,
            provider=self.provider_name,
            message="Test OTP accepted.",
            provider_message_id="wamid.iam-test",
        )


@pytest.fixture
def iam_context(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", TEST_FERNET_KEY)
    monkeypatch.setenv("SECRET_KEY", "municipal-iam-test-secret-key-at-least-32")
    db = SessionLocal()
    user_ids = []
    phones = []
    shared_super_admin = db.query(User).filter(
        User.email == "super-admin@example.test",
        User.is_super_admin.is_(True),
    ).one_or_none()

    def create_user(role, **overrides):
        uid = uuid.uuid4().hex[:12]
        phone = f"9{int(uid[:9], 16) % 1_000_000_000:09d}"
        if overrides.get("is_super_admin") is True and shared_super_admin is not None:
            # Migration 009 intentionally permits only one Super Admin. Tests
            # that need a per-test principal temporarily move that unique slot
            # away from the session-scoped command-center account.
            shared_super_admin.is_super_admin = False
            db.commit()
        user = User(
            full_name=f"Test {role.title()}",
            email=f"{role}-{uid}@example.test",
            phone=phone,
            employee_id=f"{role[:3].upper()}-{uid}",
            hashed_password=hash_password("ValidPassword123!"),
            role=role,
            is_active=True,
            is_verified=True,
            account_status="active",
            **overrides,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_ids.append(user.id)
        phones.append(phone)
        return user

    try:
        yield db, create_user, phones
    finally:
        # A failed insert/flush must not prevent fixture cleanup queries.
        db.rollback()
        if user_ids:
            provisioned_ids = [
                row[0] for row in db.query(User.id).filter(User.created_by_id.in_(user_ids)).all()
            ]
            phone_user_ids = [
                row[0] for row in db.query(User.id).filter(User.phone.in_(phones)).all()
            ]
            cleanup_ids = list(set(user_ids + provisioned_ids + phone_user_ids))
        else:
            cleanup_ids = []
        if cleanup_ids:
            db.query(AccountInvitation).filter(
                AccountInvitation.user_id.in_(cleanup_ids)
                | AccountInvitation.created_by_id.in_(cleanup_ids)
                | AccountInvitation.approved_by_id.in_(cleanup_ids)
            ).delete(synchronize_session=False)
            db.query(SecurityAuditEvent).filter(
                SecurityAuditEvent.actor_id.in_(cleanup_ids)
                | SecurityAuditEvent.target_user_id.in_(cleanup_ids)
            ).delete(synchronize_session=False)
            db.query(MobileOtpToken).filter(MobileOtpToken.phone.in_(phones)).delete(
                synchronize_session=False
            )
            db.query(User).filter(User.id.in_(cleanup_ids)).delete(synchronize_session=False)
            db.commit()
        if shared_super_admin is not None:
            db.refresh(shared_super_admin)
            shared_super_admin.is_super_admin = True
            db.commit()
        db.close()
        set_otp_delivery_provider_for_testing(None)


def test_public_citizen_registration_succeeds(iam_context):
    db, _, phones = iam_context
    phone = f"9{uuid.uuid4().int % 1_000_000_000:09d}"
    phones.append(phone)
    provider = CapturingOtpProvider()
    set_otp_delivery_provider_for_testing(provider)
    send = client.post("/api/auth/otp/send", json={"phone": phone, "purpose": "register"})
    assert send.status_code == 200

    register = client.post(
        "/api/auth/register",
        json={
            "full_name": "New Citizen",
            "phone": phone,
            "otp": provider.code,
            "challenge_id": send.json()["challenge_id"],
        },
    )
    assert register.status_code == 200
    account = db.query(User).filter(User.phone == phone).one()
    assert account.role == "citizen"
    assert register.json()["user"]["role"] == "citizen"
    # Citizen verification must be set explicitly by registration, never by a
    # trust-by-default ORM default.
    assert account.is_verified is True
    assert account.account_status == "active"


def test_user_model_verification_is_deny_by_default():
    # Staff accounts must never become trusted by an implicit ORM default.
    assert User.is_verified.default.arg is False
    assert User.is_super_admin.default.arg is False
    assert User.mfa_enabled.default.arg is False
    assert User.account_status.default.arg == "active"


def test_created_schema_denies_verification_by_default():
    from sqlalchemy import inspect

    from server.database.db import engine

    columns = {column["name"]: column for column in inspect(engine).get_columns("users")}
    assert columns["is_verified"]["nullable"] is False
    # SQLAlchemy renders boolean false() as "0" on SQLite and "false" on PostgreSQL.
    assert str(columns["is_verified"]["default"]).lower() in {"0", "false"}


@pytest.mark.parametrize("role", ["admin", "driver", "collector"])
def test_public_registration_rejects_privileged_roles(iam_context, role):
    phone = f"9{uuid.uuid4().int % 1_000_000_000:09d}"
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Unauthorized User",
            "phone": phone,
            "otp": "123456",
            "role": role,
        },
    )
    assert response.status_code == 403


def test_anonymous_user_cannot_create_privileged_accounts():
    response = client.post(
        "/api/admin/drivers",
        json={
            "full_name": "Driver One",
            "employee_id": "DRIVER-ANON-01",
            "phone": "9876543210",
            "ward": "Ward 1",
        },
    )
    assert response.status_code == 401


def test_admin_cannot_provision_another_admin(iam_context):
    db, create_user, _ = iam_context
    admin = create_user("admin")
    token = admin_access_token(admin)
    response = client.post(
        "/api/admin/admins/invitations",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "New Admin", "employee_id": "ADMIN-NOT-AUTHORIZED"},
    )
    assert response.status_code == 403


def test_super_admin_provisions_municipal_admin_without_allowlist(iam_context, monkeypatch):
    db, create_user, _ = iam_context
    monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)
    super_admin = create_user("admin", is_super_admin=True)
    super_headers = {"Authorization": f"Bearer {admin_access_token(super_admin)}"}
    assigned_employee_id = f"OFFICIAL-ASSIGNED-{uuid.uuid4().hex[:8]}"
    phone = f"9{uuid.uuid4().int % 1_000_000_000:09d}"
    payload = {
        "full_name": "New Municipal Administrator",
        "role": "admin",
        "employee_id": assigned_employee_id,
        "phone": phone,
        "email": None,
    }

    created = client.post("/api/admin/staff", headers=super_headers, json=payload)
    assert created.status_code == 201, created.text
    credentials = created.json()
    assert credentials["employee_id"] == assigned_employee_id
    assert credentials["login_id"].startswith("ADM")
    assert credentials["login_id"] != assigned_employee_id
    assert credentials["temporary_password"]

    account = db.query(User).filter(User.id == credentials["id"]).one()
    assert account.role == "admin" and account.is_super_admin is False
    assert account.must_change_password is True
    assert account.temporary_password_expires_at is not None
    assert account.mfa_enabled is False  # mandatory enrollment precedes any session

    with pytest.raises(HTTPException) as rotation_required:
        AuthService.login_user(
            db,
            LoginRequest(
                email=credentials["login_id"],
                password=credentials["temporary_password"],
                role="admin",
            ),
        )
    assert rotation_required.value.status_code == 428
    assert rotation_required.value.detail["code"] == "PASSWORD_CHANGE_REQUIRED"
    with pytest.raises(HTTPException) as employee_id_login:
        AuthService.login_user(
            db,
            LoginRequest(
                email=assigned_employee_id,
                password=credentials["temporary_password"],
                role="admin",
            ),
        )
    assert employee_id_login.value.status_code == 428
    assert employee_id_login.value.detail["code"] == "PASSWORD_CHANGE_REQUIRED"

    duplicate = client.post(
        "/api/admin/staff",
        headers=super_headers,
        json={**payload, "full_name": "Duplicate ID", "phone": f"9{uuid.uuid4().int % 1_000_000_000:09d}"},
    )
    assert duplicate.status_code == 409

    municipal_admin = create_user("admin")
    denied = client.post(
        "/api/admin/staff",
        headers={"Authorization": f"Bearer {admin_access_token(municipal_admin)}"},
        json={**payload, "employee_id": f"OTHER-{uuid.uuid4().hex[:8]}", "phone": f"9{uuid.uuid4().int % 1_000_000_000:09d}"},
    )
    assert denied.status_code == 403


def test_super_admin_invitation_api_is_offline_only(iam_context, monkeypatch):
    db, create_user, _ = iam_context
    super_admin = create_user("admin", is_super_admin=True)
    token = admin_access_token(super_admin)
    monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)

    response = client.post(
        "/api/admin/admins/invitations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "full_name": "Provisioned Admin",
            "employee_id": "MUNI-ADMIN-02",
            "email": "provisioned-admin@example.test",
            "phone": "9876501234",
        },
    )
    assert response.status_code == 410
    assert "activation_token" not in response.json()
    assert "#token=" not in response.text
    assert db.query(User).filter(User.employee_id == "MUNI-ADMIN-02").count() == 0


def test_authorized_admin_driver_invitation_api_is_disabled(iam_context):
    db, create_user, _ = iam_context
    admin = create_user("admin")
    token = admin_access_token(admin)
    response = client.post(
        "/api/admin/drivers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "full_name": "Provisioned Driver",
            "employee_id": f"DRV-{uuid.uuid4().hex[:10]}",
            "phone": f"9{uuid.uuid4().int % 1_000_000_000:09d}",
            "ward": "Ward 3",
            "vehicle_assignment": "Vehicle 17",
        },
    )
    assert response.status_code == 410
    assert "activation_token" not in response.json()
    assert "#token=" not in response.text


def test_driver_cannot_self_register_or_use_otp(iam_context):
    db, create_user, _ = iam_context
    driver = create_user("driver")
    register = client.post(
        "/api/auth/register",
        json={
            "full_name": "Self Registered Driver",
            "phone": f"9{uuid.uuid4().int % 1_000_000_000:09d}",
            "otp": "123456",
            "role": "driver",
        },
    )
    otp = client.post(
        "/api/auth/otp/send",
        json={"phone": driver.phone, "purpose": "login"},
    )
    assert register.status_code == 403
    assert otp.status_code == 403


def test_driver_password_login_requires_active_verified_account(iam_context):
    db, create_user, _ = iam_context
    driver = create_user("driver")
    response = client.post(
        "/api/auth/login",
        json={"email": driver.employee_id, "password": "ValidPassword123!", "role": "driver"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "driver"

    driver.is_active = False
    driver.account_status = "suspended"
    db.commit()
    inactive = client.post(
        "/api/auth/login",
        json={"email": driver.employee_id, "password": "ValidPassword123!", "role": "driver"},
    )
    assert inactive.status_code == 403
    driver.is_active = True
    driver.account_status = "active"
    driver.is_verified = False
    db.commit()
    unverified = client.post(
        "/api/auth/login",
        json={"email": driver.employee_id, "password": "ValidPassword123!", "role": "driver"},
    )
    assert unverified.status_code == 403


def test_admin_login_requires_mfa_and_rejects_replayed_code(iam_context):
    db, create_user, _ = iam_context
    admin = create_user("admin")
    no_mfa = client.post(
        "/api/auth/login",
        json={"email": admin.employee_id, "password": "ValidPassword123!", "role": "admin"},
    )
    assert no_mfa.status_code == 403

    prepare_admin_mfa(admin)
    db.commit()
    from server.services.iam_service import _totp_code
    import time
    code = _totp_code(TEST_TOTP_SECRET, int(time.time() // 30))
    payload = {"email": admin.employee_id, "password": "ValidPassword123!", "role": "admin", "mfa_code": code}
    success = client.post("/api/auth/login", json=payload)
    replay = client.post("/api/auth/login", json=payload)
    assert success.status_code == 200
    assert replay.status_code == 401


def test_collector_and_administrator_login_preserve_stored_roles(iam_context):
    db, create_user, _ = iam_context
    collector = create_user("collector")
    admin = create_user("admin")
    prepare_admin_mfa(collector)
    prepare_admin_mfa(admin)
    db.commit()
    code = _totp_code(TEST_TOTP_SECRET, int(time.time() // 30))

    collector_response = client.post(
        "/api/auth/login",
        json={
            "email": collector.employee_id,
            "password": "ValidPassword123!",
            "role": "collector",
            "mfa_code": code,
        },
    )
    admin_response = client.post(
        "/api/auth/login",
        json={
            "email": admin.employee_id,
            "password": "ValidPassword123!",
            "role": "admin",
            "mfa_code": code,
        },
    )
    collector_wrong_role = client.post(
        "/api/auth/login",
        json={
            "email": collector.employee_id,
            "password": "ValidPassword123!",
            "role": "admin",
            "mfa_code": code,
        },
    )

    assert collector_response.status_code == 200
    assert collector_response.json()["user"]["role"] == "collector"
    assert admin_response.status_code == 200
    assert admin_response.json()["user"]["role"] == "admin"
    assert collector_wrong_role.status_code == 401


def test_legacy_staff_verification_requires_explicit_audited_approval():
    migration_dir = Path(__file__).resolve().parents[2] / "migrations"
    migration = (migration_dir / "007_municipal_iam.sql").read_text(encoding="utf-8")
    approval_script = (
        migration_dir / "007_municipal_iam_legacy_verification.sql"
    ).read_text(encoding="utf-8")

    assert "is_verified BOOLEAN NOT NULL DEFAULT FALSE" in migration
    assert "SET is_verified = TRUE\nWHERE role = 'citizen'" in migration
    assert "SET is_verified = FALSE" in migration
    assert "role IN ('driver', 'admin', 'collector')" in migration
    assert "approved_by_employee_id" in approval_script
    assert "evidence_reference" in approval_script
    assert "'legacy_account_verified'" in approval_script
    assert "FROM approved_legacy_accounts" in approval_script
    assert "must cover every active legacy municipal account" in approval_script


def test_legacy_verification_requires_authorized_super_admin_approver():
    migration_dir = Path(__file__).resolve().parents[2] / "migrations"
    approval_script = (
        migration_dir / "007_municipal_iam_legacy_verification.sql"
    ).read_text(encoding="utf-8")

    assert "approver.role = 'admin'" in approval_script
    assert "approver.is_super_admin IS TRUE" in approval_script
    assert "approver.is_verified IS TRUE" in approval_script
    assert "approver.is_active IS TRUE" in approval_script
    assert "approver.account_status = 'active'" in approval_script
    assert "Every approver must be an existing active, verified Super Admin account" in approval_script
    assert "LEFT JOIN users approver" not in approval_script
    assert "WHERE account.employee_id = approval.employee_id" in approval_script
    assert "AND account.is_verified IS FALSE" in approval_script
    assert "AND account.is_active IS TRUE" in approval_script


def test_municipal_iam_staff_verification_statement_is_well_formed():
    migration_dir = Path(__file__).resolve().parents[2] / "migrations"
    migration = (migration_dir / "007_municipal_iam.sql").read_text(encoding="utf-8")

    match = re.search(
        r"UPDATE users\s+SET is_verified = FALSE,.*?;",
        migration,
        re.DOTALL,
    )
    assert match, "Legacy staff verification statement is missing."
    statement = match.group(0)
    assert "collector');" not in statement.replace("\n", ""), (
        "The staff verification UPDATE must not terminate before its predicates."
    )
    assert "AND verified_at IS NULL;" in statement
    assert "CASE WHEN is_active IS FALSE THEN 'suspended' ELSE 'active' END" in migration


def test_staff_verification_statement_resets_unapproved_staff_on_sqlite():
    """SQLite executes the statement for logic coverage only; this is not PostgreSQL validation."""
    migration_dir = Path(__file__).resolve().parents[2] / "migrations"
    migration = (migration_dir / "007_municipal_iam.sql").read_text(encoding="utf-8")
    statement = re.search(
        r"UPDATE users\s+SET is_verified = FALSE,.*?;",
        migration,
        re.DOTALL,
    ).group(0)

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, role TEXT NOT NULL, "
            "is_verified BOOLEAN NOT NULL DEFAULT FALSE, verified_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO users (id, role, is_verified, verified_at) VALUES (?, ?, ?, ?)",
            [
                (1, "driver", 1, None),
                (2, "admin", 1, "2026-01-01 00:00:00"),
                (3, "citizen", 1, None),
                (4, "collector", 0, None),
            ],
        )
        connection.execute(statement)
        rows = dict(
            connection.execute("SELECT id, is_verified FROM users").fetchall()
        )
        approved_at = connection.execute(
            "SELECT verified_at FROM users WHERE id = 2"
        ).fetchone()[0]
    finally:
        connection.close()

    assert rows[1] == 0, "Unapproved legacy staff must not remain verified."
    assert rows[2] == 1, "Explicitly approved staff must keep their verification."
    assert rows[3] == 1, "Citizen verification must not be reset."
    assert rows[4] == 0
    assert approved_at == "2026-01-01 00:00:00"


def test_invitation_validation_reports_expired_revoked_and_used_states(iam_context):
    db, create_user, _ = iam_context
    from datetime import datetime, timedelta, timezone

    tokens = {}
    for state in ("valid", "expired", "revoked", "used"):
        driver = create_user("driver")
        token = issue_invitation(db, driver, "driver", actor=driver)
        db.flush()
        invitation = db.query(AccountInvitation).filter(
            AccountInvitation.user_id == driver.id
        ).one()
        if state == "expired":
            invitation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        elif state == "revoked":
            invitation.revoked_at = datetime.now(timezone.utc)
        elif state == "used":
            invitation.consumed_at = datetime.now(timezone.utc)
        tokens[state] = token
    db.commit()

    for state in ("valid", "expired", "revoked", "used"):
        response = client.post(
            "/api/auth/invitations/validate",
            json={"token": tokens[state]},
        )
        assert response.status_code == 200
        assert response.json()["status"] == state
        assert "token" not in response.json()

    invalid = client.post(
        "/api/auth/invitations/validate",
        json={"token": "x" * 43},
    )
    assert invalid.status_code == 200
    assert invalid.json() == {"status": "invalid", "role": None, "employee_id": None}


def test_driver_invitation_activation_sets_password_and_consumes_token(iam_context):
    db, create_user, phones = iam_context
    admin = create_user("admin")
    driver_phone = f"9{uuid.uuid4().int % 1_000_000_000:09d}"
    phones.append(driver_phone)
    provider = CapturingOtpProvider()
    set_otp_delivery_provider_for_testing(provider)
    try:
        driver, token = _create_invited_user(
            db, admin, "driver", "Activation Driver", f"ACT-{uuid.uuid4().hex[:10]}",
            phone=driver_phone, ward="Ward 8",
        )
        invitation = db.query(AccountInvitation).join(
            User, AccountInvitation.user_id == User.id
        ).filter(
            User.phone == driver_phone,
            AccountInvitation.role == "driver",
        ).one()
        assert invitation.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
        otp_response = client.post(
            "/api/auth/otp/send",
            json={"phone": driver_phone, "purpose": "activation"},
        )
        assert otp_response.status_code == 200

        activation = client.post(
            "/api/auth/drivers/activate",
            json={
                "token": token,
                "phone": driver_phone,
                "otp": provider.code,
                "challenge_id": otp_response.json()["challenge_id"],
                "password": "NewDriverPassword123!",
            },
        )
        assert activation.status_code == 200
        driver = db.query(User).filter(User.phone == driver_phone).one()
        db.refresh(driver)
        assert driver.is_active is True
        assert driver.is_verified is True
        assert driver.account_status == "active"

        reused = client.post(
            "/api/auth/drivers/activate",
            json={
                "token": token,
                "phone": driver_phone,
                "otp": provider.code,
                "challenge_id": otp_response.json()["challenge_id"],
                "password": "NewDriverPassword123!",
            },
        )
        assert reused.status_code == 400
    finally:
        set_otp_delivery_provider_for_testing(None)


def test_administrator_invitation_activation_requires_and_enrolls_mfa(iam_context, monkeypatch):
    db, create_user, _ = iam_context
    super_admin = create_user("admin", is_super_admin=True)
    employee_id = f"NEW-ADMIN-{uuid.uuid4().hex[:8]}"
    monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)

    invited_admin, token = _create_invited_user(
        db, super_admin, "admin", "Activated Administrator", employee_id,
        email=f"{employee_id.lower()}@example.test",
        phone=f"9{uuid.uuid4().int % 1_000_000_000:09d}",
    )
    invitation = db.query(AccountInvitation).join(
        User, AccountInvitation.user_id == User.id
    ).filter(
        User.employee_id == employee_id,
        AccountInvitation.role == "admin",
    ).one()
    assert invitation.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()

    activation = client.post(
        "/api/auth/admins/activate",
        json={"token": token, "password": "NewAdminPassword123!"},
    )
    assert activation.status_code == 200
    admin = db.query(User).filter(User.employee_id == employee_id).one()
    db.refresh(admin)
    assert admin.is_active is True
    assert admin.is_verified is True
    assert admin.mfa_enabled is False

    enrollment = client.post(
        "/api/auth/mfa/enrollment/start",
        json={"employee_id": employee_id, "password": "NewAdminPassword123!"},
    )
    assert enrollment.status_code == 200
    code = _totp_code(enrollment.json()["secret"], int(time.time() // 30))
    confirmation = client.post(
        "/api/auth/mfa/enrollment/confirm",
        json={
            "employee_id": employee_id,
            "password": "NewAdminPassword123!",
            "code": code,
        },
    )
    assert confirmation.status_code == 200
    db.refresh(admin)
    assert admin.mfa_enabled is True


def test_anonymous_user_cannot_create_collector():
    response = client.post(
        "/api/admin/collectors",
        json={"full_name": "Collector One", "employee_id": "COLLECTOR-ANON-01"},
    )
    assert response.status_code == 401


def test_authorized_admin_collector_invitation_api_is_disabled(iam_context):
    db, create_user, _ = iam_context
    admin = create_user("admin")
    employee_id = f"COL-{uuid.uuid4().hex[:10]}"
    email = f"{employee_id.lower()}@example.test"
    phone = f"9{uuid.uuid4().int % 1_000_000_000:09d}"

    response = client.post(
        "/api/admin/collectors",
        headers={"Authorization": f"Bearer {admin_access_token(admin)}"},
        json={
            "full_name": "Provisioned Collector",
            "employee_id": employee_id,
            "email": email,
            "phone": phone,
            "ward": "Ward 4",
        },
    )
    assert response.status_code == 410
    assert "activation_token" not in response.json()
    assert "#token=" not in response.text
    assert db.query(User).filter(User.employee_id == employee_id).count() == 0


def test_non_admin_roles_cannot_provision_collectors(iam_context):
    _, create_user, _ = iam_context
    collector = create_user("collector")
    driver = create_user("driver")
    citizen = create_user("citizen")

    collector_provision = client.post(
        "/api/admin/collectors",
        headers={"Authorization": f"Bearer {admin_access_token(collector)}"},
        json={"full_name": "Forged Collector", "employee_id": "FORGED-COLLECTOR-01"},
    )
    driver_provision = client.post(
        "/api/admin/drivers",
        headers={"Authorization": f"Bearer {admin_access_token(collector)}"},
        json={
            "full_name": "Forged Driver",
            "employee_id": "FORGED-DRIVER-01",
            "phone": "9876509999",
            "ward": "Ward 1",
        },
    )
    driver_collector_provision = client.post(
        "/api/admin/collectors",
        headers={"Authorization": f"Bearer {admin_access_token(driver)}"},
        json={"full_name": "Driver Collector", "employee_id": "FORGED-DRIVER-COL-01"},
    )
    citizen_collector_provision = client.post(
        "/api/admin/collectors",
        headers={"Authorization": f"Bearer {citizen_access_token(citizen)}"},
        json={"full_name": "Citizen Collector", "employee_id": "FORGED-CITIZEN-COL-01"},
    )

    assert collector_provision.status_code == 403
    assert driver_provision.status_code == 403
    assert driver_collector_provision.status_code == 403
    assert citizen_collector_provision.status_code == 403


def test_collector_duplicate_invitation_requests_do_not_create_accounts(iam_context):
    _, create_user, _ = iam_context
    admin = create_user("admin")
    headers = {"Authorization": f"Bearer {admin_access_token(admin)}"}
    employee_id = f"COL-{uuid.uuid4().hex[:10]}"
    email = f"{employee_id.lower()}@example.test"
    phone = f"9{uuid.uuid4().int % 1_000_000_000:09d}"

    created = client.post(
        "/api/admin/collectors",
        headers=headers,
        json={
            "full_name": "Unique Collector",
            "employee_id": employee_id,
            "email": email,
            "phone": phone,
            "ward": "Ward 4",
        },
    )
    assert created.status_code == 410

    duplicate_employee = client.post(
        "/api/admin/collectors",
        headers=headers,
        json={
            "full_name": "Duplicate Employee",
            "employee_id": employee_id,
            "email": f"other-{uuid.uuid4().hex[:8]}@example.test",
            "phone": f"9{uuid.uuid4().int % 1_000_000_000:09d}",
            "ward": "Ward 4",
        },
    )
    duplicate_phone = client.post(
        "/api/admin/collectors",
        headers=headers,
        json={
            "full_name": "Duplicate Phone",
            "employee_id": f"COL-{uuid.uuid4().hex[:10]}",
            "phone": phone,
            "ward": "Ward 4",
        },
    )
    duplicate_email = client.post(
        "/api/admin/collectors",
        headers=headers,
        json={
            "full_name": "Duplicate Email",
            "employee_id": f"COL-{uuid.uuid4().hex[:10]}",
            "email": email,
            "ward": "Ward 4",
        },
    )

    assert duplicate_employee.status_code == 410
    assert duplicate_phone.status_code == 410
    assert duplicate_email.status_code == 410


def test_collector_activation_requires_mfa_enrollment_before_sign_in(iam_context):
    db, create_user, _ = iam_context
    admin = create_user("admin")
    employee_id = f"COL-{uuid.uuid4().hex[:10]}"
    password = "NewCollectorPassword123!"

    collector, token = _create_invited_user(
        db, admin, "collector", "Activation Collector", employee_id,
        email=f"{employee_id.lower()}@example.test",
        phone=f"9{uuid.uuid4().int % 1_000_000_000:09d}", ward="Ward 4",
    )

    activation = client.post(
        "/api/auth/collectors/activate",
        json={"token": token, "password": password},
    )
    assert activation.status_code == 200
    collector = db.query(User).filter(User.employee_id == employee_id).one()
    db.refresh(collector)
    assert collector.is_active is True
    assert collector.is_verified is True
    assert collector.account_status == "active"
    assert collector.mfa_enabled is False

    blocked_login = client.post(
        "/api/auth/login",
        json={"email": employee_id, "password": password, "role": "collector"},
    )
    assert blocked_login.status_code == 403

    reused = client.post(
        "/api/auth/collectors/activate",
        json={"token": token, "password": password},
    )
    assert reused.status_code == 400

    enrollment = client.post(
        "/api/auth/mfa/enrollment/start",
        json={"employee_id": employee_id, "password": password},
    )
    assert enrollment.status_code == 200
    code = _totp_code(enrollment.json()["secret"], int(time.time() // 30))
    confirmation = client.post(
        "/api/auth/mfa/enrollment/confirm",
        json={"employee_id": employee_id, "password": password, "code": code},
    )
    assert confirmation.status_code == 200

    login_code = _totp_code(
        enrollment.json()["secret"],
        int(time.time() // 30) + 1,
    )
    login = client.post(
        "/api/auth/login",
        json={
            "email": employee_id,
            "password": password,
            "role": "collector",
            "mfa_code": login_code,
        },
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "collector"


def test_super_admin_directory_reports_invitation_status_and_can_suspend_collector(iam_context, monkeypatch):
    db, create_user, _ = iam_context
    super_admin = create_user("admin", is_super_admin=True)
    headers = {"Authorization": f"Bearer {admin_access_token(super_admin)}"}
    employee_id = f"MUNI-{uuid.uuid4().hex[:8]}"
    monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)

    invited, _ = _create_invited_user(
        db, super_admin, "admin", "Tracked Administrator", employee_id,
    )

    directory = client.get("/api/admin/admins", headers=headers)
    assert directory.status_code == 200
    row = next(
        account for account in directory.json()
        if account["employee_id"] == invited.employee_id
    )
    assert row["invitation_status"] == "pending"
    assert row["invitation_expires_at"] is not None

    collector = create_user("collector")
    suspended = client.patch(
        f"/api/admin/accounts/{collector.id}/status",
        headers=headers,
        json={"account_status": "suspended", "reason": "Operational review"},
    )
    assert suspended.status_code == 200
    db.refresh(collector)
    assert collector.account_status == "suspended"

    municipal_admin = create_user("admin")
    forbidden = client.get(
        "/api/admin/admins",
        headers={"Authorization": f"Bearer {admin_access_token(municipal_admin)}"},
    )
    assert forbidden.status_code == 403


def test_driver_task_data_and_updates_are_identity_scoped(iam_context):
    db, create_user, _ = iam_context
    owner = create_user("driver")
    other_driver = create_user("driver")
    owner_task = DriverTask(driver_id=owner.id, location_name="Assigned stop")
    other_task = DriverTask(driver_id=other_driver.id, location_name="Other stop")
    db.add_all([owner_task, other_task])
    db.commit()
    db.refresh(owner_task)
    db.refresh(other_task)
    owner_token = make_access_token(owner, "driver-isolation-owner")
    headers = {"Authorization": f"Bearer {owner_token}"}

    tasks = client.get("/api/driver/tasks", headers=headers)
    other_update = client.patch(
        f"/api/driver/tasks/{other_task.id}/status",
        headers=headers,
        json={"status": "Completed"},
    )

    assert tasks.status_code == 200
    assert [task["id"] for task in tasks.json()] == [owner_task.id]
    assert other_update.status_code == 403
    db.delete(owner_task)
    db.delete(other_task)
    db.commit()


def test_suspended_admin_cannot_access_privileged_api(iam_context):
    db, create_user, _ = iam_context
    admin = create_user("admin")
    prepare_admin_mfa(admin)
    token = make_access_token(admin, "suspended-test-session")
    admin.is_active = False
    admin.account_status = "suspended"
    db.commit()
    response = client.get(
        "/api/admin/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_password_change_revokes_existing_sessions(iam_context):
    db, create_user, _ = iam_context
    citizen = create_user("citizen")
    token = citizen_access_token(citizen)
    changed = client.post(
        "/api/auth/password/change",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "ValidPassword123!",
            "new_password": "ReplacementPassword123!",
        },
    )
    assert changed.status_code == 200
    revoked = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoked.status_code == 401


def test_demo_user_seeding_is_disabled_in_production(iam_context, monkeypatch):
    db, _, _ = iam_context
    monkeypatch.setenv("ENV", "production")
    before = db.query(User).count()
    AuthService.seed_demo_users(db)
    assert db.query(User).count() == before


@pytest.mark.parametrize("role", ["driver", "admin", "collector"])
def test_staff_profile_update_omits_and_rejects_ward_changes(iam_context, role):
    db, create_user, _ = iam_context
    staff = create_user(role, ward="Ward A")
    token = admin_access_token(staff) if role in {"admin", "collector"} else citizen_access_token(staff)
    headers = {"Authorization": f"Bearer {token}"}

    profile = client.put(
        "/api/auth/profile",
        headers=headers,
        json={"full_name": f"Updated {role.title()}", "phone": staff.phone},
    )
    assert profile.status_code == 200, profile.text
    db.refresh(staff)
    assert staff.full_name == f"Updated {role.title()}"
    assert staff.ward == "Ward A"

    # A caller cannot bypass the UI and change an employee's assigned ward.
    denied = client.put(
        "/api/auth/profile",
        headers=headers,
        json={"full_name": "Should Not Persist", "ward": "Ward B", "phone": staff.phone},
    )
    assert denied.status_code == 403
    db.refresh(staff)
    assert staff.full_name == f"Updated {role.title()}"
    assert staff.ward == "Ward A"


def test_citizen_profile_can_still_update_ward(iam_context):
    db, create_user, _ = iam_context
    citizen = create_user("citizen", ward="Ward A")
    headers = {"Authorization": f"Bearer {citizen_access_token(citizen)}"}

    response = client.put(
        "/api/auth/profile",
        headers=headers,
        json={"full_name": "Updated Citizen", "ward": "Ward B", "phone": citizen.phone},
    )

    assert response.status_code == 200, response.text
    db.refresh(citizen)
    assert citizen.full_name == "Updated Citizen"
    assert citizen.ward == "Ward B"


def test_collector_complaint_and_driver_operations_are_ward_scoped(iam_context):
    db, create_user, _ = iam_context
    collector = create_user("collector", ward="Ward A")
    driver_a = create_user("driver", ward="Ward A")
    driver_b = create_user("driver", ward="Ward B")
    driver_a.is_verified = driver_b.is_verified = True
    complaint_a = Complaint(
        tracking_number=f"EP-A-{uuid.uuid4().hex[:12]}", ward="Ward A",
        location_address="A", waste_type="Mixed Waste", status="Pending",
    )
    complaint_b = Complaint(
        tracking_number=f"EP-B-{uuid.uuid4().hex[:12]}", ward="Ward B",
        location_address="B", waste_type="Mixed Waste", status="Pending",
    )
    db.add_all([complaint_a, complaint_b])
    db.commit()
    headers = {"Authorization": f"Bearer {admin_access_token(collector)}"}

    ward_change = client.put(
        "/api/auth/profile", headers=headers, json={"ward": "Ward B"},
    )
    assert ward_change.status_code == 403
    db.refresh(collector)
    assert collector.ward == "Ward A"

    listing = client.get("/api/admin/complaints", headers=headers)
    assert listing.status_code == 200
    assert {row["ward"] for row in listing.json()} <= {"Ward A"}
    assert complaint_a.tracking_number in {row["id"] for row in listing.json()}
    assert complaint_b.tracking_number not in {row["id"] for row in listing.json()}

    assert client.post(
        "/api/admin/assign-task", headers=headers,
        json={"complaint_id": complaint_a.id, "driver_name": driver_a.employee_id},
    ).status_code == 200
    assert client.post(
        "/api/admin/assign-task", headers=headers,
        json={"complaint_id": complaint_a.id, "driver_name": driver_b.employee_id},
    ).status_code == 404

    assert client.patch(
        f"/api/admin/complaints/{complaint_a.id}/status", headers=headers,
        json={"status": "Completed"},
    ).status_code == 409
    assert client.patch(
        f"/api/admin/complaints/{complaint_b.id}/status", headers=headers,
        json={"status": "Completed"},
    ).status_code == 404
    assert client.patch(
        f"/api/admin/complaints/{complaint_a.id}/status", headers=headers,
        json={"status": "Pending"},
    ).status_code == 403

    drivers = client.get("/api/admin/drivers", headers=headers)
    assert drivers.status_code == 200
    assert all(row["ward"] == "Ward A" and row["role"] == "driver" for row in drivers.json())
    complaint_ids = [complaint_a.id, complaint_b.id]
    db.query(DriverTask).filter(DriverTask.complaint_id.in_(complaint_ids)).delete(synchronize_session=False)
    db.query(Complaint).filter(Complaint.id.in_(complaint_ids)).delete(synchronize_session=False)
    db.commit()


def test_collector_cannot_use_global_or_governance_endpoints(iam_context):
    _, create_user, _ = iam_context
    collector = create_user("collector", ward="Ward A")
    driver = create_user("driver", ward="Ward A")
    headers = {"Authorization": f"Bearer {admin_access_token(collector)}"}

    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert client.get("/api/admin/export-csv", headers=headers).status_code == 403
    assert client.get("/api/admin/notifications", headers=headers).status_code == 403
    assert client.post(
        "/api/admin/notifications/broadcast", headers=headers,
        json={"title": "x", "message": "y", "audience": "All", "priority": "Standard"},
    ).status_code == 403
    assert client.post(
        "/api/admin/drivers", headers=headers,
        json={"full_name": "No", "employee_id": "NO-DRIVER", "phone": "9876543210", "ward": "Ward A"},
    ).status_code == 403
    assert client.post(
        "/api/admin/collectors", headers=headers,
        json={"full_name": "No", "employee_id": "NO-COLLECTOR", "ward": "Ward A"},
    ).status_code == 403
    assert client.post(
        "/api/admin/admins/invitations", headers=headers,
        json={"full_name": "No", "employee_id": "NO-ADMIN"},
    ).status_code == 403
    assert client.get("/api/admin/admins", headers=headers).status_code == 403
    assert client.get("/api/admin/audit", headers=headers).status_code == 403
    assert client.get("/api/whatsapp/citizens", headers=headers).status_code == 403
    assert client.post("/api/whatsapp/generate-qr", headers=headers, json={"ward": 1}).status_code == 403
    assert client.patch(
        f"/api/admin/drivers/{driver.id}/status", headers=headers, json={"is_active": False}
    ).status_code == 403


def test_ward_assigned_municipal_admin_cannot_change_other_ward_driver_status(iam_context):
    db, create_user, _ = iam_context
    municipal_admin = create_user("admin", ward="Ward A")
    local_driver = create_user("driver", ward="Ward A")
    remote_driver = create_user("driver", ward="Ward B")
    headers = {"Authorization": f"Bearer {admin_access_token(municipal_admin)}"}

    local_response = client.patch(
        f"/api/admin/drivers/{local_driver.id}/status",
        headers=headers,
        json={"is_active": False, "reason": "Ward operational review"},
    )
    assert local_response.status_code == 200, local_response.text
    db.refresh(local_driver)
    assert local_driver.account_status == "suspended"

    remote_response = client.patch(
        f"/api/admin/drivers/{remote_driver.id}/status",
        headers=headers,
        json={"is_active": False, "reason": "Ward operational review"},
    )
    assert remote_response.status_code == 403
    db.refresh(remote_driver)
    assert remote_driver.account_status == "active"


def test_collector_bins_are_ward_scoped_and_unassigned_is_denied(iam_context):
    db, create_user, _ = iam_context
    collector = create_user("collector", ward="Ward A")
    local_bin = SmartBin(bin_code=f"A-{uuid.uuid4().hex[:8]}", location_name="A", ward="Ward A")
    remote_bin = SmartBin(bin_code=f"B-{uuid.uuid4().hex[:8]}", location_name="B", ward="Ward B")
    db.add_all([local_bin, remote_bin])
    db.commit()
    headers = {"Authorization": f"Bearer {admin_access_token(collector)}"}

    listing = client.get("/api/admin/bins", headers=headers)
    assert listing.status_code == 200
    assert all(row["ward"] == "Ward A" for row in listing.json()["bins"])
    assert local_bin.id in {row["id"] for row in listing.json()["bins"]}
    assert remote_bin.id not in {row["id"] for row in listing.json()["bins"]}
    assert client.patch(
        f"/api/admin/bins/{remote_bin.id}", headers=headers,
        json={"fill_level_pct": 50},
    ).status_code == 404
    assert client.patch(
        f"/api/admin/bins/{local_bin.id}", headers=headers,
        json={"fill_level_pct": 50, "is_active": False},
    ).status_code == 403

    unassigned = create_user("collector", ward=None)
    unassigned_headers = {"Authorization": f"Bearer {admin_access_token(unassigned)}"}
    assert client.get("/api/admin/complaints", headers=unassigned_headers).status_code == 403
    assert client.get("/api/admin/bins", headers=unassigned_headers).status_code == 403
    assert client.get("/api/admin/analytics", headers=unassigned_headers).status_code == 403
    db.delete(local_bin)
    db.delete(remote_bin)
    db.commit()


def test_admin_access_remains_and_driver_citizen_cannot_enter_admin_api(iam_context):
    db, create_user, _ = iam_context
    admin = create_user("admin", ward="Ward A")
    super_admin = create_user("admin", is_super_admin=True, ward="Ward A")
    driver = create_user("driver", ward="Ward A")
    citizen = create_user("citizen", ward="Ward A")
    phone_only_citizen = create_user("citizen", ward="Ward A")
    phone_only_citizen.email = None
    db.commit()

    admin_headers = {"Authorization": f"Bearer {admin_access_token(admin)}"}
    super_headers = {"Authorization": f"Bearer {admin_access_token(super_admin)}"}
    listing = client.get("/api/admin/users", headers=admin_headers)
    assert listing.status_code == 200
    rows = {row["id"]: row for row in listing.json()}
    assert rows[citizen.id]["email"] == citizen.email
    assert rows[phone_only_citizen.id]["email"] is None
    assert "email" in rows[phone_only_citizen.id]
    assert client.post(
        "/api/admin/collectors", headers=admin_headers,
        json={"full_name": "New Collector", "employee_id": f"NEW-{uuid.uuid4().hex[:8]}", "ward": "Ward A"},
    ).status_code == 410
    assert client.get("/api/admin/admins", headers=super_headers).status_code == 200
    assert client.get("/api/admin/audit", headers=super_headers).status_code == 200
    assert client.get(
        "/api/admin/complaints", headers={"Authorization": f"Bearer {admin_access_token(driver)}"}
    ).status_code == 403
    assert client.get(
        "/api/admin/complaints", headers={"Authorization": f"Bearer {citizen_access_token(citizen)}"}
    ).status_code == 403


def test_collector_metrics_and_analytics_are_ward_scoped_and_admin_is_global(iam_context):
    db, create_user, _ = iam_context
    suffix = uuid.uuid4().hex[:8]
    ward_a = f"Phase1J-{suffix}-A"
    ward_b = f"Phase1J-{suffix}-B"
    type_a = f"WardA-{suffix}"
    type_b = f"WardB-{suffix}"
    collector = create_user("collector", ward=ward_a)
    municipal_admin = create_user("admin", ward=ward_a)
    complaints = [
        Complaint(
            tracking_number=f"EP-{suffix}-A", ward=ward_a,
            location_address="A", waste_type=type_a, status="In Progress",
        ),
        Complaint(
            tracking_number=f"EP-{suffix}-B", ward=ward_b,
            location_address="B", waste_type=type_b, status="Pending",
        ),
    ]
    db.add_all(complaints)
    db.commit()
    try:
        collector_headers = {"Authorization": f"Bearer {admin_access_token(collector)}"}
        metrics = client.get("/api/admin/metrics", headers=collector_headers)
        analytics = client.get("/api/admin/analytics", headers=collector_headers)
        assert metrics.status_code == analytics.status_code == 200
        assert metrics.json()["total_complaints"] == db.query(Complaint).filter(Complaint.ward == ward_a).count()
        assert metrics.json()["total_citizens"] == 0
        assert {row["name"] for row in metrics.json()["top_wards"]} <= {ward_a}
        assert {row["ward"] for row in analytics.json()["ward_breakdown"]} <= {ward_a}
        assert {row["type"] for row in analytics.json()["top_waste_types"]} == {type_a}

        admin_headers = {"Authorization": f"Bearer {admin_access_token(municipal_admin)}"}
        admin_analytics = client.get("/api/admin/analytics", headers=admin_headers)
        assert admin_analytics.status_code == 200
        assert {ward_a, ward_b} <= {row["ward"] for row in admin_analytics.json()["ward_breakdown"]}
        assert {type_a, type_b} <= {row["type"] for row in admin_analytics.json()["top_waste_types"]}
    finally:
        db.query(Complaint).filter(Complaint.id.in_([complaint.id for complaint in complaints])).delete(
            synchronize_session=False
        )
        db.commit()


def test_collector_is_denied_and_authorized_invitation_resets_are_offline(iam_context):
    _, create_user, _ = iam_context
    collector = create_user("collector", ward="Ward A")
    municipal_admin = create_user("admin", ward="Ward A")
    super_admin = create_user("admin", is_super_admin=True, ward="Ward A")
    admin_target = create_user("admin", ward="Ward A")
    driver_target = create_user("driver", ward="Ward A")
    collector_headers = {"Authorization": f"Bearer {admin_access_token(collector)}"}
    municipal_headers = {"Authorization": f"Bearer {admin_access_token(municipal_admin)}"}
    super_headers = {"Authorization": f"Bearer {admin_access_token(super_admin)}"}
    prior_admin_password = admin_target.hashed_password
    prior_admin_version = admin_target.session_version
    prior_driver_password = driver_target.hashed_password
    prior_driver_version = driver_target.session_version

    admin_reset_path = f"/api/admin/admins/{admin_target.id}/reset-invitation"
    driver_reset_path = f"/api/admin/drivers/{driver_target.id}/reset-invitation"
    assert client.post(admin_reset_path, headers=collector_headers).status_code == 403
    assert client.post(driver_reset_path, headers=collector_headers).status_code == 403
    assert admin_target.hashed_password == prior_admin_password
    assert admin_target.session_version == prior_admin_version
    assert driver_target.hashed_password == prior_driver_password
    assert driver_target.session_version == prior_driver_version

    # Only a Super Admin may reset a Municipal Admin invitation.
    assert client.post(admin_reset_path, headers=municipal_headers).status_code == 403
    assert client.post(admin_reset_path, headers=super_headers).status_code == 410
    # Reset requests are metadata-free and must use the offline CLI.
    assert client.post(driver_reset_path, headers=municipal_headers).status_code == 410


def test_collector_denied_and_municipal_admin_can_change_in_scope_account_status(iam_context):
    db, create_user, _ = iam_context
    collector = create_user("collector", ward="Ward A")
    municipal_admin = create_user("admin", ward="Ward A")
    super_admin = create_user("admin", is_super_admin=True, ward="Ward A")
    target = create_user("driver", ward="Ward A")
    path = f"/api/admin/accounts/{target.id}/status"
    payload = {"account_status": "suspended", "reason": "Ward operational review"}

    assert client.patch(
        path, headers={"Authorization": f"Bearer {admin_access_token(collector)}"}, json=payload,
    ).status_code == 403
    allowed = client.patch(
        path, headers={"Authorization": f"Bearer {admin_access_token(municipal_admin)}"}, json=payload,
    )
    assert allowed.status_code == 200
    assert target.account_status == "suspended"
    # Reactivate for the Super Admin assertion below.
    target.account_status = "active"
    target.is_active = True
    db.commit()
    response = client.patch(
        path, headers={"Authorization": f"Bearer {admin_access_token(super_admin)}"}, json=payload,
    )
    assert response.status_code == 200
    assert response.json()["account_status"] == "suspended"
    db.refresh(target)
    assert target.account_status == "suspended"


def test_collector_cannot_change_notification_read_state(iam_context):
    db, create_user, _ = iam_context
    collector = create_user("collector", ward="Ward A")
    municipal_admin = create_user("admin", ward="Ward A")
    notification = Notification(
        title="Phase 1J read-state test", message="test", is_broadcast=True,
        recipient_id=None, is_read=False,
    )
    db.add(notification)
    db.commit()
    path = f"/api/admin/notifications/{notification.id}/read"

    denied = client.patch(
        path, headers={"Authorization": f"Bearer {admin_access_token(collector)}"},
    )
    assert denied.status_code == 403
    db.refresh(notification)
    assert notification.is_read is False

    allowed = client.patch(
        path, headers={"Authorization": f"Bearer {admin_access_token(municipal_admin)}"},
    )
    assert allowed.status_code == 200
    try:
        db.refresh(notification)
        assert notification.is_read is True
    finally:
        db.delete(notification)
        db.commit()


def test_collector_complaint_image_authorization_is_ward_scoped(iam_context, monkeypatch):
    db, create_user, _ = iam_context
    collector = create_user("collector", ward="Ward A")
    inside = Complaint(
        tracking_number=f"EP-IMG-A-{uuid.uuid4().hex[:8]}", ward="Ward A",
        location_address="A", waste_type="Mixed Waste", image_url="private/object-a",
    )
    outside = Complaint(
        tracking_number=f"EP-IMG-B-{uuid.uuid4().hex[:8]}", ward="Ward B",
        location_address="B", waste_type="Mixed Waste", image_url="private/object-b",
    )
    db.add_all([inside, outside])
    db.commit()
    monkeypatch.setattr(ComplaintService, "_format_resolved_image", staticmethod(lambda complaint: {"id": complaint.id}))

    assert ComplaintService.authorize_and_resolve_image(db, str(inside.id), current_user=collector)
    with pytest.raises(Exception) as excinfo:
        ComplaintService.authorize_and_resolve_image(db, str(outside.id), current_user=collector)
    assert getattr(excinfo.value, "status_code", None) == 403
    db.delete(inside)
    db.delete(outside)
    db.commit()
