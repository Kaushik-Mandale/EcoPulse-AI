"""Regression tests for database target checks before dev/test mutations."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

import server.models  # noqa: F401
from server.database.db import Base
from server.database.initialization import initialize_database
from server.database.target_policy import (
    UnsafeDatabaseTarget,
    validate_development_target,
)


PRODUCTION_URL = "postgresql://app:secret@db.example.com/ecopulse"
DISPOSABLE_URL = "postgresql://app:secret@127.0.0.1:5432/ecopulse_test"


def _target(url: str):
    """An engine-shaped object that cannot open a network connection."""
    return SimpleNamespace(url=url)


def test_development_init_rejects_production_postgres_url_before_ddl(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    calls = []
    monkeypatch.setattr(
        "server.database.initialization._create_base_schema",
        lambda *_args: calls.append("create"),
    )

    with pytest.raises(UnsafeDatabaseTarget):
        initialize_database(_target(PRODUCTION_URL), "development")
    assert calls == []


def test_application_startup_rejects_target_before_connectivity_probe(monkeypatch):
    import server.main as main
    import server.database.db as db_module

    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setattr(main, "engine", _target(PRODUCTION_URL))
    monkeypatch.setattr(main, "get_environment", lambda: "development")
    monkeypatch.setattr(main.config, "reload", lambda: None)
    connections = []
    monkeypatch.setattr(db_module, "validate_database_connection", lambda _engine: connections.append(True))

    startup = main.lifespan(main.app)
    with pytest.raises(UnsafeDatabaseTarget):
        startup.__aenter__().send(None)
    assert connections == []


def test_production_environment_cannot_force_development_initialization(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(UnsafeDatabaseTarget):
        initialize_database(_target(PRODUCTION_URL), "production", allow_mutation=True)


def test_production_runtime_cannot_be_overridden_by_development_argument(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    with pytest.raises(UnsafeDatabaseTarget, match="configured runtime environment"):
        validate_development_target("sqlite:///:memory:", "development")


def test_development_sqlite_initialization_remains_supported(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'local-dev.db').as_posix()}")
    try:
        initialize_database(engine, "development")
    finally:
        engine.dispose()


def test_authorized_loopback_disposable_postgres_target_is_accepted(monkeypatch):
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION", "DISPOSABLE")
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_URL", DISPOSABLE_URL)
    assert validate_development_target(_target(DISPOSABLE_URL), "test") == DISPOSABLE_URL


@pytest.mark.parametrize(
    "url",
    [
        "not-a-database-url",
        "mysql://localhost/ecopulse_test",
        "sqlite:////production/share/ecopulse.db",
    ],
)
def test_unknown_or_ambiguous_target_fails_closed(url):
    with pytest.raises(UnsafeDatabaseTarget):
        validate_development_target(_target(url), "development")


def test_remote_disposable_postgres_is_not_accepted_for_app_mutation(monkeypatch):
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION", "DISPOSABLE")
    remote_url = "postgresql://app:secret@10.0.0.8:5432/ecopulse_test"
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_URL", remote_url)
    with pytest.raises(UnsafeDatabaseTarget, match="loopback disposable"):
        validate_development_target(_target(remote_url), "test")


def test_development_environment_cannot_mutate_postgres_even_if_designated(monkeypatch):
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION", "DISPOSABLE")
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_URL", DISPOSABLE_URL)
    with pytest.raises(UnsafeDatabaseTarget, match="only in test environments"):
        validate_development_target(_target(DISPOSABLE_URL), "development")


def test_postgres_target_must_match_separate_disposable_designation(monkeypatch):
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION", "DISPOSABLE")
    monkeypatch.setenv("ECOLPULSE_DISPOSABLE_POSTGRES_URL", DISPOSABLE_URL)
    different_url = "postgresql://app:secret@127.0.0.1:5432/ecopulse_other_test"
    with pytest.raises(UnsafeDatabaseTarget, match="does not match"):
        validate_development_target(_target(different_url), "test")


def test_demo_seeding_rejects_production_url_even_when_env_is_development(monkeypatch):
    from server.services.auth_service import AuthService

    class Session:
        def get_bind(self):
            return _target(PRODUCTION_URL)

        def query(self, *_args, **_kwargs):  # pragma: no cover - must not be reached
            pytest.fail("seed target was queried before validation")

    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert AuthService.should_seed_demo_users(Session()) is False
    with pytest.raises(UnsafeDatabaseTarget):
        AuthService.seed_demo_users(Session())


@pytest.mark.parametrize("script_name", ["server.init_db", "server.database.init_db"])
def test_standalone_initializers_reject_target_before_create_all(
    monkeypatch, script_name
):
    import importlib
    import server.database.db as db_module

    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setattr(db_module, "engine", _target(PRODUCTION_URL))
    calls = []
    monkeypatch.setattr(Base.metadata, "create_all", lambda **_kwargs: calls.append("ddl"))
    script = importlib.import_module(script_name)
    entry = "initialize_database" if script_name == "server.init_db" else "init_and_seed_db"

    with pytest.raises(UnsafeDatabaseTarget):
        getattr(script, entry)()
    assert calls == []


@pytest.mark.parametrize(
    "module_name,function_name",
    [
        ("server.database.db", "ensure_complaints_schema"),
        ("server.database.db", "ensure_users_schema"),
        ("server.models.whatsapp_session", "ensure_whatsapp_processed_messages_schema"),
        ("server.models.whatsapp_session", "ensure_whatsapp_citizens_schema"),
    ],
)
def test_compatibility_helpers_validate_before_ddl(
    monkeypatch, module_name, function_name
):
    import importlib
    from server.models.mobile_otp import MobileOtpToken

    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    calls = []
    monkeypatch.setattr(MobileOtpToken.__table__, "create", lambda *_a, **_k: calls.append("ddl"))
    module = importlib.import_module(module_name)

    with pytest.raises(UnsafeDatabaseTarget):
        getattr(module, function_name)(_target(PRODUCTION_URL))
    assert calls == []


def test_manual_sample_seed_path_validates_before_schema_or_data_access(monkeypatch):
    import server.database.db as db_module
    from server.database.init_db import init_and_seed_db

    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setattr(db_module, "engine", _target(PRODUCTION_URL))
    calls = []
    monkeypatch.setattr(Base.metadata, "create_all", lambda **_kwargs: calls.append("ddl"))

    with pytest.raises(UnsafeDatabaseTarget):
        init_and_seed_db()
    assert calls == []

