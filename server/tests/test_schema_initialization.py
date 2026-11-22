"""Startup schema policy: production is verification-only, never DDL."""
import sqlite3
import re

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

import server.models  # noqa: F401  # register every table on Base.metadata
from server.database import initialization
from server.database.db import Base
from server.database.initialization import (
    REQUIRED_TABLES,
    SchemaValidationError,
    initialize_database,
    schema_mutation_allowed,
    verify_required_schema,
)


@pytest.fixture
def fresh_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'schema.db').as_posix()}")
    try:
        yield engine
    finally:
        engine.dispose()


def _tables(engine):
    return set(inspect(engine).get_table_names())


def _sqlite_snapshot(engine):
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT type, name, sql FROM sqlite_master ORDER BY type, name")
        ).fetchall()
    return [tuple(row) for row in rows]


def test_production_startup_on_empty_database_fails_without_creating_anything(fresh_engine):
    with pytest.raises(SchemaValidationError) as excinfo:
        initialize_database(fresh_engine, "production")

    message = str(excinfo.value)
    assert "missing tables" in message
    assert "users" in message
    assert _sqlite_snapshot(fresh_engine) == []


def test_production_startup_is_read_only_when_schema_exists(fresh_engine):
    Base.metadata.create_all(bind=fresh_engine)
    before = _sqlite_snapshot(fresh_engine)

    initialize_database(fresh_engine, "production")

    assert _sqlite_snapshot(fresh_engine) == before
    assert "schema_migrations" not in _tables(fresh_engine)


def test_production_path_never_invokes_schema_mutation(monkeypatch, fresh_engine):
    Base.metadata.create_all(bind=fresh_engine)
    calls = []
    monkeypatch.setattr(initialization, "_create_base_schema", lambda engine: calls.append(engine))

    initialize_database(fresh_engine, "production")

    assert calls == []


def test_production_startup_reports_missing_user_columns(fresh_engine):
    if sqlite3.sqlite_version_info < (3, 35, 0):
        pytest.skip("ALTER TABLE ... DROP COLUMN requires SQLite 3.35+")
    Base.metadata.create_all(bind=fresh_engine)
    with fresh_engine.begin() as connection:
        connection.execute(text("ALTER TABLE users DROP COLUMN mfa_enrolled_at"))

    with pytest.raises(SchemaValidationError) as excinfo:
        initialize_database(fresh_engine, "production")

    assert "missing users columns" in str(excinfo.value)
    assert "mfa_enrolled_at" in str(excinfo.value)


def test_production_startup_requires_onboarding_expiry_columns(fresh_engine):
    Base.metadata.create_all(bind=fresh_engine)
    with fresh_engine.begin() as connection:
        connection.execute(text("ALTER TABLE users DROP COLUMN temporary_password_expires_at"))

    with pytest.raises(SchemaValidationError) as excinfo:
        initialize_database(fresh_engine, "production")

    assert "temporary_password_expires_at" in str(excinfo.value)
    assert _sqlite_snapshot(fresh_engine)


def test_production_startup_rejects_missing_otp_table(fresh_engine):
    Base.metadata.create_all(bind=fresh_engine)
    with fresh_engine.begin() as connection:
        connection.execute(text("DROP TABLE mobile_otp_tokens"))
    with pytest.raises(SchemaValidationError, match="mobile_otp_tokens"):
        initialize_database(fresh_engine, "production")


def test_production_startup_rejects_missing_otp_observability_column(fresh_engine):
    Base.metadata.create_all(bind=fresh_engine)
    with fresh_engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_mobile_otp_tokens_delivery_status"))
        connection.execute(text("ALTER TABLE mobile_otp_tokens DROP COLUMN delivery_status"))
    with pytest.raises(SchemaValidationError, match="delivery_status"):
        initialize_database(fresh_engine, "production")


def test_production_startup_rejects_missing_registration_table(fresh_engine):
    Base.metadata.create_all(bind=fresh_engine)
    with fresh_engine.begin() as connection:
        connection.execute(text("DROP TABLE whatsapp_registration_challenges"))
    with pytest.raises(SchemaValidationError, match="whatsapp_registration_challenges"):
        initialize_database(fresh_engine, "production")


def test_production_startup_rejects_missing_registration_column(fresh_engine):
    Base.metadata.create_all(bind=fresh_engine)
    with fresh_engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_whatsapp_reg_challenges_phone"))
        connection.execute(text("ALTER TABLE whatsapp_registration_challenges DROP COLUMN phone"))
    with pytest.raises(SchemaValidationError, match="phone"):
        initialize_database(fresh_engine, "production")


def test_production_startup_rejects_wrong_schema_type_and_nullability(fresh_engine):
    Base.metadata.create_all(bind=fresh_engine)
    with fresh_engine.begin() as connection:
        connection.execute(text("DROP TABLE whatsapp_registration_challenges"))
        connection.execute(text(
            "CREATE TABLE whatsapp_registration_challenges ("
            "id INTEGER PRIMARY KEY, phone INTEGER, otp_hash VARCHAR(64) NOT NULL, "
            "purpose VARCHAR(50) NOT NULL DEFAULT 'citizen_registration', "
            "attempts INTEGER NOT NULL, max_attempts INTEGER NOT NULL DEFAULT 5, "
            "status VARCHAR(30) NOT NULL DEFAULT 'PENDING', expires_at DATETIME NOT NULL, "
            "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        ))
    with pytest.raises(SchemaValidationError) as excinfo:
        initialize_database(fresh_engine, "production")
    message = str(excinfo.value)
    assert "phone type mismatch" in message
    assert "phone nullability mismatch" in message
    assert "attempts default mismatch" in message
    assert "secret_hash" in message
    assert "foreign key" in message


def test_production_startup_fails_closed_on_inspector_exception(monkeypatch, fresh_engine):
    def broken_inspect(_engine):
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(initialization, "inspect", broken_inspect)
    with pytest.raises(SchemaValidationError, match="inspection failed closed"):
        initialize_database(fresh_engine, "production")


@pytest.mark.parametrize("env", ["development", "dev", "local", "test", "testing", " TEST "])
def test_non_production_initialization_creates_schema(fresh_engine, env):
    initialize_database(fresh_engine, env)

    assert REQUIRED_TABLES <= _tables(fresh_engine)
    verify_required_schema(fresh_engine)


@pytest.mark.parametrize("env", ["production", "staging", "prod", "", None])
def test_unlisted_environments_are_verification_only(env):
    assert schema_mutation_allowed(env) is False


def test_initialize_database_rejects_wrong_environment_by_default(fresh_engine):
    with pytest.raises(SchemaValidationError):
        initialize_database(fresh_engine, "staging")

    assert _sqlite_snapshot(fresh_engine) == []


def test_development_initialization_still_creates_and_verifies_migration_schemas(fresh_engine):
    initialize_database(fresh_engine, "test")
    assert "mobile_otp_tokens" in _tables(fresh_engine)
    assert "whatsapp_registration_challenges" in _tables(fresh_engine)
    assert verify_required_schema(fresh_engine) is None


def _make_pre_011_database(engine, *, registry_exists: bool):
    """Build a disposable pre-011 schema while retaining populated user data."""
    from server.database.migrations_runner import HISTORY_TABLE
    from server.models.user import User

    Base.metadata.create_all(bind=engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        connection.exec_driver_sql("DROP TABLE users")
        if not registry_exists:
            connection.exec_driver_sql("DROP TABLE wards")
            connection.exec_driver_sql("DROP TABLE municipalities")
        connection.commit()

        old_user_sql = str(CreateTable(User.__table__).compile(dialect=sqlite.dialect()))
        old_user_sql = re.sub(r"^\s*(?:municipality_id|ward_id) INTEGER,?\s*$", "", old_user_sql, flags=re.MULTILINE)
        old_user_sql = re.sub(
            r"^\s*FOREIGN KEY\((?:municipality_id|ward_id)\).*?,?\s*$",
            "",
            old_user_sql,
            flags=re.MULTILINE,
        )
        # Removing lines can leave a comma immediately before the table close.
        old_user_sql = re.sub(r",\s*\)\s*$", "\n)", old_user_sql)
        connection.exec_driver_sql(old_user_sql)
        for index in User.__table__.indexes:
            if any(column.name in {"municipality_id", "ward_id"} for column in index.columns):
                continue
            connection.exec_driver_sql(
                str(CreateIndex(index).compile(dialect=sqlite.dialect()))
            )

        if registry_exists:
            municipality_id = connection.execute(
                text("SELECT id FROM municipalities WHERE code = 'DHULE'")
            ).scalar()
            if municipality_id is None:
                connection.execute(
                    text("INSERT INTO municipalities (code, name) VALUES ('DHULE', 'Dhule')")
                )
                municipality_id = connection.execute(
                    text("SELECT id FROM municipalities WHERE code = 'DHULE'")
                ).scalar()
            if not connection.execute(text("SELECT 1 FROM wards LIMIT 1")).first():
                connection.execute(
                    text("INSERT INTO wards (municipality_id, ward_number, display_name) "
                         "VALUES (:municipality_id, '1', 'Ward 1')"),
                    {"municipality_id": municipality_id},
                )

        connection.execute(
            text("INSERT INTO users (id, full_name, email, employee_id, login_id, "
                 "hashed_password, role, ward, phone, is_active, is_verified, "
                 "is_super_admin, must_change_password, mfa_secret_enc, mfa_enabled, "
                 "session_version, account_status) VALUES "
                 "(1, 'Local Super Admin', 'local-admin@example.test', 'SUP-LOCAL-001', "
                 "'SUP-LOCAL-001', 'preserved-password-hash', 'admin', 'Ward 1', "
                 "'9000000001', 1, 1, 1, 0, 'preserved-encrypted-mfa', 1, 17, 'active')")
        )
        connection.execute(
            text("INSERT INTO complaints (id, tracking_number, ward, location_address, "
                 "waste_type, status, citizen_id) VALUES "
                 "(5, 'TRACK-LEGACY-5', 'Ward 1', 'Legacy location', 'Mixed Waste', "
                 "'In Progress', 1)")
        )
        connection.execute(
            text("INSERT INTO tasks (id, complaint_id, driver_id, location_name, status) "
                 "VALUES (9, 5, 1, 'Legacy route', 'Pending Verification')")
        )
        connection.execute(
            text("INSERT INTO task_evidence (id, task_id, complaint_id, driver_id, "
                 "after_image_ref, status) VALUES "
                 "(11, 9, 5, 1, 'evidence/legacy.jpg', 'submitted')")
        )
        connection.execute(
            text("INSERT INTO security_audit_events (id, actor_id, target_user_id, "
                 "action, details) VALUES (13, 1, 1, 'legacy.test', 'preserve-event')")
        )
        connection.commit()


@pytest.mark.parametrize("registry_exists", [False, True], ids=["pre-011", "partial-011"])
def test_existing_disposable_database_migrates_before_ward_orm_queries(
    fresh_engine, registry_exists
):
    from server.database.migrations_runner import history_rows
    from server.models.user import User
    from sqlalchemy.orm import Session

    _make_pre_011_database(fresh_engine, registry_exists=registry_exists)
    assert "municipality_id" not in {
        column["name"] for column in inspect(fresh_engine).get_columns("users")
    }
    assert "ward_id" not in {
        column["name"] for column in inspect(fresh_engine).get_columns("users")
    }
    assert "schema_migrations" not in _tables(fresh_engine)

    initialize_database(fresh_engine, "test")

    with Session(fresh_engine) as session:
        account = session.get(User, 1)
        assert account.login_id == "SUP-LOCAL-001"
        assert account.hashed_password == "preserved-password-hash"
        assert account.mfa_secret_enc == "preserved-encrypted-mfa"
        assert account.mfa_enabled is True
        assert account.session_version == 17
        assert account.ward_id is not None
        assert account.municipality_id is not None
    with fresh_engine.connect() as connection:
        assert connection.execute(
            text("SELECT tracking_number, status FROM complaints WHERE id = 5")
        ).one() == ("TRACK-LEGACY-5", "In Progress")
        assert connection.execute(
            text("SELECT location_name, status FROM tasks WHERE id = 9")
        ).one() == ("Legacy route", "Pending Verification")
        assert connection.execute(
            text("SELECT after_image_ref, status FROM task_evidence WHERE id = 11")
        ).one() == ("evidence/legacy.jpg", "submitted")
        assert connection.execute(
            text("SELECT details FROM security_audit_events WHERE id = 13")
        ).scalar() == "preserve-event"

    history = history_rows(fresh_engine)
    assert history["009"]["method"] == "applied"
    assert history["010"]["method"] == "applied"
    assert history["011"]["method"] == "applied"
    verify_required_schema(fresh_engine)

    # A second startup is a no-op and does not duplicate the seeded registry.
    initialize_database(fresh_engine, "test")
    with fresh_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM wards")).scalar() == 19


def test_fresh_disposable_database_records_all_migrations_and_seeds_registry(fresh_engine):
    from server.database.migrations_runner import discover_migrations, history_rows

    initialize_database(fresh_engine, "test")

    expected_versions = {migration.version for migration in discover_migrations()}
    assert expected_versions <= set(history_rows(fresh_engine))
    assert verify_required_schema(fresh_engine) is None
    with fresh_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM wards")).scalar() == 19


def _prepare_production_lifespan(monkeypatch, engine):
    import server.main as main
    import server.database.db as db_module

    class DummySession:
        def close(self):
            pass

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", DummySession)
    monkeypatch.setattr(main, "get_environment", lambda: "production")
    monkeypatch.setattr(main.config, "reload", lambda: None)
    monkeypatch.setattr(main.config, "validate_production_settings", lambda: None)
    monkeypatch.setattr(main.AuthService, "should_seed_demo_users", staticmethod(lambda: False))
    monkeypatch.setattr(main, "resynchronize_sequences", lambda _db, _env: None)
    monkeypatch.setattr(db_module, "validate_database_connection", lambda _engine: None)
    return main


def _run_synchronous_lifespan_awaitable(awaitable):
    """Advance the startup coroutine without opening Windows asyncio sockets."""
    try:
        awaitable.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("Application startup unexpectedly suspended on asynchronous I/O.")


def test_production_lifespan_refuses_incompatible_schema(monkeypatch, fresh_engine):
    main = _prepare_production_lifespan(monkeypatch, fresh_engine)
    context = main.lifespan(main.app)
    with pytest.raises(SchemaValidationError):
        _run_synchronous_lifespan_awaitable(context.__aenter__())


def test_production_lifespan_allows_compatible_schema(monkeypatch, fresh_engine):
    Base.metadata.create_all(bind=fresh_engine)
    main = _prepare_production_lifespan(monkeypatch, fresh_engine)
    context = main.lifespan(main.app)
    _run_synchronous_lifespan_awaitable(context.__aenter__())
    _run_synchronous_lifespan_awaitable(context.__aexit__(None, None, None))
