"""`status`, `plan`, and `diagnose` must never mutate the database."""
import re

import pytest
from sqlalchemy import create_engine, event, inspect, text

import server.models  # noqa: F401  # register every table on Base.metadata
from server.database.db import Base
from server.database.migrations_runner import (
    HISTORY_TABLE,
    diagnose,
    discover_migrations,
    ensure_history_table,
    plan,
    status,
)
from server.scripts import migrate

MUTATING_SQL = re.compile(
    r"\b(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|REPLACE|TRUNCATE)\b", re.IGNORECASE
)


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'readonly.db').as_posix()}")
    statements = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    engine.captured = statements
    try:
        yield engine
    finally:
        engine.dispose()


def _tables(engine):
    return set(inspect(engine).get_table_names())


def _assert_no_mutation(engine):
    offending = [s for s in engine.captured if MUTATING_SQL.search(s)]
    assert offending == []


def test_status_on_empty_database_is_read_only(engine):
    state = status(engine)

    assert state["initialized"] is False
    assert state["applied"] == []
    assert state["in_progress"] == []
    assert len(state["pending"]) == len(discover_migrations())
    assert HISTORY_TABLE not in _tables(engine)
    _assert_no_mutation(engine)


def test_status_does_not_adopt_an_existing_schema(engine):
    Base.metadata.create_all(bind=engine)
    before = _tables(engine)
    engine.captured.clear()

    state = status(engine)

    assert state["initialized"] is False
    assert state["applied"] == []
    assert HISTORY_TABLE not in _tables(engine)
    assert _tables(engine) == before
    _assert_no_mutation(engine)


def test_status_with_history_is_select_only(engine):
    ensure_history_table(engine)
    engine.captured.clear()

    state = status(engine)

    assert state["initialized"] is True
    assert _tables(engine) == {HISTORY_TABLE}
    _assert_no_mutation(engine)


def test_plan_is_read_only(engine):
    applied, pending = plan(engine)

    assert applied == {}
    assert pending
    assert HISTORY_TABLE not in _tables(engine)
    _assert_no_mutation(engine)


def test_diagnose_is_read_only(engine):
    Base.metadata.create_all(bind=engine)
    engine.captured.clear()

    issues = diagnose(engine)

    assert [issue.code for issue in issues] == ["uninitialized_existing_schema"]
    assert HISTORY_TABLE not in _tables(engine)
    _assert_no_mutation(engine)


def test_cli_status_is_read_only(tmp_path, monkeypatch, caplog):
    url = f"sqlite:///{(tmp_path / 'cli_status.db').as_posix()}"
    engine = create_engine(url)
    statements = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, parameters, context, executemany: statements.append(
            statement
        ),
    )
    monkeypatch.setattr(migrate, "create_engine", lambda *args, **kwargs: engine)
    try:
        with caplog.at_level("INFO", logger="ecopulse.migrate"):
            assert migrate.main(["status", "--url", url]) == 0
        assert not any(MUTATING_SQL.search(s) for s in statements)
        assert HISTORY_TABLE not in set(inspect(engine).get_table_names())
        assert "has not been initialized" in caplog.text
    finally:
        engine.dispose()


def test_cli_dry_run_does_not_create_history(engine, tmp_path, monkeypatch):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_create_widgets.sql").write_text(
        "CREATE TABLE IF NOT EXISTS widgets (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
    )
    monkeypatch.setattr(migrate, "create_engine", lambda *args, **kwargs: engine)

    assert (
        migrate.main(
            [
                "up",
                "--dry-run",
                "--url",
                str(engine.url),
                "--migrations-dir",
                str(migrations_dir),
            ]
        )
        == 0
    )
    assert HISTORY_TABLE not in _tables(engine)
    assert "widgets" not in _tables(engine)
