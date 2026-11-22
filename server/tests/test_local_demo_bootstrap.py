from __future__ import annotations

import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from server.scripts.bootstrap_local_demo import (
    LocalDemoSetupError,
    _disable_external_delivery,
    _local_demo_database_path,
    _safe_failure_message,
    _validate_initial_password,
)


def _demo_env(path: Path, **overrides):
    values = {
        "ENV": "development",
        "DATABASE_URL": f"sqlite:///{path.as_posix()}",
    }
    values.update(overrides)
    return values


def test_local_demo_accepts_only_new_named_temp_sqlite_target(tmp_path):
    name = f"ecopulse-demo-{uuid.uuid4().hex}.sqlite3"
    target = tmp_path / name
    resolved = _local_demo_database_path(_demo_env(target), temp_root=tmp_path)
    assert resolved == target.resolve()
    assert not target.exists()


@pytest.mark.parametrize("env", ["production", "staging", "test", ""])
def test_local_demo_refuses_non_development_environment(tmp_path, env):
    target = tmp_path / f"ecopulse-demo-{uuid.uuid4().hex}.sqlite3"
    with pytest.raises(RuntimeError, match="ENV=development"):
        _local_demo_database_path(_demo_env(target, ENV=env), temp_root=tmp_path)


def test_local_demo_refuses_conflicting_environment_variable(tmp_path):
    target = tmp_path / f"ecopulse-demo-{uuid.uuid4().hex}.sqlite3"
    with pytest.raises(RuntimeError, match="conflicting ENVIRONMENT"):
        _local_demo_database_path(_demo_env(target, ENVIRONMENT="production"), temp_root=tmp_path)


@pytest.mark.parametrize("url", [
    "postgresql://user:password@localhost/ecopulse_test",
    "sqlite:///./ecopulse-demo-local.sqlite3",
    "sqlite:///:memory:",
    "sqlite://host/share/ecopulse-demo-local.sqlite3",
])
def test_local_demo_refuses_remote_or_unconfined_targets(tmp_path, url):
    with pytest.raises(RuntimeError):
        _local_demo_database_path(_demo_env(tmp_path / "unused.sqlite3", DATABASE_URL=url), temp_root=tmp_path)


def test_local_demo_refuses_existing_database_file(tmp_path):
    target = tmp_path / f"ecopulse-demo-{uuid.uuid4().hex}.sqlite3"
    target.touch()
    with pytest.raises(RuntimeError, match="new database file"):
        _local_demo_database_path(_demo_env(target), temp_root=tmp_path)


def test_local_demo_requires_explicit_database_url():
    with pytest.raises(RuntimeError, match="new local SQLite file"):
        _local_demo_database_path({"ENV": "development", "DATABASE_URL": ""})


def test_local_demo_disables_inherited_external_delivery_credentials(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "must-be-cleared")
    monkeypatch.setenv("META_WHATSAPP_ACCESS_TOKEN", "must-be-cleared")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "must-be-cleared")

    _disable_external_delivery()

    assert os.environ["WHATSAPP_TOKEN"] == ""
    assert os.environ["META_WHATSAPP_ACCESS_TOKEN"] == ""
    assert os.environ["TWILIO_AUTH_TOKEN"] == ""
    assert os.environ["OTP_DELIVERY_PROVIDER"] == "development"
    assert os.environ["MEDIA_STORAGE_BACKEND"] == "local"


def test_local_demo_password_validation_reports_policy_without_echoing_input():
    password = "weak-password"
    with pytest.raises(LocalDemoSetupError) as error:
        _validate_initial_password(password)

    message = _safe_failure_message(error.value, "validating the initial password")
    assert "12" in message and "72" in message
    assert "uppercase" in message and "lowercase" in message and "symbol" in message
    assert password not in message


def test_weak_password_is_rejected_before_disposable_database_is_created():
    database = Path(tempfile.gettempdir()) / f"ecopulse-demo-{uuid.uuid4().hex}.sqlite3"
    password = "weak-password"
    employee_id = f"LOCAL-SUP-{uuid.uuid4().hex[:8].upper()}"
    environment = os.environ.copy()
    environment.update({
        "ENV": "development",
        "ENVIRONMENT": "development",
        "DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "SECRET_KEY": secrets.token_urlsafe(48),
        "MFA_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        "MUNICIPAL_EMPLOYEE_ALLOWLIST": employee_id,
        "MUNICIPAL_SUPER_ADMIN_EMPLOYEE_ID": employee_id,
        "MUNICIPAL_SUPER_ADMIN_LOGIN_ID": f"SUP-{uuid.uuid4().hex[:8].upper()}",
        "MUNICIPAL_SUPER_ADMIN_NAME": "Local Demo Super Admin",
        "MUNICIPAL_SUPER_ADMIN_EMAIL": f"{uuid.uuid4().hex}@example.test",
        "MUNICIPAL_SUPER_ADMIN_PHONE": f"9{uuid.uuid4().int % 1_000_000_000:09d}",
        "LOCAL_DEMO_TEST_PASSWORD": password,
    })
    runner = (
        "import os; from server.scripts import bootstrap_local_demo as d; "
        "d._read_password_no_echo = lambda _: os.environ['LOCAL_DEMO_TEST_PASSWORD']; "
        "raise SystemExit(d.main())"
    )
    result = subprocess.run(
        [sys.executable, "-c", runner],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 2
    assert "12–72 UTF-8 bytes" in result.stdout
    assert password not in result.stdout + result.stderr
    assert not database.exists()


def test_local_demo_bootstrap_creates_all_roles_only_in_a_new_temp_database():
    database = Path(tempfile.gettempdir()) / f"ecopulse-demo-{uuid.uuid4().hex}.sqlite3"
    password = secrets.token_urlsafe(24) + "A1!"
    employee_id = f"LOCAL-SUP-{uuid.uuid4().hex[:8].upper()}"
    environment = os.environ.copy()
    environment.update({
        "ENV": "development",
        "ENVIRONMENT": "development",
        "DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "SECRET_KEY": secrets.token_urlsafe(48),
        "MFA_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        "MUNICIPAL_EMPLOYEE_ALLOWLIST": employee_id,
        "MUNICIPAL_SUPER_ADMIN_EMPLOYEE_ID": employee_id,
        "MUNICIPAL_SUPER_ADMIN_LOGIN_ID": f"SUP-{uuid.uuid4().hex[:8].upper()}",
        "MUNICIPAL_SUPER_ADMIN_NAME": "Local Demo Super Admin",
        "MUNICIPAL_SUPER_ADMIN_EMAIL": f"{uuid.uuid4().hex}@example.test",
        "MUNICIPAL_SUPER_ADMIN_PHONE": f"9{uuid.uuid4().int % 1_000_000_000:09d}",
        "LOCAL_DEMO_TEST_PASSWORD": password,
    })
    runner = (
        "import os; from server.scripts import bootstrap_local_demo as d; "
        "d._read_password_no_echo = lambda _: os.environ['LOCAL_DEMO_TEST_PASSWORD']; "
        "raise SystemExit(d.main())"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", runner],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert password not in result.stdout
        assert password not in result.stderr
        assert f"$env:DATABASE_URL = 'sqlite:///{database.as_posix()}'" in result.stdout
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        try:
            roles = {row[0] for row in connection.execute("select distinct role from users")}
            assert {"admin", "driver", "collector", "citizen"}.issubset(roles)
            assert connection.execute("select count(*) from users where is_super_admin = 1").fetchone()[0] == 1
        finally:
            connection.close()
    finally:
        for path in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
            if path.exists():
                path.unlink()
