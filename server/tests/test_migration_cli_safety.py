"""Migration CLI target safety: explicit URL only, no fallback, no prod hosts."""
import logging

import pytest
from sqlalchemy import create_engine, inspect

import server.models  # noqa: F401  # register every table on Base.metadata
from server.database.db import Base
from server.database.target_guard import (
    describe_target,
    redact_text,
    validate_target_url,
)
from server.scripts import migrate


@pytest.fixture
def migrations_dir(tmp_path):
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "001_create_widgets.sql").write_text(
        "CREATE TABLE IF NOT EXISTS widgets (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def no_engine(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("create_engine must not be reached for a refused target")

    monkeypatch.setattr(migrate, "create_engine", _fail)


def _run(argv, caplog, level=logging.INFO):
    caplog.clear()
    with caplog.at_level(level, logger="ecopulse.migrate"):
        return migrate.main(argv)


@pytest.mark.parametrize(
    "command",
    [
        ["status"],
        ["check"],
        ["up", "--yes"],
        ["up", "--dry-run"],
        ["adopt", "--through", "000", "--yes"],
        ["reconcile", "--record", "001", "--yes"],
    ],
)
def test_every_command_requires_an_explicit_url(no_engine, migrations_dir, caplog, command):
    assert _run([*command, "--migrations-dir", str(migrations_dir)], caplog) == 2
    assert "explicit --url" in caplog.text
    assert "DATABASE_URL is never used" in caplog.text


def test_database_url_is_never_used_as_a_fallback(
    monkeypatch, no_engine, migrations_dir, caplog, tmp_path
):
    fallback = tmp_path / "fallback.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{fallback.as_posix()}")

    assert _run(["status", "--migrations-dir", str(migrations_dir)], caplog) == 2
    assert not fallback.exists()


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "postgresql://app:supersecret@ep-cool-123456.us-east-2.aws.neon.tech/ecopulse",
            "blocked production host",
        ),
        (
            "postgresql://app:supersecret@dpg-abc123.oregon-postgres.render.com/ecopulse",
            "blocked production host",
        ),
        (
            "postgresql://app:supersecret@db.example.com/ecopulse_dev",
            "non-local postgresql host",
        ),
        (
            "postgresql://app:supersecret@10.0.0.5:5432/ecopulse",
            "disposable database names",
        ),
        (
            "postgresql://app:supersecret@10.0.0.5:5432/ecopulse_test",
            "disposable",
        ),
        ("postgresql://app:supersecret@127.0.0.1:5432/", "database name"),
        ("postgresql://app:supersecret@127.0.0.1:5432/postgres", "system database"),
        ("mysql://app:supersecret@127.0.0.1/ecopulse", "unsupported database driver"),
        ("not-a-url", "must include a scheme"),
    ],
)
def test_unsafe_targets_are_refused_before_any_connection(
    no_engine, migrations_dir, caplog, url, expected
):
    assert _run(["status", "--url", url, "--migrations-dir", str(migrations_dir)], caplog) == 2
    assert expected in caplog.text.lower()
    assert "supersecret" not in caplog.text


@pytest.mark.parametrize("url", [
    "postgresql://app:pw@127.0.0.1:5432/ecopulse_test",
    "postgresql://app:pw@localhost/ecopulse_dev",
])
def test_loopback_disposable_targets_are_accepted(url):
    normalized = validate_target_url(url, require_disposable=True,
                                     disposable_authorization="DISPOSABLE")

    assert normalized.startswith("postgresql://")
    assert "pw" not in describe_target(normalized)


def test_private_test_target_requires_explicit_disposable_designation():
    from server.database.target_guard import TargetSafetyError

    with pytest.raises(TargetSafetyError, match="require --authorize-disposable-target"):
        validate_target_url("postgresql://app:pw@10.0.0.5:5432/ecopulse_test")


def test_private_production_like_database_name_is_rejected_even_if_test_marked():
    from server.database.target_guard import TargetSafetyError

    with pytest.raises(TargetSafetyError, match="production-like"):
        validate_target_url(
            "postgresql://app:pw@10.0.0.5:5432/ecopulse_production_test",
            disposable_authorization="DISPOSABLE",
            require_disposable=True,
        )


def test_private_test_target_with_designation_is_accepted():
    url = "postgresql://app:pw@10.0.0.5:5432/ecopulse_test"
    assert validate_target_url(url, disposable_authorization="DISPOSABLE",
                               require_disposable=True) == url


def test_public_ip_is_rejected():
    from server.database.target_guard import TargetSafetyError

    with pytest.raises(TargetSafetyError, match="non-local PostgreSQL host"):
        validate_target_url("postgresql://app:pw@8.8.8.8:5432/ecopulse_test",
                            disposable_authorization="DISPOSABLE")


@pytest.mark.parametrize("host", ["example.neon.tech", "db.example.render.com"])
def test_neon_and_render_hosts_remain_blocked(host):
    from server.database.target_guard import TargetSafetyError

    with pytest.raises(TargetSafetyError, match="blocked production host"):
        validate_target_url(f"postgresql://app:pw@{host}/ecopulse_test",
                            disposable_authorization="DISPOSABLE")


@pytest.mark.parametrize("designation", [None, "", "YES", "disposable", "PRODUCTION"])
def test_missing_or_malformed_disposable_designation_is_rejected(designation):
    from server.database.target_guard import TargetSafetyError

    with pytest.raises(TargetSafetyError, match="DISPOSABLE"):
        validate_target_url("postgresql://app:pw@127.0.0.1:5432/ecopulse_test",
                            disposable_authorization=designation, require_disposable=True)


def test_validate_target_rejects_missing_url():
    from server.database.target_guard import TargetSafetyError

    with pytest.raises(TargetSafetyError):
        validate_target_url(None)


@pytest.mark.parametrize(
    "text",
    [
        "postgresql://app:supersecret@host:5432/db",
        "failed to connect: postgres://user:supersecret@host/db",
        "connection password=supersecret host=db",
    ],
)
def test_redaction_removes_credentials(text):
    redacted = redact_text(text)

    assert "supersecret" not in redacted


def test_connection_failure_is_reported_without_credentials(monkeypatch, migrations_dir, caplog):
    class ExplodingEngine:
        def connect(self):
            raise RuntimeError("boom postgresql://app:supersecret@127.0.0.1/db")

        def dispose(self):
            pass

    monkeypatch.setattr(migrate, "create_engine", lambda *a, **k: ExplodingEngine())

    rc = _run(
        [
            "status",
            "--url",
            "postgresql://app:supersecret@127.0.0.1:5432/ecopulse_dev",
            "--migrations-dir",
            str(migrations_dir),
        ],
        caplog,
    )

    assert rc == 2
    assert "Target refused" in caplog.text
    assert "supersecret" not in caplog.text


def test_unexpected_errors_are_redacted(monkeypatch, migrations_dir, caplog):
    raw_url = "postgresql://app:supersecret@127.0.0.1:5432/ecopulse_dev"

    def _boom(*args, **kwargs):
        raise RuntimeError(f"dialect failed for {raw_url}")

    monkeypatch.setattr(migrate, "create_engine", _boom)

    rc = _run(["status", "--url", raw_url, "--migrations-dir", str(migrations_dir)], caplog)

    assert rc == 1
    assert "supersecret" not in caplog.text


def test_explicit_sqlite_target_still_works(tmp_path, migrations_dir, caplog):
    url = f"sqlite:///{(tmp_path / 'target.db').as_posix()}"

    assert _run(["up", "--yes", "--authorize-disposable-target", "DISPOSABLE",
                 "--url", url, "--migrations-dir", str(migrations_dir)], caplog) == 0

    engine = create_engine(url)
    try:
        assert "widgets" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_cli_can_adopt_an_existing_sqlite_schema(tmp_path, caplog):
    url = f"sqlite:///{(tmp_path / 'adopt.db').as_posix()}"
    engine = create_engine(url)
    try:
        Base.metadata.create_all(bind=engine)
    finally:
        engine.dispose()

    assert _run(["adopt", "--through", "007", "--yes", "--authorize-disposable-target",
                 "DISPOSABLE", "--url", url], caplog) == 0
    assert "Adoption complete" in caplog.text


def test_invalid_through_value_is_refused(tmp_path, caplog):
    url = f"sqlite:///{(tmp_path / 'through.db').as_posix()}"

    assert _run(["adopt", "--through", "7", "--yes", "--authorize-disposable-target",
                 "DISPOSABLE", "--url", url], caplog) == 2
    assert "Invalid --through" in caplog.text
