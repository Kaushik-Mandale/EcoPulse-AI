"""Startup sequence policy: production never rewrites id sequences."""
import pytest
from types import SimpleNamespace

from server.database.db import SessionLocal
from server.database.initialization import (
    IDENTIFIER_SEQUENCE_TABLES,
    resynchronize_sequences,
)


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class RecordingSession:
    """Minimal Session stand-in that records every statement."""

    def __init__(self, sequence_name="public.users_id_seq", max_id=7):
        self.sequence_name = sequence_name
        self.max_id = max_id
        self.calls = []
        self.commits = 0

    def get_bind(self):
        return SimpleNamespace(
            url="postgresql://tester:disposable@127.0.0.1:5432/ecopulse_test"
        )

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.calls.append((sql, parameters))
        if "pg_get_serial_sequence" in sql:
            return _Result(self.sequence_name if "'users'" in sql else None)
        if "COALESCE(MAX" in sql:
            return _Result(self.max_id)
        return _Result(None)

    def commit(self):
        self.commits += 1


@pytest.mark.parametrize("env", ["production", "staging", "prod", "", None])
def test_non_mutating_environments_never_touch_sequences(env):
    session = RecordingSession()

    resynchronize_sequences(session, env)

    assert session.calls == []
    assert session.commits == 0


@pytest.mark.parametrize("env", ["test", "testing"])
def test_mutation_environments_resynchronise_sequences(env, monkeypatch):
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION", "DISPOSABLE")
    monkeypatch.setenv(
        "ECOLPULSE_DISPOSABLE_POSTGRES_URL",
        "postgresql://tester:disposable@127.0.0.1:5432/ecopulse_test",
    )
    session = RecordingSession()

    resynchronize_sequences(session, env)

    setval_calls = [(sql, params) for sql, params in session.calls if "setval" in sql]
    assert len(setval_calls) == 1
    sql, params = setval_calls[0]
    assert "setval" in sql
    assert params == {"sequence": "public.users_id_seq", "value": 8}
    assert session.commits == 1


@pytest.mark.parametrize("env", ["development", "dev", "local"])
def test_local_development_cannot_mutate_postgres_sequences(env, monkeypatch):
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION", "DISPOSABLE")
    monkeypatch.setenv(
        "ECOLPULSE_DISPOSABLE_POSTGRES_URL",
        "postgresql://tester:disposable@127.0.0.1:5432/ecopulse_test",
    )
    session = RecordingSession()
    with pytest.raises(RuntimeError, match="only in test environments"):
        resynchronize_sequences(session, env)
    assert session.calls == []


def test_all_identifier_tables_are_considered(monkeypatch):
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION", "DISPOSABLE")
    monkeypatch.setenv(
        "ECOLPULSE_DISPOSABLE_POSTGRES_URL",
        "postgresql://tester:disposable@127.0.0.1:5432/ecopulse_test",
    )
    session = RecordingSession()

    resynchronize_sequences(session, "test")

    inspected_tables = [
        (sql, params)
        for sql, params in session.calls
        if "pg_get_serial_sequence" in sql
    ]
    assert len(inspected_tables) == len(IDENTIFIER_SEQUENCE_TABLES)


def test_sqlite_development_startup_tolerates_missing_pg_functions():
    db = SessionLocal()
    try:
        resynchronize_sequences(db, "test")
    finally:
        db.close()
