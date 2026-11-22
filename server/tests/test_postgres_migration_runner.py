"""Disposable PostgreSQL validation for the explicit migration runner.

Skipped unless ECOLPULSE_DISPOSABLE_POSTGRES_URL points at a throwaway
PostgreSQL database and ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION is
DISPOSABLE. This module creates and drops only its own uniquely named schema.
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

psycopg2 = pytest.importorskip("psycopg2")

from sqlalchemy import text

import server.models  # noqa: F401  # register all tables on Base.metadata
from server.database.db import Base
from server.models.security_audit_event import SecurityAuditEvent
from server.models.user import User
from server.database.migrations_runner import (
    HISTORY_TABLE,
    MIGRATION_LOCK_KEY,
    Migration,
    MigrationError,
    PrerequisiteError,
    adopt_existing,
    apply_pending,
    diagnose,
    discover_migrations,
    _missing_objects,
    _inspect_index_definitions,
    migration_lock,
    status,
)

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

_TEST_URL = None
_TEST_SCHEMA = None


@pytest.fixture(scope="module")
def pg_engine():
    global _TEST_URL, _TEST_SCHEMA
    try:
        url = validate_postgres_test_target(PG_URL, PG_AUTHORIZATION)
    except Exception as exc:
        pytest.fail(f"Refusing unsafe disposable PostgreSQL test target: {exc}")
    schema = isolated_schema_name("migration_runner")
    _TEST_URL, _TEST_SCHEMA = url, schema
    engine = create_isolated_postgres_engine(url, schema)
    try:
        _drop_everything(engine)
        yield engine
    finally:
        try:
            _drop_everything(engine)
        finally:
            engine.dispose()
            drop_isolated_postgres_schema(url, schema)


def _drop_everything(engine) -> None:
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {HISTORY_TABLE}"))


def _reset_to_current_models(engine) -> None:
    _drop_everything(engine)
    Base.metadata.create_all(bind=engine)


def _reset_with_baseline(engine) -> None:
    _reset_to_current_models(engine)
    assert adopt_existing(engine, discover_migrations(), through_version="000") == ["000"]


def _reset_to_pre_009_user_schema(engine) -> tuple[int, int]:
    """Build the actual 008-era users/invitation shape without 009/010 fields.

    This is an explicit frozen PostgreSQL DDL snapshot of the 008 users table:
    it deliberately does not call Base.metadata.create_all(), which now
    contains the 009/010 fields and indexes under test.
    """
    _drop_everything(engine)
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(120) NOT NULL,
                email VARCHAR(120) UNIQUE,
                employee_id VARCHAR(50) UNIQUE,
                hashed_password VARCHAR(255),
                role VARCHAR(20) NOT NULL,
                ward VARCHAR(50),
                phone VARCHAR(20),
                eco_coins INTEGER DEFAULT 0,
                is_active BOOLEAN,
                failed_attempts INTEGER,
                is_locked BOOLEAN,
                is_verified BOOLEAN NOT NULL DEFAULT FALSE,
                is_super_admin BOOLEAN NOT NULL DEFAULT FALSE,
                mfa_secret_enc VARCHAR(512),
                mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                mfa_last_verified_step BIGINT,
                session_version INTEGER NOT NULL DEFAULT 0,
                account_status VARCHAR(30) NOT NULL DEFAULT 'active',
                vehicle_assignment VARCHAR(100),
                created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                approved_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                verified_at TIMESTAMPTZ,
                activated_at TIMESTAMPTZ,
                suspended_at TIMESTAMPTZ,
                deactivated_at TIMESTAMPTZ,
                mfa_enrolled_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text(
            "CREATE UNIQUE INDEX uq_users_phone ON users(phone) "
            "WHERE phone IS NOT NULL AND phone != ''"
        ))
        connection.execute(text(
            "CREATE INDEX ix_users_id ON users(id)"
        ))
        connection.execute(text(
            "CREATE INDEX ix_users_email ON users(email)"
        ))
        connection.execute(text(
            "CREATE INDEX ix_users_employee_id ON users(employee_id)"
        ))
        connection.execute(text("""
            CREATE TABLE account_invitations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL,
                token_hash VARCHAR(64) NOT NULL UNIQUE,
                created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                approved_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMPTZ NOT NULL,
                consumed_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ
            )
        """))
        connection.execute(text("""
            CREATE TABLE security_audit_events (
                id SERIAL PRIMARY KEY,
                actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                target_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                actor_employee_id VARCHAR(50),
                target_employee_id VARCHAR(50),
                action VARCHAR(80) NOT NULL,
                details TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.execute(text("""
            INSERT INTO users (
                full_name, email, employee_id, hashed_password, role, ward,
                phone, eco_coins, is_active, is_verified, account_status
            ) VALUES
                ('Legacy Citizen', 'legacy-citizen@example.test', NULL,
                 '$2b$12$legacy_hash_fixture_only', 'citizen', 'Ward 1',
                 '9876500001', 17, TRUE, TRUE, 'active'),
                ('Legacy Driver', 'legacy-driver@example.test', 'LEGACY-DRV-01',
                 '$2b$12$legacy_hash_fixture_only', 'driver', 'Ward 1',
                 '9876500002', 0, TRUE, FALSE, 'active'),
                ('Legacy Admin', 'legacy-admin@example.test', 'LEGACY-ADM-01',
                 '$2b$12$legacy_hash_fixture_only', 'admin', NULL,
                 '9876500003', 0, TRUE, FALSE, 'active')
        """))
        connection.execute(text("""
            INSERT INTO account_invitations (user_id, role, token_hash, expires_at)
            SELECT id, role, repeat('a', 64), CURRENT_TIMESTAMP + INTERVAL '1 day'
            FROM users WHERE employee_id = 'LEGACY-DRV-01'
        """))
        ids = connection.execute(text(
            "SELECT id, (SELECT id FROM users WHERE employee_id = 'LEGACY-ADM-01') "
            "FROM users WHERE email = 'legacy-citizen@example.test'"
        )).one()
    return int(ids[0]), int(ids[1])


def _run_migration_file(engine, filename: str) -> None:
    path = Path(__file__).resolve().parents[2] / "migrations" / filename
    connection = engine.raw_connection()
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(path.read_text(encoding="utf-8"))
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _apply_009_010_to_legacy_schema(engine) -> tuple[int, int]:
    user_ids = _reset_to_pre_009_user_schema(engine)
    _run_migration_file(engine, "009_secure_super_admin_bootstrap.sql")
    _run_migration_file(engine, "010_staff_temporary_password_expiry.sql")
    return user_ids


def test_postgres_009_010_upgrade_from_genuine_pre009_schema(pg_engine):
    citizen_id, driver_id = _apply_009_010_to_legacy_schema(pg_engine)

    # The runner contracts and catalog inspection must agree with the actual
    # PostgreSQL objects produced from the frozen pre-009 schema.
    assert _missing_objects(pg_engine, "009") == []
    assert _missing_objects(pg_engine, "010") == []
    assert inspect(pg_engine).get_indexes("users")

    with pg_engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT id, role, employee_id, hashed_password, eco_coins, "
            "login_id, must_change_password, temporary_password_expires_at, "
            "mfa_enrollment_expires_at FROM users ORDER BY id"
        )).all()
        invitation = connection.execute(text(
            "SELECT user_id, role, token_hash FROM account_invitations"
        )).one()
        types = connection.execute(text(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_schema = current_schema() "
            "AND table_name = 'users' AND column_name IN "
            "('temporary_password_expires_at', 'mfa_enrollment_expires_at')"
        )).all()
    assert [(row.role, row.employee_id, row.eco_coins) for row in rows] == [
        ("citizen", None, 17),
        ("driver", "LEGACY-DRV-01", 0),
        ("admin", "LEGACY-ADM-01", 0),
    ]
    assert all(row.login_id is None and row.must_change_password is False for row in rows)
    assert all(row.temporary_password_expires_at is None and row.mfa_enrollment_expires_at is None for row in rows)
    assert all(row.hashed_password == "$2b$12$legacy_hash_fixture_only" for row in rows)
    assert invitation == (driver_id, "driver", "a" * 64)
    assert {(row.column_name, row.data_type, row.is_nullable) for row in types} == {
        ("temporary_password_expires_at", "timestamp with time zone", "YES"),
        ("mfa_enrollment_expires_at", "timestamp with time zone", "YES"),
    }

    # NULL and empty login IDs remain available to legacy/unprovisioned rows;
    # non-empty IDs and the true Super Admin slot are unique.
    with pg_engine.begin() as connection:
        connection.execute(text("UPDATE users SET login_id = 'DRV001' WHERE id = :id"), {"id": driver_id})
        connection.execute(text("UPDATE users SET login_id = '' WHERE id = :id"), {"id": citizen_id})
        connection.execute(text("INSERT INTO users (full_name, role, login_id) VALUES "
                                "('Second empty login', 'citizen', '')"))
        connection.execute(text("INSERT INTO users (full_name, role, is_super_admin) "
                                "VALUES ('First Super Admin', 'admin', TRUE)"))
    with pytest.raises(IntegrityError):
        with pg_engine.begin() as connection:
            connection.execute(text("UPDATE users SET login_id = 'DRV001' WHERE id = :id"), {"id": citizen_id})
    with pytest.raises(IntegrityError):
        with pg_engine.begin() as connection:
            connection.execute(text("INSERT INTO users (full_name, role, is_super_admin) "
                                    "VALUES ('Second Super Admin', 'admin', TRUE)"))

    # In-use onboarding state prevents both downgrades and leaves each schema
    # intact after PostgreSQL aborts the self-managed transaction.
    with pg_engine.begin() as connection:
        connection.execute(text(
            "UPDATE users SET login_id = 'DRV001', must_change_password = TRUE, "
            "temporary_password_expires_at = CURRENT_TIMESTAMP + INTERVAL '1 day', "
            "mfa_enrollment_expires_at = CURRENT_TIMESTAMP + INTERVAL '1 day' "
            "WHERE id = :id"
        ), {"id": driver_id})
    with pytest.raises(psycopg2.Error):
        _run_migration_file(pg_engine, "010_staff_temporary_password_expiry_down.sql")
    with pytest.raises(psycopg2.Error):
        _run_migration_file(pg_engine, "009_secure_super_admin_bootstrap_down.sql")
    assert _missing_objects(pg_engine, "009") == []
    assert _missing_objects(pg_engine, "010") == []


def test_postgres_009_upgrade_failure_rolls_back_all_ddl(pg_engine):
    _reset_to_pre_009_user_schema(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("INSERT INTO users (full_name, role, is_super_admin) "
                                "VALUES ('Conflicting Super Admin A', 'admin', TRUE), "
                                "('Conflicting Super Admin B', 'admin', TRUE)"))

    with pytest.raises(psycopg2.Error):
        _run_migration_file(pg_engine, "009_secure_super_admin_bootstrap.sql")

    columns = {column["name"] for column in inspect(pg_engine).get_columns("users")}
    indexes = {index["name"] for index in inspect(pg_engine).get_indexes("users")}
    assert "login_id" not in columns
    assert "must_change_password" not in columns
    assert "uq_users_login_id" not in indexes
    assert "uq_users_single_super_admin" not in indexes


def test_postgres_concurrent_super_admin_bootstrap_uses_partial_unique_guard(pg_engine, monkeypatch):
    from server.scripts import bootstrap_super_admin

    _apply_009_010_to_legacy_schema(pg_engine)
    suffix = os.urandom(4).hex().upper()
    employee_id = f"STAGE8-SA-{suffix}"
    monkeypatch.setenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", employee_id)
    barrier = threading.Barrier(2)
    original_validate = bootstrap_super_admin.validate_employee_allowlist

    def synchronized_validation(value):
        original_validate(value)
        barrier.wait(timeout=15)

    monkeypatch.setattr(bootstrap_super_admin, "validate_employee_allowlist", synchronized_validation)

    def provision():
        with Session(pg_engine) as session:
            try:
                return bootstrap_super_admin.provision_super_admin(
                    session,
                    employee_id=employee_id,
                    login_id=f"SUP-{suffix}",
                    full_name="Disposable Concurrent Bootstrap Test",
                    email=f"stage8-sa-{suffix.lower()}@example.test",
                    phone="9876500101",
                    password="Stage8-Test-Password-Only!23",
                )
            except bootstrap_super_admin.BootstrapConflict:
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: provision(), range(2)))
    assert sorted(results) == [False, True]
    with pg_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users WHERE is_super_admin IS TRUE")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM security_audit_events WHERE action = 'super_admin_bootstrapped'")).scalar_one() == 1


def test_postgres_concurrent_staff_login_id_allocation_retries_unique_conflict(pg_engine, monkeypatch):
    from server.schemas.admin import StaffProvisionRequest
    from server.scripts import bootstrap_super_admin
    from server.services import staff_provisioning_service

    _apply_009_010_to_legacy_schema(pg_engine)
    suffix = os.urandom(4).hex().upper()
    employee_id = f"STAGE8-SA-{suffix}"
    monkeypatch.setenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", employee_id)
    with Session(pg_engine) as session:
        bootstrap_super_admin.provision_super_admin(
            session,
            employee_id=employee_id,
            login_id=f"SUP-{suffix}",
            full_name="Disposable Provisioning Test Admin",
            email=f"stage8-provision-admin-{suffix.lower()}@example.test",
            phone="9876500102",
            password="Stage8-Test-Password-Only!23",
        )

    barrier = threading.Barrier(4)
    local = threading.local()
    original_next = staff_provisioning_service._next_login_id

    def synchronized_first_allocation(session, prefix):
        value = original_next(session, prefix)
        if not getattr(local, "waited", False):
            local.waited = True
            barrier.wait(timeout=15)
        return value

    monkeypatch.setattr(staff_provisioning_service, "_next_login_id", synchronized_first_allocation)

    def provision(number):
        with Session(pg_engine) as session:
            actor = session.query(User).filter(User.employee_id == employee_id).one()
            request = StaffProvisionRequest(
                full_name=f"Disposable Collector {number}", role="collector",
                phone=f"98765002{number:02d}", email=f"stage8-collector-{suffix.lower()}-{number}@example.test",
                ward="Stage8 Test Ward",
            )
            return staff_provisioning_service.provision_staff_account(session, actor, request)

    with ThreadPoolExecutor(max_workers=4) as pool:
        credentials = list(pool.map(provision, range(4)))
    login_ids = [credential["login_id"] for credential in credentials]
    assert len(set(login_ids)) == 4
    assert all(login_id.startswith("COL") for login_id in login_ids)
    with Session(pg_engine) as session:
        from server.utils.security import verify_password

        persisted = session.query(User).filter(User.login_id.in_(login_ids)).all()
        assert len(persisted) == 4
        assert all(user.must_change_password and user.hashed_password for user in persisted)
        credentials_by_login = {credential["login_id"]: credential for credential in credentials}
        for user in persisted:
            temporary_password = credentials_by_login[user.login_id]["temporary_password"]
            assert user.hashed_password != temporary_password
            assert verify_password(temporary_password, user.hashed_password)
        assert session.query(SecurityAuditEvent).filter(
            SecurityAuditEvent.action == "collector_account_provisioned"
        ).count() == 4


def test_runner_applies_real_migrations_on_postgresql(pg_engine):
    _reset_to_current_models(pg_engine)
    migrations = discover_migrations()

    recorded = adopt_existing(pg_engine, migrations, through_version="000")
    assert recorded == ["000"]

    applied = apply_pending(pg_engine, migrations)
    assert applied == ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010"]

    state = status(pg_engine, migrations)
    assert state["baseline"] is True
    assert state["pending"] == []

    with pg_engine.connect() as connection:
        rows = connection.execute(
            text(f"SELECT version, method FROM {HISTORY_TABLE} ORDER BY version")
        ).fetchall()
    assert [row[0] for row in rows] == ["000", "001", "002", "003", "004", "005", "006", "007", "008", "009", "010"]
    assert {row[1] for row in rows[1:]} == {"applied"}


def test_runner_rerun_is_a_noop_on_postgresql(pg_engine):
    migrations = discover_migrations()
    _reset_with_baseline(pg_engine)
    assert apply_pending(pg_engine, migrations) == ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010"]

    assert apply_pending(pg_engine, migrations) == []
    assert status(pg_engine, migrations)["pending"] == []


def test_runner_refuses_concurrent_execution_on_postgresql(pg_engine):
    _reset_with_baseline(pg_engine)
    holder = pg_engine.raw_connection()
    try:
        holder.autocommit = True
        with holder.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        with pytest.raises(MigrationError) as excinfo:
            apply_pending(pg_engine, discover_migrations())
    finally:
        holder.close()

    assert "advisory lock" in str(excinfo.value)


def test_failed_script_rolls_back_managed_transaction(pg_engine):
    _reset_with_baseline(pg_engine)
    broken = Migration(
        version="900",
        name="broken",
        path=Path("900_broken.sql"),
        sql="CREATE TABLE tx_probe (id INTEGER);\nSELECT 1/0;\n",
        checksum="broken",
    )

    with pytest.raises(MigrationError):
        apply_pending(pg_engine, [broken])

    with pg_engine.connect() as connection:
        exists = connection.execute(
            text("SELECT to_regclass('tx_probe')")
        ).scalar()
    assert exists is None


def _direct_connection():
    """A genuinely independent session, never taken from the engine pool."""
    if not _TEST_URL or not _TEST_SCHEMA:
        raise RuntimeError("The isolated PostgreSQL schema fixture is not active.")
    driver_url = make_url(_TEST_URL).set(drivername="postgresql").render_as_string(hide_password=False)
    connection = psycopg2.connect(driver_url)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(f'SET search_path TO "{_TEST_SCHEMA}"')
    return connection


def _probe_lock() -> bool:
    connection = _direct_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
            acquired = bool(cursor.fetchone()[0])
            if acquired:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))
        return acquired
    finally:
        connection.close()


def _wait_until_free(deadline_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if _probe_lock():
            return True
        time.sleep(0.05)
    return False


def _advisory_lock_count(engine) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                "AND classid = :classid AND objid = :objid"
            ),
            {
                "classid": (MIGRATION_LOCK_KEY >> 32) & 0xFFFFFFFF,
                "objid": MIGRATION_LOCK_KEY & 0xFFFFFFFF,
            },
        ).scalar()


def test_advisory_lock_is_acquired_then_released(pg_engine):
    assert _probe_lock() is True

    with migration_lock(pg_engine):
        assert _probe_lock() is False
        assert _advisory_lock_count(pg_engine) == 1

    assert _probe_lock() is True
    assert _advisory_lock_count(pg_engine) == 0


def test_second_process_is_rejected_while_lock_is_held(pg_engine):
    holder = _direct_connection()
    try:
        with holder.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        with pytest.raises(MigrationError) as excinfo:
            with migration_lock(pg_engine):
                pass
    finally:
        holder.close()

    assert "advisory lock" in str(excinfo.value)


def test_lock_releases_after_successful_run(pg_engine):
    _reset_with_baseline(pg_engine)

    applied = apply_pending(pg_engine, discover_migrations())

    assert applied == ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010"]
    assert _probe_lock() is True
    assert _advisory_lock_count(pg_engine) == 0


def test_lock_releases_after_a_failed_run(pg_engine):
    _reset_with_baseline(pg_engine)
    broken = Migration(
        version="902",
        name="broken",
        path=Path("902_broken.sql"),
        sql="CREATE TABLE tx_probe_fail (id INTEGER);\nSELECT 1/0;\n",
        checksum="broken",
    )

    with pytest.raises(MigrationError):
        apply_pending(pg_engine, [broken])

    assert _probe_lock() is True
    assert _advisory_lock_count(pg_engine) == 0
    with pg_engine.connect() as connection:
        recorded = connection.execute(
            text(f"SELECT count(*) FROM {HISTORY_TABLE} WHERE version = '902'")
        ).scalar()
    assert recorded == 0


def test_session_termination_releases_the_lock(pg_engine):
    holder = _direct_connection()
    with holder.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
    assert _probe_lock() is False

    holder.close()

    assert _wait_until_free()


def test_lock_does_not_leak_into_pooled_connections(pg_engine):
    _reset_with_baseline(pg_engine)
    migrations = discover_migrations()

    for _ in range(3):
        with migration_lock(pg_engine):
            assert _advisory_lock_count(pg_engine) == 1
        assert _advisory_lock_count(pg_engine) == 0

    assert apply_pending(pg_engine, migrations) == ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010"]
    assert _probe_lock() is True
    assert _advisory_lock_count(pg_engine) == 0


def test_self_managed_failure_removes_the_intent_marker(pg_engine):
    _reset_with_baseline(pg_engine)
    broken = Migration(
        version="903",
        name="broken_managed",
        path=Path("903_broken_managed.sql"),
        sql=(
            "BEGIN;\n"
            "CREATE TABLE tx_probe_managed (id INTEGER);\n"
            "SELECT 1/0;\n"
            "COMMIT;\n"
        ),
        checksum="broken",
    )

    with pytest.raises(MigrationError):
        apply_pending(pg_engine, [broken])

    with pg_engine.connect() as connection:
        rows = connection.execute(
            text(f"SELECT version, method FROM {HISTORY_TABLE} WHERE version = '903'")
        ).fetchall()
        exists = connection.execute(
            text("SELECT to_regclass('tx_probe_managed')")
        ).scalar()
    assert rows == []
    assert exists is None
    assert _advisory_lock_count(pg_engine) == 0


def test_crash_window_blocks_execution_until_reconciled(pg_engine):
    _reset_with_baseline(pg_engine)
    migrations = discover_migrations()
    with pg_engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO {HISTORY_TABLE} (version, name, checksum, method) "
                "VALUES ('003', 'whatsapp_link_tokens', 'stale', 'applying')"
            )
        )

    with pytest.raises(MigrationError) as excinfo:
        apply_pending(pg_engine, migrations)

    assert "Incomplete migration state" in str(excinfo.value)
    issues = diagnose(pg_engine, migrations)
    assert any(
        issue.code == "incomplete_application" and issue.version == "003" for issue in issues
    )
    assert _advisory_lock_count(pg_engine) == 0


def test_postgres_adopt_rejects_missing_foreign_key(pg_engine):
    _reset_to_current_models(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("ALTER TABLE complaints DROP CONSTRAINT IF EXISTS complaints_whatsapp_citizen_id_fkey"))
        # Drop constraint by query if name differs
        conn.execute(text("""
            DO $$
            DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT constraint_name FROM information_schema.table_constraints
                          WHERE table_name = 'complaints' AND constraint_type = 'FOREIGN KEY') LOOP
                    EXECUTE 'ALTER TABLE complaints DROP CONSTRAINT ' || quote_ident(r.constraint_name);
                END LOOP;
            END $$;
        """))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(pg_engine, discover_migrations(), through_version="001")
    assert "foreign key" in str(excinfo.value).lower()


def test_postgres_adopt_rejects_missing_index(pg_engine):
    _reset_to_current_models(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_complaints_tracking_secret"))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(pg_engine, discover_migrations(), through_version="002")
    assert "index on" in str(excinfo.value).lower()
    assert "tracking_secret" in str(excinfo.value)


def test_postgres_adopt_rejects_missing_observability_column(pg_engine):
    _reset_to_current_models(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("ALTER TABLE mobile_otp_tokens DROP COLUMN IF EXISTS delivery_status CASCADE"))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(pg_engine, discover_migrations(), through_version="005")
    assert "delivery_status" in str(excinfo.value)


def test_postgres_adopt_rejects_incorrect_nullable(pg_engine):
    _reset_to_current_models(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ALTER COLUMN email SET NOT NULL"))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(pg_engine, discover_migrations(), through_version="004")
    assert "nullability mismatch" in str(excinfo.value).lower()


def _replace_partial_index(pg_engine, index_name: str, table: str, column: str, predicate: str | None):
    with pg_engine.begin() as connection:
        connection.execute(text(f'DROP INDEX IF EXISTS "{index_name}"'))
        where = f" WHERE {predicate}" if predicate else ""
        connection.execute(
            text(
                f'CREATE UNIQUE INDEX "{index_name}" ON "{table}" ("{column}"){where}'
            )
        )


@pytest.mark.parametrize(
    ("index_name", "table", "column", "predicate"),
    [
        (
            "uq_whatsapp_citizens_user_id_notnull",
            "whatsapp_citizens",
            "user_id",
            None,
        ),
        ("uq_users_phone", "users", "phone", None),
    ],
)
def test_postgres_adoption_rejects_regular_unique_replacement(
    pg_engine, index_name, table, column, predicate
):
    _reset_to_current_models(pg_engine)
    _replace_partial_index(pg_engine, index_name, table, column, predicate)

    version = "003" if table == "whatsapp_citizens" else "004"
    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(pg_engine, discover_migrations(), through_version=version)

    assert index_name in str(excinfo.value)
    assert status(pg_engine)["applied"] == []


@pytest.mark.parametrize(
    ("index_name", "table", "column", "predicate", "wrong_predicate", "version"),
    [
        (
            "uq_whatsapp_citizens_user_id_notnull",
            "whatsapp_citizens",
            "user_id",
            "user_id IS NOT NULL",
            "user_id IS NOT NULL AND user_id > 0",
            "003",
        ),
        (
            "uq_users_phone",
            "users",
            "phone",
            "phone IS NOT NULL AND phone != ''",
            "phone IS NOT NULL",
            "004",
        ),
    ],
)
def test_postgres_adoption_rejects_incorrect_partial_predicate(
    pg_engine, index_name, table, column, predicate, wrong_predicate, version
):
    _reset_to_current_models(pg_engine)
    _replace_partial_index(pg_engine, index_name, table, column, wrong_predicate)

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(pg_engine, discover_migrations(), through_version=version)

    assert "predicate mismatch" in str(excinfo.value)
    assert status(pg_engine)["applied"] == []


def test_postgres_fresh_orm_schema_matches_migration_sentinels(pg_engine):
    _reset_to_current_models(pg_engine)

    migrations = discover_migrations()
    for version in ("001", "002", "003", "004", "005", "006", "007", "008", "009", "010"):
        assert _missing_objects(pg_engine, version) == []

    # The supported fresh setup is ORM create_all; verify the migration runner
    # accepts its complete 001-010 sentinel contract without applying DDL.
    assert adopt_existing(pg_engine, migrations, through_version="010") == [
        "000", "001", "002", "003", "004", "005", "006", "007", "008", "009", "010",
    ]
    assert status(pg_engine, migrations)["pending"] == []


def test_postgres_adopts_legacy_schema_with_migration_partial_indexes(pg_engine):
    _reset_to_current_models(pg_engine)
    # Recreate these indexes from the authoritative 003/004 migration clauses,
    # independent of the ORM-created index objects.
    with pg_engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_whatsapp_citizens_user_id_notnull"))
        connection.execute(text("DROP INDEX uq_users_phone"))
        connection.execute(text(
            "CREATE UNIQUE INDEX uq_whatsapp_citizens_user_id_notnull "
            "ON whatsapp_citizens (user_id) WHERE user_id IS NOT NULL"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX uq_users_phone ON users(phone) "
            "WHERE phone IS NOT NULL AND phone != ''"
        ))

    adopted = adopt_existing(pg_engine, discover_migrations(), through_version="006")
    assert adopted == ["000", "001", "002", "003", "004", "005", "006"]


def test_postgres_adoption_rejects_invalid_index(pg_engine):
    _reset_to_current_models(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_whatsapp_citizens_user_id_notnull"))
        user_id = connection.execute(
            text("INSERT INTO users (full_name, role) VALUES ('Index Probe', 'citizen') RETURNING id")
        ).scalar_one()
        connection.execute(
            text("INSERT INTO whatsapp_citizens (phone_number, user_id) VALUES "
                 "('15550000001', :user_id), ('15550000002', :user_id)"),
            {"user_id": user_id},
        )
    raw = pg_engine.raw_connection()
    try:
        raw.autocommit = True
        with raw.cursor() as cursor:
            with pytest.raises(psycopg2.Error):
                cursor.execute(
                    "CREATE UNIQUE INDEX CONCURRENTLY uq_whatsapp_citizens_user_id_notnull "
                    "ON whatsapp_citizens (user_id) WHERE user_id IS NOT NULL"
                )
    finally:
        raw.close()

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(pg_engine, discover_migrations(), through_version="003")
    assert "invalid or not ready" in str(excinfo.value)
    assert status(pg_engine)["applied"] == []


def test_postgres_catalog_preserves_key_order_and_excludes_included_columns(pg_engine):
    with pg_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS catalog_probe"))
        connection.execute(text("CREATE TABLE catalog_probe (first_key INTEGER, second_key INTEGER, payload TEXT)"))
        connection.execute(text(
            "CREATE INDEX ix_catalog_probe_order ON catalog_probe (second_key, first_key) INCLUDE (payload)"
        ))

    try:
        info = _inspect_index_definitions(pg_engine, "catalog_probe")["ix_catalog_probe_order"]
        assert info["columns"] == ["second_key", "first_key"]
        assert info["included_columns"] == ["payload"]
    finally:
        with pg_engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS catalog_probe"))


def test_postgres_expression_key_is_not_reported_as_a_plain_column(pg_engine):
    _reset_to_current_models(pg_engine)
    with pg_engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_users_phone"))
        connection.execute(text(
            "CREATE UNIQUE INDEX uq_users_phone ON users (lower(phone)) "
            "WHERE phone IS NOT NULL AND phone != ''"
        ))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(pg_engine, discover_migrations(), through_version="004")
    assert "columns mismatch" in str(excinfo.value)
    assert status(pg_engine)["applied"] == []


def test_postgres_index_in_an_unrelated_schema_cannot_satisfy_adoption(pg_engine):
    _reset_to_current_models(pg_engine)
    decoy_schema = isolated_schema_name("catalog_decoy")
    with pg_engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_users_phone"))
        connection.execute(text(f'CREATE SCHEMA "{decoy_schema}"'))
        connection.execute(text(f'CREATE TABLE "{decoy_schema}".users (phone VARCHAR(20))'))
        connection.execute(text(
            f'CREATE UNIQUE INDEX uq_users_phone ON "{decoy_schema}".users(phone) '
            "WHERE phone IS NOT NULL AND phone != ''"
        ))

    try:
        assert "uq_users_phone" not in _inspect_index_definitions(pg_engine, "users")
        with pytest.raises(PrerequisiteError):
            adopt_existing(pg_engine, discover_migrations(), through_version="004")
        assert status(pg_engine)["applied"] == []
    finally:
        with pg_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{decoy_schema}" CASCADE'))

