"""Disposable PostgreSQL validation for migration 007 and its rollback.

Skipped unless ECOLPULSE_DISPOSABLE_POSTGRES_URL points at a throwaway
PostgreSQL database and ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION is
DISPOSABLE. The application test suite never uses this module's database, and
this module never falls back to SQLite. Each module owns a unique test schema.

Safety guards (all must pass before any DDL runs):
- Neon and Render hosts are refused unconditionally.
- Only loopback hosts are allowed.
- The database name must identify a disposable target and must not look production-like.
- An explicit disposable-target authorization is required.
- Every test rebuilds only its own isolated schema.

Example:
    createdb ecopulse_migration_test
    ECOLPULSE_DISPOSABLE_POSTGRES_URL=postgresql://postgres:postgres@127.0.0.1:5432/ecopulse_migration_test \
    ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION=DISPOSABLE \
        python -m pytest server/tests/test_postgres_migration_007.py -q

The schema is created from the current SQLAlchemy models, then reduced to a
representative pre-007 shape (IAM columns and tables removed) before migration
007 is applied.
"""

import os
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2")

from sqlalchemy import inspect, text

import server.models  # noqa: F401  # register all tables on Base.metadata
from server.database.db import Base

PG_URL = os.getenv("ECOLPULSE_DISPOSABLE_POSTGRES_URL", "").strip()
PG_AUTHORIZATION = os.getenv("ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION", "").strip()

from server.tests.postgres_test_support import (
    create_isolated_postgres_engine,
    drop_isolated_postgres_schema,
    isolated_schema_name,
    validate_postgres_test_target,
)

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="Set an explicitly authorized ECOLPULSE_DISPOSABLE_POSTGRES_URL for PostgreSQL tests.",
)

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
MIGRATION_007 = MIGRATIONS / "007_municipal_iam.sql"
MIGRATION_DOWN = MIGRATIONS / "007_municipal_iam_down.sql"
LEGACY_VERIFICATION = MIGRATIONS / "007_municipal_iam_legacy_verification.sql"

IAM_COLUMNS = (
    "mfa_enrolled_at",
    "deactivated_at",
    "suspended_at",
    "activated_at",
    "verified_at",
    "approved_by_id",
    "created_by_id",
    "vehicle_assignment",
    "account_status",
    "session_version",
    "mfa_last_verified_step",
    "mfa_enabled",
    "mfa_secret_enc",
    "is_super_admin",
    "is_verified",
)

# employee_id, role, is_active, approver employee_id
PRE_MIGRATION_ACCOUNTS = (
    ("CITIZEN-001", "citizen", True, None),
    ("DRIVER-ACTIVE", "driver", True, "SUPER-001"),
    ("COLLECTOR-ACTIVE", "collector", True, "SUPER-001"),
    ("ADMIN-LEGACY", "admin", True, "SUPER-001"),
    ("DRIVER-INACTIVE", "driver", False, None),
    ("ADMIN-NULL-ACTIVE", "admin", None, None),
    # Inactive control: it must be excluded from the mandatory approval
    # coverage check. The non-super-admin approver test activates and verifies
    # it explicitly before using it as an approver.
    ("ADMIN-MUNICIPAL", "admin", False, None),
    ("SUPER-001", "admin", True, None),
)

APPROVALS = tuple(
    (employee_id, role, approver_employee_id)
    for employee_id, role, _, approver_employee_id in PRE_MIGRATION_ACCOUNTS
    if approver_employee_id
)


@pytest.fixture(scope="module")
def pg_engine():
    try:
        url = validate_postgres_test_target(PG_URL, PG_AUTHORIZATION)
    except Exception as exc:
        pytest.fail(f"Refusing unsafe disposable PostgreSQL test target: {exc}")
    schema = isolated_schema_name("migration_007")
    engine = create_isolated_postgres_engine(url, schema)
    try:
        yield engine
    finally:
        try:
            Base.metadata.drop_all(bind=engine)
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE IF EXISTS schema_migrations"))
        finally:
            engine.dispose()
            drop_isolated_postgres_schema(url, schema)


def _run_sql(engine, sql: str) -> None:
    connection = engine.raw_connection()
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
    finally:
        connection.close()


def _run_sql_expecting_error(engine, sql: str, expected_message: str) -> None:
    connection = engine.raw_connection()
    connection.autocommit = True
    try:
        with pytest.raises(psycopg2.Error) as excinfo:
            with connection.cursor() as cursor:
                cursor.execute(sql)
    finally:
        connection.close()
    assert expected_message in str(excinfo.value)


def _reset_to_pre_migration(engine) -> None:
    """Rebuild the schema, then remove IAM objects to emulate the pre-007 state."""
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS schema_migrations"))
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS security_audit_events CASCADE"))
        connection.execute(text("DROP TABLE IF EXISTS account_invitations CASCADE"))
        for column in IAM_COLUMNS:
            connection.execute(text(f"ALTER TABLE users DROP COLUMN IF EXISTS {column} CASCADE"))
        for index, (employee_id, role, is_active, _) in enumerate(PRE_MIGRATION_ACCOUNTS):
            connection.execute(
                text(
                    "INSERT INTO users ("
                    "full_name, email, employee_id, hashed_password, role, ward, phone, "
                    "eco_coins, is_active, failed_attempts, is_locked"
                    ") VALUES ("
                    ":full_name, :email, :employee_id, 'placeholder-hash', :role, "
                    "'Ward 1', :phone, 100, :is_active, 0, FALSE"
                    ")"
                ),
                {
                    "full_name": f"Legacy {employee_id}",
                    "email": f"{employee_id.lower()}@legacy.test",
                    "employee_id": employee_id,
                    "role": role,
                    "phone": f"90000000{index:02d}",
                    "is_active": is_active,
                },
            )


def _apply_007(engine) -> None:
    _run_sql(engine, MIGRATION_007.read_text(encoding="utf-8"))


def _promote_super_admin(engine) -> None:
    """Equivalent authorization state to the offline Super Admin bootstrap."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE users SET is_super_admin = TRUE, is_verified = TRUE, "
                "verified_at = NOW(), is_active = TRUE, account_status = 'active' "
                "WHERE employee_id = 'SUPER-001'"
            )
        )


def _approval_script(approvals) -> str:
    script = LEGACY_VERIFICATION.read_text(encoding="utf-8")
    inserts = "\n".join(
        "INSERT INTO approved_legacy_accounts "
        "(employee_id, role, approved_by_employee_id, evidence_reference) "
        f"VALUES ('{employee_id}', '{role}', '{approver}', 'case-{employee_id}');"
        for employee_id, role, approver in approvals
    )
    marker = "-- Example only;"
    assert marker in script
    return script.replace(marker, f"{inserts}\n{marker}", 1)


def _scalar(engine, sql: str, **params):
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar()


def _user_row(engine, employee_id: str):
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT is_verified, verified_at, approved_by_id, account_status, "
                "is_active, is_super_admin FROM users WHERE employee_id = :employee_id"
            ),
            {"employee_id": employee_id},
        ).one()


def _prepare_migrated(engine) -> None:
    _reset_to_pre_migration(engine)
    _apply_007(engine)
    _promote_super_admin(engine)


def test_007_backfills_legacy_accounts_and_creates_iam_objects(pg_engine):
    _reset_to_pre_migration(pg_engine)
    _apply_007(pg_engine)

    inspector = inspect(pg_engine)
    user_columns = {column["name"]: column for column in inspector.get_columns("users")}
    assert set(IAM_COLUMNS) <= set(user_columns)
    assert user_columns["is_verified"]["nullable"] is False
    assert user_columns["is_super_admin"]["nullable"] is False
    assert user_columns["session_version"]["nullable"] is False
    assert user_columns["account_status"]["nullable"] is False
    assert "false" in str(user_columns["is_super_admin"]["default"]).lower()
    assert "false" in str(user_columns["is_verified"]["default"]).lower()
    assert "active" in str(user_columns["account_status"]["default"])
    assert "0" in str(user_columns["eco_coins"]["default"])

    tables = set(inspector.get_table_names())
    assert {"account_invitations", "security_audit_events"} <= tables
    index_names = {index["name"] for index in inspector.get_indexes("account_invitations")}
    index_names |= {index["name"] for index in inspector.get_indexes("security_audit_events")}
    assert {
        "ix_account_invitations_user_id",
        "ix_security_audit_events_actor_id",
        "ix_security_audit_events_target_user_id",
        "ix_security_audit_events_action",
        "ix_security_audit_events_created_at",
    } <= index_names

    citizen = _user_row(pg_engine, "CITIZEN-001")
    active_driver = _user_row(pg_engine, "DRIVER-ACTIVE")
    inactive_driver = _user_row(pg_engine, "DRIVER-INACTIVE")
    null_active_admin = _user_row(pg_engine, "ADMIN-NULL-ACTIVE")

    assert citizen.is_verified is True, "Citizens must remain verified after the backfill."
    assert active_driver.is_verified is False, "Legacy staff must not be trusted implicitly."
    assert inactive_driver.account_status == "suspended"
    assert null_active_admin.account_status == "active"
    assert null_active_admin.is_active is None, "A NULL is_active must not violate NOT NULL."


def test_007_is_safe_to_rerun_before_and_after_legacy_approval(pg_engine):
    _prepare_migrated(pg_engine)

    _run_sql(pg_engine, _approval_script(APPROVALS))
    approved_before = _user_row(pg_engine, "DRIVER-ACTIVE")
    assert approved_before.is_verified is True

    _apply_007(pg_engine)

    approved_after = _user_row(pg_engine, "DRIVER-ACTIVE")
    assert approved_after.is_verified is True
    assert approved_after.approved_by_id is not None
    assert _user_row(pg_engine, "CITIZEN-001").is_verified is True
    assert _user_row(pg_engine, "DRIVER-INACTIVE").is_verified is False


def test_legacy_verification_accepts_only_active_verified_super_admin(pg_engine):
    _prepare_migrated(pg_engine)
    _run_sql(pg_engine, _approval_script(APPROVALS))

    super_admin_id = _scalar(
        pg_engine,
        "SELECT id FROM users WHERE employee_id = 'SUPER-001'",
    )
    for employee_id in ("DRIVER-ACTIVE", "COLLECTOR-ACTIVE", "ADMIN-LEGACY"):
        row = _user_row(pg_engine, employee_id)
        assert row.is_verified is True
        assert row.approved_by_id == super_admin_id

    audits = _scalar(
        pg_engine,
        "SELECT COUNT(*) FROM security_audit_events "
        "WHERE action = 'legacy_account_verified' AND actor_id = :actor_id",
        actor_id=super_admin_id,
    )
    assert audits == 3
    assert _user_row(pg_engine, "DRIVER-INACTIVE").is_verified is False


def test_legacy_verification_rejects_unknown_approver(pg_engine):
    _prepare_migrated(pg_engine)
    approvals = tuple((employee, role, "GHOST-APPROVER") for employee, role, _ in APPROVALS)
    _run_sql_expecting_error(
        pg_engine,
        _approval_script(approvals),
        "Every approver must be an existing active, verified Super Admin account",
    )
    assert _user_row(pg_engine, "DRIVER-ACTIVE").is_verified is False


def test_legacy_verification_rejects_non_super_admin_approver(pg_engine):
    _prepare_migrated(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE users SET is_verified = TRUE, verified_at = NOW(), "
                "is_active = TRUE, account_status = 'active', is_super_admin = FALSE "
                "WHERE employee_id = 'ADMIN-MUNICIPAL'"
            )
        )
    approvals = tuple((employee, role, "ADMIN-MUNICIPAL") for employee, role, _ in APPROVALS)
    _run_sql_expecting_error(
        pg_engine,
        _approval_script(approvals),
        "Every approver must be an existing active, verified Super Admin account",
    )


def test_legacy_verification_rejects_suspended_super_admin(pg_engine):
    _prepare_migrated(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE users SET is_active = FALSE, account_status = 'suspended' "
                "WHERE employee_id = 'SUPER-001'"
            )
        )
    _run_sql_expecting_error(
        pg_engine,
        _approval_script(APPROVALS),
        "Every approver must be an existing active, verified Super Admin account",
    )


def test_legacy_verification_rejects_incomplete_coverage(pg_engine):
    _prepare_migrated(pg_engine)
    incomplete = tuple(approval for approval in APPROVALS if approval[0] == "DRIVER-ACTIVE")
    _run_sql_expecting_error(
        pg_engine,
        _approval_script(incomplete),
        "must cover every active legacy municipal account",
    )


def test_invitation_and_audit_constraints_behave_correctly(pg_engine):
    _prepare_migrated(pg_engine)
    super_admin_id = _scalar(pg_engine, "SELECT id FROM users WHERE employee_id = 'SUPER-001'")

    with pg_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO account_invitations (user_id, role, token_hash, expires_at) "
                "VALUES (:user_id, 'driver', :token_hash, NOW() + INTERVAL '1 hour')"
            ),
            {"user_id": super_admin_id, "token_hash": "a" * 64},
        )

    with pytest.raises(Exception):
        with pg_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO account_invitations (user_id, role, token_hash, expires_at) "
                    "VALUES (:user_id, 'driver', :token_hash, NOW() + INTERVAL '1 hour')"
                ),
                {"user_id": super_admin_id, "token_hash": "a" * 64},
            )

    with pg_engine.begin() as connection:
        disposable = connection.execute(
            text(
                "INSERT INTO users (full_name, role, is_active, is_verified, account_status) "
                "VALUES ('Cascade Probe', 'driver', TRUE, FALSE, 'pending') RETURNING id"
            )
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO account_invitations (user_id, role, token_hash, expires_at) "
                "VALUES (:user_id, 'driver', :token_hash, NOW() + INTERVAL '1 hour')"
            ),
            {"user_id": disposable, "token_hash": "b" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO security_audit_events (target_user_id, action) "
                "VALUES (:user_id, 'cascade_probe')"
            ),
            {"user_id": disposable},
        )
        connection.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": disposable})

    assert _scalar(pg_engine, "SELECT COUNT(*) FROM account_invitations") == 1
    assert _scalar(
        pg_engine,
        "SELECT target_user_id FROM security_audit_events WHERE action = 'cascade_probe'",
    ) is None


def test_rollback_removes_iam_objects_and_restores_coin_default(pg_engine):
    _prepare_migrated(pg_engine)
    _run_sql(pg_engine, MIGRATION_DOWN.read_text(encoding="utf-8"))

    inspector = inspect(pg_engine)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert not set(IAM_COLUMNS) & user_columns
    assert "account_invitations" not in set(inspector.get_table_names())
    assert "security_audit_events" not in set(inspector.get_table_names())
    eco_coins = next(
        column for column in inspector.get_columns("users") if column["name"] == "eco_coins"
    )
    assert "100" in str(eco_coins["default"])
