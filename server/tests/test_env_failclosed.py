"""
Phase 1G & 1G.2: Complete Fail-Closed Environment, Conflict Validation & Startup Isolation Tests.

Verifies that:
  1. Every database initialization entry point fails closed.
  2. Conflicting ENV and ENVIRONMENT values are deterministically rejected.
  3. Alternate database initialization scripts fail closed on unauthorized environments
     and execute zero SQL statements.
  4. Importing server.main, server.database.db, and initialization modules performs zero
     connections and zero SQL operations.
  5. Database initialization occurs strictly during FastAPI lifespan startup.
  6. Demo seeding and sequence resynchronization require explicit non-production configuration.

All tests use isolated in-memory/tmp SQLite engines, subprocess execution, and mocks.
No test connects to Neon, Render, or any external database.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect, text

import server.models  # noqa: F401 — register all ORM tables on Base.metadata
from server.database.db import Base
from server.database.initialization import (
    MUTATION_ALLOWED_ENVIRONMENTS,
    SchemaValidationError,
    initialize_database,
    resynchronize_sequences,
    schema_mutation_allowed,
)
from server.utils.config import (
    _MUTATION_ALLOWED_ENVS,
    _RECOGNIZED_ENVS,
    config,
    get_environment,
    is_local_or_test_environment,
    is_production_environment,
    normalize_environment,
)


def test_production_runtime_configuration_does_not_require_employee_allowlist(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "production-config-test-secret-key-0123456789")
    monkeypatch.setenv("CORS_ORIGINS", "https://portal.example.test")
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv("MEDIA_STORAGE_BACKEND", "local")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "mock")
    monkeypatch.setenv("OTP_DELIVERY_PROVIDER", "development")
    monkeypatch.delenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", raising=False)

    config.validate_production_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_engine(tmp_path=None):
    """Return a fresh SQLite engine on a temp path, or in-memory if no tmp_path."""
    if tmp_path is None:
        return create_engine("sqlite:///:memory:")
    return create_engine(f"sqlite:///{(tmp_path / 'failclosed.db').as_posix()}")


def _tables(engine):
    return set(inspect(engine).get_table_names())


def _sqlite_snapshot(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT type, name, sql FROM sqlite_master ORDER BY type, name")
        ).fetchall()
    return [tuple(r) for r in rows]


@contextlib.contextmanager
def _env_set(**env_vars):
    """Context manager that temporarily overrides os.environ entries."""
    old = {k: os.environ.get(k) for k in env_vars}
    for k, v in env_vars.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# 1. get_environment() fail-closed & conflict validation policy
# ---------------------------------------------------------------------------

class TestGetEnvironmentFailClosed:
    def test_unset_env_raises(self):
        with _env_set(ENV=None, ENVIRONMENT=None):
            with pytest.raises(RuntimeError, match="Neither ENV nor ENVIRONMENT is set"):
                get_environment()

    def test_empty_string_env_raises(self):
        with _env_set(ENV="", ENVIRONMENT=None):
            with pytest.raises(RuntimeError, match="Neither ENV nor ENVIRONMENT is set"):
                get_environment()

    def test_unknown_env_raises(self):
        with _env_set(ENV="sandbox", ENVIRONMENT=None):
            with pytest.raises(RuntimeError, match="not a recognized environment"):
                get_environment()

    def test_unknown_env_is_not_treated_as_development(self):
        """An unknown env value must NOT return any mutation-allowed environment."""
        with _env_set(ENV="sandbox", ENVIRONMENT=None):
            with pytest.raises(RuntimeError):
                env = get_environment()
                assert env not in _MUTATION_ALLOWED_ENVS

    @pytest.mark.parametrize("env", ["development", "dev", "local", "test", "testing"])
    def test_valid_dev_test_envs_accepted(self, env):
        with _env_set(ENV=env, ENVIRONMENT=None):
            result = get_environment()
            assert result == env

    @pytest.mark.parametrize("env", ["staging", "production"])
    def test_valid_prod_staging_envs_accepted(self, env):
        with _env_set(ENV=env, ENVIRONMENT=None):
            result = get_environment()
            assert result == env

    def test_whitespace_stripped(self):
        with _env_set(ENV="  development  ", ENVIRONMENT=None):
            result = get_environment()
            assert result == "development"

    def test_case_insensitive(self):
        with _env_set(ENV="PRODUCTION", ENVIRONMENT=None):
            result = get_environment()
            assert result == "production"


class TestEnvironmentConflictValidation:
    """Phase 1G.2: Deterministic conflict validation between ENV and ENVIRONMENT."""

    def test_env_development_environment_production_raises_conflict(self):
        with _env_set(ENV="development", ENVIRONMENT="production"):
            with pytest.raises(RuntimeError, match="CONFIGURATION CONFLICT.*disagree"):
                get_environment()

    def test_env_production_environment_development_raises_conflict(self):
        with _env_set(ENV="production", ENVIRONMENT="development"):
            with pytest.raises(RuntimeError, match="CONFIGURATION CONFLICT.*disagree"):
                get_environment()

    def test_env_staging_environment_development_raises_conflict(self):
        with _env_set(ENV="staging", ENVIRONMENT="development"):
            with pytest.raises(RuntimeError, match="CONFIGURATION CONFLICT.*disagree"):
                get_environment()

    def test_env_development_environment_development_succeeds(self):
        with _env_set(ENV="development", ENVIRONMENT="DEVELOPMENT"):
            assert get_environment() == "development"

    def test_env_unset_environment_production_succeeds(self):
        with _env_set(ENV=None, ENVIRONMENT="production"):
            assert get_environment() == "production"

    def test_env_production_environment_unset_succeeds(self):
        with _env_set(ENV="production", ENVIRONMENT=None):
            assert get_environment() == "production"

    def test_both_unset_raises_configuration_error(self):
        with _env_set(ENV=None, ENVIRONMENT=None):
            with pytest.raises(RuntimeError, match="Neither ENV nor ENVIRONMENT is set"):
                get_environment()

    def test_both_empty_raises_configuration_error(self):
        with _env_set(ENV="", ENVIRONMENT=""):
            with pytest.raises(RuntimeError, match="Neither ENV nor ENVIRONMENT is set"):
                get_environment()

    @pytest.mark.parametrize("invalid_env", ["sandbox", "unknown", "custom", "prod_backup"])
    def test_unknown_in_either_variable_fails_closed(self, invalid_env):
        with _env_set(ENV=invalid_env, ENVIRONMENT=None):
            with pytest.raises(RuntimeError, match="not a recognized environment"):
                get_environment()
        with _env_set(ENV=None, ENVIRONMENT=invalid_env):
            with pytest.raises(RuntimeError, match="not a recognized environment"):
                get_environment()

    def test_conflicting_configuration_cannot_activate_schema_mutation(self):
        """Conflicting ENV and ENVIRONMENT must not allow schema mutation."""
        with _env_set(ENV="development", ENVIRONMENT="production"):
            assert is_local_or_test_environment() is False
            assert is_production_environment() is False
            from server.services.auth_service import AuthService
            assert AuthService.should_seed_demo_users() is False


# ---------------------------------------------------------------------------
# 2. schema_mutation_allowed — unknown/unset/conflicting ENV is NOT mutation-allowed
# ---------------------------------------------------------------------------

class TestSchemaMutationAllowed:
    @pytest.mark.parametrize("env", ["", None, "sandbox", "unknown", "staging", "production"])
    def test_unknown_or_non_dev_envs_not_allowed(self, env):
        assert schema_mutation_allowed(env) is False

    @pytest.mark.parametrize("env", list(MUTATION_ALLOWED_ENVIRONMENTS))
    def test_explicit_dev_test_envs_are_allowed(self, env):
        assert schema_mutation_allowed(env) is True


# ---------------------------------------------------------------------------
# 3. initialize_database — fail-closed on unknown / unset ENV
# ---------------------------------------------------------------------------

class TestInitializeDatabaseFailClosed:
    def test_unset_env_does_not_mutate_schema(self, tmp_path):
        """ENV unset → verification-only → raises on empty DB, no mutation."""
        engine = _fresh_engine(tmp_path)
        try:
            with pytest.raises(SchemaValidationError):
                initialize_database(engine, "")
            assert _sqlite_snapshot(engine) == []
        finally:
            engine.dispose()

    def test_unknown_env_does_not_mutate_schema(self, tmp_path):
        """ENV=sandbox → verification-only → raises, no mutation."""
        engine = _fresh_engine(tmp_path)
        try:
            with pytest.raises(SchemaValidationError):
                initialize_database(engine, "sandbox")
            assert _sqlite_snapshot(engine) == []
        finally:
            engine.dispose()

    def test_staging_does_not_mutate_schema(self, tmp_path):
        engine = _fresh_engine(tmp_path)
        try:
            with pytest.raises(SchemaValidationError):
                initialize_database(engine, "staging")
            assert _sqlite_snapshot(engine) == []
        finally:
            engine.dispose()

    def test_production_does_not_mutate_schema(self, tmp_path):
        engine = _fresh_engine(tmp_path)
        try:
            with pytest.raises(SchemaValidationError):
                initialize_database(engine, "production")
            assert _sqlite_snapshot(engine) == []
        finally:
            engine.dispose()

    def test_production_with_full_schema_is_read_only(self, tmp_path):
        """Production startup on a fully-initialized schema must not alter it."""
        engine = _fresh_engine(tmp_path)
        try:
            Base.metadata.create_all(bind=engine)
            before = _sqlite_snapshot(engine)
            initialize_database(engine, "production")
            assert _sqlite_snapshot(engine) == before
        finally:
            engine.dispose()

    def test_staging_with_full_schema_is_read_only(self, tmp_path):
        engine = _fresh_engine(tmp_path)
        try:
            Base.metadata.create_all(bind=engine)
            before = _sqlite_snapshot(engine)
            initialize_database(engine, "staging")
            assert _sqlite_snapshot(engine) == before
        finally:
            engine.dispose()

    def test_development_creates_schema(self, tmp_path):
        engine = _fresh_engine(tmp_path)
        try:
            initialize_database(engine, "development")
            assert "users" in _tables(engine)
            assert "complaints" in _tables(engine)
        finally:
            engine.dispose()

    def test_test_env_creates_schema(self, tmp_path):
        engine = _fresh_engine(tmp_path)
        try:
            initialize_database(engine, "test")
            assert "users" in _tables(engine)
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 4. get_database_url — fail-closed on unset/unknown ENV
# ---------------------------------------------------------------------------

class TestGetDatabaseUrlFailClosed:
    def test_unset_env_no_database_url_fails(self):
        """ENV unset + no DATABASE_URL → RuntimeError (not silent SQLite)."""
        with patch.dict(os.environ, {}, clear=True):
            from server.database.db import get_database_url
            with pytest.raises(RuntimeError):
                get_database_url()

    def test_unknown_env_no_database_url_fails(self):
        """ENV=sandbox + no DATABASE_URL → RuntimeError."""
        with patch.dict(os.environ, {"ENV": "sandbox"}, clear=True):
            from server.database.db import get_database_url
            with pytest.raises(RuntimeError, match="not a recognized environment"):
                get_database_url()

    def test_production_no_database_url_fails(self):
        """ENV=production + no DATABASE_URL → RuntimeError."""
        with patch.dict(os.environ, {"ENV": "production"}, clear=True):
            from server.database.db import get_database_url
            with pytest.raises(RuntimeError, match="DATABASE_URL is required in production"):
                get_database_url()

    def test_staging_no_database_url_fails(self):
        """ENV=staging + no DATABASE_URL → RuntimeError."""
        with patch.dict(os.environ, {"ENV": "staging"}, clear=True):
            from server.database.db import get_database_url
            with pytest.raises(RuntimeError, match="DATABASE_URL is required in staging"):
                get_database_url()

    def test_development_no_database_url_uses_sqlite(self):
        """ENV=development + no DATABASE_URL → SQLite fallback is allowed."""
        with patch.dict(os.environ, {"ENV": "development"}, clear=True):
            from server.database.db import get_database_url
            url = get_database_url()
            assert url.startswith("sqlite://")

    def test_production_sqlite_database_url_fails(self):
        """ENV=production + SQLite DATABASE_URL → RuntimeError."""
        with patch.dict(os.environ, {"ENV": "production", "DATABASE_URL": "sqlite:///./ecopulse.db"}, clear=True):
            from server.database.db import get_database_url
            with pytest.raises(RuntimeError, match="SQLite is not allowed in production"):
                get_database_url()

    def test_unknown_env_with_postgresql_url_no_driver_fails(self):
        """ENV=sandbox + PostgreSQL URL + no psycopg2 → fail closed (not SQLite fallback)."""
        with patch.dict(os.environ, {"ENV": "sandbox", "DATABASE_URL": "postgresql://host/db"}, clear=True):
            from server.database.db import get_database_url
            with pytest.raises(RuntimeError, match="not a recognized environment"):
                get_database_url()


# ---------------------------------------------------------------------------
# 5. Demo-account seeding safety
# ---------------------------------------------------------------------------

class TestDemoAccountSeedingSafety:
    @pytest.mark.parametrize("env", ["production", "staging", "", None])
    def test_should_seed_returns_false_for_non_dev_envs(self, env):
        from server.services.auth_service import AuthService
        with _env_set(ENV=env, ENVIRONMENT=None):
            assert AuthService.should_seed_demo_users() is False

    def test_should_seed_returns_false_for_unknown_env(self):
        from server.services.auth_service import AuthService
        with _env_set(ENV="sandbox", ENVIRONMENT=None):
            assert AuthService.should_seed_demo_users() is False

    def test_should_seed_returns_false_when_env_unset(self):
        from server.services.auth_service import AuthService
        with _env_set(ENV=None, ENVIRONMENT=None):
            assert AuthService.should_seed_demo_users() is False

    def test_should_seed_returns_true_only_for_explicit_development(self):
        from server.services.auth_service import AuthService
        with _env_set(ENV="development", ENVIRONMENT=None):
            assert AuthService.should_seed_demo_users() is True

    def test_should_seed_returns_false_for_dev_alias(self):
        """ENV=dev (alias) must NOT seed demo accounts — only 'development' qualifies."""
        from server.services.auth_service import AuthService
        with _env_set(ENV="dev", ENVIRONMENT=None):
            assert AuthService.should_seed_demo_users() is False

    def test_seed_demo_users_is_noop_for_production(self, tmp_path):
        from server.services.auth_service import AuthService
        engine = _fresh_engine(tmp_path)
        try:
            Base.metadata.create_all(bind=engine)
            from sqlalchemy.orm import sessionmaker
            Session = sessionmaker(bind=engine)
            db = Session()
            try:
                with _env_set(ENV="production", ENVIRONMENT=None):
                    AuthService.seed_demo_users(db)
                from server.models.user import User
                count = db.query(User).count()
                assert count == 0, f"Expected 0 users, found {count}"
            finally:
                db.close()
        finally:
            engine.dispose()

    def test_seed_demo_users_is_noop_for_unset_env(self, tmp_path):
        from server.services.auth_service import AuthService
        engine = _fresh_engine(tmp_path)
        try:
            Base.metadata.create_all(bind=engine)
            from sqlalchemy.orm import sessionmaker
            Session = sessionmaker(bind=engine)
            db = Session()
            try:
                with _env_set(ENV=None, ENVIRONMENT=None):
                    AuthService.seed_demo_users(db)
                from server.models.user import User
                count = db.query(User).count()
                assert count == 0, f"Expected 0 users, found {count}"
            finally:
                db.close()
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 6. Sequence resynchronization safety
# ---------------------------------------------------------------------------

class TestSequenceResyncSafety:
    @pytest.mark.parametrize("env", ["production", "staging", "", None])
    def test_non_mutation_envs_never_touch_sequences(self, env):
        from server.database.initialization import resynchronize_sequences

        class _RecordingSession:
            def __init__(self):
                self.calls = []
                self.commits = 0
            def execute(self, stmt, params=None):
                self.calls.append(str(stmt))
                return MagicMock(scalar=lambda: None)
            def commit(self):
                self.commits += 1

        session = _RecordingSession()
        resynchronize_sequences(session, env)
        assert session.calls == [], f"Expected no DB calls for ENV={env!r}, got {session.calls}"
        assert session.commits == 0

    def test_unknown_env_never_touches_sequences(self):
        from server.database.initialization import resynchronize_sequences

        class _RecordingSession:
            def __init__(self):
                self.calls = []
            def execute(self, stmt, params=None):
                self.calls.append(str(stmt))
                return MagicMock(scalar=lambda: None)
            def commit(self):
                pass

        session = _RecordingSession()
        resynchronize_sequences(session, "sandbox")
        assert session.calls == []


# ---------------------------------------------------------------------------
# 7. Alternate database initialization scripts safety (Phase 1G.2)
# ---------------------------------------------------------------------------

class TestAlternateInitializationScripts:
    """Verifies server/init_db.py and server/database/init_db.py fail closed."""

    @pytest.mark.parametrize("unauthorized_env", [None, "", "unknown", "staging", "production"])
    def test_server_init_db_fails_closed_without_touching_db(self, unauthorized_env):
        code = f"""
import os, sys
env_val = {unauthorized_env!r}
if env_val is not None:
    os.environ['ENV'] = env_val
else:
    os.environ.pop('ENV', None)
os.environ.pop('ENVIRONMENT', None)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

executed_sqls = []
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, 'before_cursor_execute')
def before_cursor(conn, cursor, statement, parameters, context, executemany):
    executed_sqls.append(statement)

from server.init_db import initialize_database
try:
    initialize_database()
    print('FAIL: did not raise')
    sys.exit(1)
except RuntimeError as exc:
    assert len(executed_sqls) == 0, f'Expected 0 SQL statements, executed: {{executed_sqls}}'
    print('PASS: raised RuntimeError without SQL')
    sys.exit(0)
"""
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert p.returncode == 0, f"Failed for ENV={unauthorized_env!r}: stdout={p.stdout}, stderr={p.stderr}"
        assert "PASS: raised RuntimeError without SQL" in p.stdout

    @pytest.mark.parametrize("unauthorized_env", [None, "", "unknown", "staging", "production"])
    def test_server_database_init_db_fails_closed_without_touching_db(self, unauthorized_env):
        code = f"""
import os, sys
env_val = {unauthorized_env!r}
if env_val is not None:
    os.environ['ENV'] = env_val
else:
    os.environ.pop('ENV', None)
os.environ.pop('ENVIRONMENT', None)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

executed_sqls = []
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, 'before_cursor_execute')
def before_cursor(conn, cursor, statement, parameters, context, executemany):
    executed_sqls.append(statement)

from server.database.init_db import init_and_seed_db
try:
    init_and_seed_db()
    print('FAIL: did not raise')
    sys.exit(1)
except RuntimeError as exc:
    assert len(executed_sqls) == 0, f'Expected 0 SQL statements, executed: {{executed_sqls}}'
    print('PASS: raised RuntimeError without SQL')
    sys.exit(0)
"""
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert p.returncode == 0, f"Failed for ENV={unauthorized_env!r}: stdout={p.stdout}, stderr={p.stderr}"
        assert "PASS: raised RuntimeError without SQL" in p.stdout

    @pytest.mark.parametrize("authorized_env", ["development", "test"])
    def test_server_init_db_succeeds_in_dev_test(self, authorized_env, tmp_path):
        db_path = (tmp_path / f"init_{authorized_env}.db").as_posix()
        code = f"""
import os, sys
os.environ['ENV'] = {authorized_env!r}
os.environ.pop('ENVIRONMENT', None)
os.environ['DATABASE_URL'] = 'sqlite:///{db_path}'

from server.init_db import initialize_database
initialize_database()
from sqlalchemy import create_engine, inspect
engine = create_engine('sqlite:///{db_path}')
tables = inspect(engine).get_table_names()
assert 'users' in tables, f'users table missing: {{tables}}'
print('PASS: initialized successfully')
sys.exit(0)
"""
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert p.returncode == 0, f"Failed for authorized ENV={authorized_env!r}: stdout={p.stdout}, stderr={p.stderr}"
        assert "PASS: initialized successfully" in p.stdout


# ---------------------------------------------------------------------------
# 8. Subprocess import isolation tests (Phase 1G.2)
# ---------------------------------------------------------------------------

class TestSubprocessImportIsolation:
    """Verifies that importing modules executes zero SQL, establishes zero connections, and creates no DDL."""

    def test_import_config_performs_zero_sql(self):
        code = """
import sys
executed_sqls = []
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, 'before_cursor_execute')
def before_cursor(conn, cursor, statement, parameters, context, executemany):
    executed_sqls.append(statement)

import server.utils.config
assert len(executed_sqls) == 0
print('PASS')
"""
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert p.returncode == 0, f"stdout={p.stdout}, stderr={p.stderr}"
        assert "PASS" in p.stdout

    def test_import_initialization_performs_zero_sql(self):
        code = """
import sys
executed_sqls = []
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, 'before_cursor_execute')
def before_cursor(conn, cursor, statement, parameters, context, executemany):
    executed_sqls.append(statement)

import server.database.initialization
assert len(executed_sqls) == 0
print('PASS')
"""
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert p.returncode == 0, f"stdout={p.stdout}, stderr={p.stderr}"
        assert "PASS" in p.stdout

    def test_import_db_performs_zero_connections_and_zero_sql(self):
        code = """
import os, sys
os.environ['ENV'] = 'test'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

executed_sqls = []
connections = []
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, 'before_cursor_execute')
def before_cursor(conn, cursor, statement, parameters, context, executemany):
    executed_sqls.append(statement)

@event.listens_for(Engine, 'connect')
def on_connect(dbapi_connection, connection_record):
    connections.append(dbapi_connection)

import server.database.db
assert len(executed_sqls) == 0, f'Expected 0 SQL, got: {executed_sqls}'
assert len(connections) == 0, f'Expected 0 connections, got: {connections}'
print('PASS')
"""
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert p.returncode == 0, f"stdout={p.stdout}, stderr={p.stderr}"
        assert "PASS" in p.stdout

    def test_import_main_performs_zero_connections_and_zero_sql(self):
        code = """
import os, sys
os.environ['ENV'] = 'test'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

executed_sqls = []
connections = []
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, 'before_cursor_execute')
def before_cursor(conn, cursor, statement, parameters, context, executemany):
    executed_sqls.append(statement)

@event.listens_for(Engine, 'connect')
def on_connect(dbapi_connection, connection_record):
    connections.append(dbapi_connection)

import server.main
assert len(executed_sqls) == 0, f'Expected 0 SQL, got: {executed_sqls}'
assert len(connections) == 0, f'Expected 0 connections, got: {connections}'
print('PASS')
"""
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert p.returncode == 0, f"stdout={p.stdout}, stderr={p.stderr}"
        assert "PASS" in p.stdout

    def test_import_main_in_development_does_not_execute_ddl(self):
        code = """
import os, sys
os.environ['ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

executed_sqls = []
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, 'before_cursor_execute')
def before_cursor(conn, cursor, statement, parameters, context, executemany):
    executed_sqls.append(statement)

import server.main
ddls = [s for s in executed_sqls if any(k in s.upper() for k in ['CREATE', 'ALTER', 'DROP'])]
assert len(ddls) == 0, f'Expected 0 DDL, got: {ddls}'
assert len(executed_sqls) == 0, f'Expected 0 SQL, got: {executed_sqls}'
print('PASS')
"""
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert p.returncode == 0, f"stdout={p.stdout}, stderr={p.stderr}"
        assert "PASS" in p.stdout

    def test_import_main_in_production_does_not_execute_select1_or_reflection(self):
        code = """
import os, sys
os.environ['ENV'] = 'production'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'a'*32
from cryptography.fernet import Fernet
os.environ['MFA_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
os.environ['MUNICIPAL_EMPLOYEE_ALLOWLIST'] = 'EMP-01'
os.environ['WHATSAPP_PROVIDER'] = 'mock'
os.environ['OTP_DELIVERY_PROVIDER'] = 'development'
os.environ['CORS_ORIGINS'] = 'https://ecopulse-ai-frontend.onrender.com'

executed_sqls = []
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, 'before_cursor_execute')
def before_cursor(conn, cursor, statement, parameters, context, executemany):
    executed_sqls.append(statement)

try:
    import server.main
    assert False, 'Should fail because SQLite is forbidden in production'
except RuntimeError as exc:
    assert 'SQLite is not allowed in production' in str(exc)
    assert len(executed_sqls) == 0, f'Expected 0 SQL queries, got: {executed_sqls}'
    print('PASS')
"""
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert p.returncode == 0, f"stdout={p.stdout}, stderr={p.stderr}"
        assert "PASS" in p.stdout

    def test_invalid_env_fails_without_touching_database(self):
        code = """
import os, sys
os.environ['ENV'] = 'sandbox'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

executed_sqls = []
connections = []
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, 'before_cursor_execute')
def before_cursor(conn, cursor, statement, parameters, context, executemany):
    executed_sqls.append(statement)

@event.listens_for(Engine, 'connect')
def on_connect(dbapi_connection, connection_record):
    connections.append(dbapi_connection)

try:
    import server.main
    assert False, 'Should fail closed on unknown ENV'
except RuntimeError as exc:
    assert 'not a recognized environment' in str(exc)
    assert len(executed_sqls) == 0
    assert len(connections) == 0
    print('PASS')
"""
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert p.returncode == 0, f"stdout={p.stdout}, stderr={p.stderr}"
        assert "PASS" in p.stdout


# ---------------------------------------------------------------------------
# 9. is_production_environment / is_local_or_test_environment helpers
# ---------------------------------------------------------------------------

class TestEnvironmentHelpers:
    def test_is_production_explicit_value(self):
        assert is_production_environment("production") is True
        assert is_production_environment("PRODUCTION") is True
        assert is_production_environment("development") is False
        assert is_production_environment("") is False
        assert is_production_environment(None) is False

    def test_is_local_or_test_explicit_value(self):
        for env in ["development", "dev", "local", "test", "testing"]:
            assert is_local_or_test_environment(env) is True
        for env in ["production", "staging", "", "sandbox"]:
            assert is_local_or_test_environment(env) is False

    def test_is_production_reads_from_os_env(self):
        with _env_set(ENV="production", ENVIRONMENT=None):
            assert is_production_environment() is True
        with _env_set(ENV=None, ENVIRONMENT=None):
            assert is_production_environment() is False

    def test_is_local_or_test_reads_from_os_env(self):
        with _env_set(ENV="test", ENVIRONMENT=None):
            assert is_local_or_test_environment() is True
        with _env_set(ENV="production", ENVIRONMENT=None):
            assert is_local_or_test_environment() is False
        with _env_set(ENV=None, ENVIRONMENT=None):
            assert is_local_or_test_environment() is False
