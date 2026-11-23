import hashlib
import os
import stat
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import server.models  # noqa: F401
from server.database.db import Base
from server.database.db import get_db
from server.models.account_invitation import AccountInvitation
from server.models.user import User
from server.scripts import issue_invitation_offline as offline
from server.services.iam_service import _totp_code, encrypt_mfa_secret, issue_invitation
from server.tests.iam_test_helpers import TEST_TOTP_SECRET
from server.utils.security import hash_password
from server.main import app
from fastapi.testclient import TestClient


def _database(tmp_path):
    url = f"sqlite:///{(tmp_path / 'ecopulse_test_offline_invites.db').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return url, engine


def _operator(db, *, role="admin", super_admin=False):
    actor = User(
        full_name="Offline Operator",
        employee_id=f"OFFLINE-{uuid.uuid4().hex[:10]}",
        email=f"operator-{uuid.uuid4().hex[:8]}@example.test",
        role=role,
        is_super_admin=super_admin,
        is_active=True,
        is_verified=True,
        account_status="active",
        hashed_password=hash_password("ValidPassword123!"),
        mfa_enabled=True,
        mfa_secret_enc=encrypt_mfa_secret(TEST_TOTP_SECRET),
    )
    db.add(actor)
    db.commit()
    db.refresh(actor)
    return actor


def _args(url, output, *, role="collector", reset_id=None, **extra):
    args = [
        "--url", url, "--environment", "test",
        "--authorize-disposable-target", "DISPOSABLE",
        "--actor-employee-id", extra.pop("actor_employee_id"),
        "--role", role,
        "--frontend-origin", "https://portal.example.test",
        "--output-file", str(output),
    ]
    if reset_id is not None:
        args += ["--reset-user-id", str(reset_id)]
    else:
        args += ["--full-name", "Synthetic Invitee", "--employee-id", extra.get("invitee_employee_id", f"SYN-{uuid.uuid4().hex[:8]}")]
        for key in ("email", "phone", "ward", "vehicle_assignment"):
            value = extra.get(key)
            if value:
                args += [f"--{key.replace('_', '-')}", value]
    return args


def _run(db, url, output, actor, *, role="collector", reset_id=None, input_value="ISSUE", **extra):
    step = int(datetime.now(timezone.utc).timestamp() // 30)
    actor.mfa_last_verified_step = step - 1
    db.commit()
    code = _totp_code(TEST_TOTP_SECRET, step)
    credentials = iter(("ValidPassword123!", code))
    return offline.main(
        _args(url, output, role=role, reset_id=reset_id, actor_employee_id=actor.employee_id, **extra),
        input_fn=lambda _prompt: input_value,
        password_fn=lambda _prompt: next(credentials),
    )


def test_offline_cli_issues_hash_only_invitation_to_protected_file(tmp_path, monkeypatch, capsys):
    url, engine = _database(tmp_path)
    output = tmp_path.parent / f"invitation-{uuid.uuid4().hex}.txt"
    monkeypatch.setenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", "")
    with Session(engine) as db:
        actor = _operator(db)
        assert _run(db, url, output, actor, role="collector", ward="Ward 8") == 0
        message = capsys.readouterr().out
        assert "activation_token" not in message
        assert "#token=" not in message
        invitee = db.query(User).filter(User.employee_id.like("SYN-%")).one()
        invitation = db.query(AccountInvitation).filter_by(user_id=invitee.id).one()
        token = output.read_text(encoding="utf-8").strip().split("#token=", 1)[1]
        assert invitation.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in invitation.token_hash
        assert invitee.ward == "Ward 8" and invitee.role == "collector"
    if os.name != "nt":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
    output.unlink()
    engine.dispose()


def test_offline_cli_refuses_existing_output_and_unsafe_targets(tmp_path, monkeypatch, capsys):
    url, engine = _database(tmp_path)
    output = tmp_path.parent / f"existing-{uuid.uuid4().hex}.txt"
    output.write_text("do not overwrite", encoding="utf-8")
    with Session(engine) as db:
        actor = _operator(db)
        assert _run(db, url, output, actor, ward="Ward 1") == 1
        assert output.read_text(encoding="utf-8") == "do not overwrite"
    with pytest.raises(SystemExit) as missing_url:
        offline.main(["--role", "driver"], input_fn=lambda _: "ISSUE")
    assert missing_url.value.code == 2
    unsafe = _args("postgresql://x:x@db.example.com/ecopulse_test", output, actor_employee_id="x", ward="Ward 1")
    assert offline.main(unsafe, input_fn=lambda _: "ISSUE") == 2
    assert "activation_token" not in capsys.readouterr().err
    output.unlink()
    engine.dispose()


def test_offline_cli_reset_invalidates_old_invitation_before_replacement(tmp_path):
    url, engine = _database(tmp_path)
    output = tmp_path.parent / f"reset-{uuid.uuid4().hex}.txt"
    with Session(engine) as db:
        actor = _operator(db)
        target = User(
            full_name="Synthetic Invitee", employee_id=f"SYN-{uuid.uuid4().hex[:8]}",
            role="driver", ward="Ward 2", phone="9876501234", is_active=False,
            is_verified=False, account_status="pending",
        )
        db.add(target)
        db.flush()
        old_token = issue_invitation(db, target, "driver", actor)
        db.commit()
        assert _run(db, url, output, actor, role="driver", reset_id=target.id, input_value="RESET") == 0
        invitations = db.query(AccountInvitation).filter_by(user_id=target.id).order_by(AccountInvitation.id).all()
        assert len(invitations) == 2
        assert invitations[0].revoked_at is not None
        assert invitations[1].revoked_at is None
        assert invitations[0].token_hash == hashlib.sha256(old_token.encode()).hexdigest()
    output.unlink()
    engine.dispose()


def test_offline_cli_enforces_role_hierarchy_without_admin_allowlist(tmp_path, monkeypatch):
    url, engine = _database(tmp_path)
    output = tmp_path.parent / f"role-{uuid.uuid4().hex}.txt"
    with Session(engine) as db:
        actor = _operator(db)
        with pytest.raises(ValueError, match="Only Super Admin"):
            offline._validate_role(actor, "admin", "MUNI-1")
        super_admin = _operator(db, super_admin=True)
        offline._validate_role(super_admin, "admin", "MUNI-1")
        offline._validate_role(super_admin, "admin", "ARBITRARY-UNIQUE-OFFICIAL-ID")
        with pytest.raises(ValueError, match="requires an employee ID"):
            offline._validate_role(super_admin, "admin", None)
        with pytest.raises(ValueError, match="only to provision Municipal Admins"):
            offline._validate_role(super_admin, "driver", "DRV-1")
    assert not output.exists()
    engine.dispose()


@pytest.mark.parametrize("role,super_admin,extra", [
    ("driver", False, {"phone": "9876504321", "ward": "Ward 2"}),
    ("admin", True, {}),
])
def test_offline_cli_authorized_staff_role_issuance(tmp_path, monkeypatch, role, super_admin, extra):
    url, engine = _database(tmp_path)
    output = tmp_path.parent / f"staff-{uuid.uuid4().hex}.txt"
    employee_id = f"ROLE-{uuid.uuid4().hex[:8]}"
    with Session(engine) as db:
        actor = _operator(db, super_admin=super_admin)
        monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)
        assert _run(
            db, url, output, actor, role=role,
            invitee_employee_id=employee_id, **extra,
        ) == 0
        invitee = db.query(User).filter_by(employee_id=employee_id).one()
        invitation = db.query(AccountInvitation).filter_by(user_id=invitee.id).one()
        assert invitee.role == role
        assert invitation.role == role
        assert output.read_text(encoding="utf-8").startswith("https://portal.example.test/activate#token=")
    output.unlink()
    engine.dispose()


def test_offline_cli_requires_collector_ward_and_verified_operator(tmp_path, capsys):
    url, engine = _database(tmp_path)
    output = tmp_path.parent / f"rejected-{uuid.uuid4().hex}.txt"
    with Session(engine) as db:
        actor = _operator(db)
        args = _args(url, output, role="collector", actor_employee_id=actor.employee_id)
        step = int(datetime.now(timezone.utc).timestamp() // 30)
        actor.mfa_last_verified_step = step - 1
        db.commit()
        credentials = iter(("ValidPassword123!", _totp_code(TEST_TOTP_SECRET, step)))
        assert offline.main(args, input_fn=lambda _: "ISSUE", password_fn=lambda _: next(credentials)) == 1
        assert db.query(User).filter(User.employee_id.like("SYN-%")).count() == 0
        assert not output.exists()
        assert "requires --ward" in capsys.readouterr().err
        actor.mfa_last_verified_step = step - 1
        db.commit()
        credentials = iter(("wrong-password", _totp_code(TEST_TOTP_SECRET, step)))
        assert offline.main(args, input_fn=lambda _: "ISSUE", password_fn=lambda _: next(credentials)) == 1
        assert not output.exists()
    engine.dispose()


def test_offline_cli_invitation_activates_through_existing_activation_api(tmp_path):
    url, engine = _database(tmp_path)
    output = tmp_path / "activation-link.txt"
    with Session(engine) as db:
        actor = _operator(db)
        assert _run(db, url, output, actor, role="collector", ward="Ward 9") == 0
        activation_url = output.read_text(encoding="utf-8").strip()
        token = activation_url.split("#token=", 1)[1]

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).post(
            "/api/auth/collectors/activate",
            json={"token": token, "password": "SyntheticCollectorPassword123!"},
        )
        assert response.status_code == 200
        with Session(engine) as verify_db:
            invitee = verify_db.query(User).filter(User.employee_id.like("SYN-%")).one()
            invitation = verify_db.query(AccountInvitation).filter_by(user_id=invitee.id).one()
            assert invitee.is_active is True
            assert invitee.is_verified is True
            assert invitation.consumed_at is not None
            reused = TestClient(app).post(
                "/api/auth/collectors/activate",
                json={"token": token, "password": "SyntheticCollectorPassword123!"},
            )
            assert reused.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)
        output.unlink()
        engine.dispose()
