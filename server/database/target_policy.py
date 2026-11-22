"""Target policy for development schema and seed mutations.

The application environment is not evidence that the configured database is
disposable. Every development mutation must classify the actual SQLAlchemy URL
before issuing DDL or inserting fixture data.
"""
from __future__ import annotations

import ipaddress
import os
import re
from typing import Any

from sqlalchemy.engine import make_url


MUTATION_ENVIRONMENTS = frozenset({"development", "dev", "local", "test", "testing"})
_PRODUCTION_MARKERS = frozenset({"prod", "production", "live"})


class UnsafeDatabaseTarget(RuntimeError):
    """Raised when a development mutation target is not safely disposable."""


def _engine_url(target: Any) -> str:
    value = getattr(target, "url", target)
    if value is None:
        raise UnsafeDatabaseTarget("Database mutation refused: target URL is unavailable.")
    try:
        # Credentials are needed only for in-memory comparison with the explicit
        # disposable designation; this value is never logged or included in errors.
        return value.render_as_string(hide_password=False) if hasattr(value, "render_as_string") else str(value)
    except Exception:
        raise UnsafeDatabaseTarget("Database mutation refused: target URL is ambiguous.") from None


def validate_development_target(target: Any, environment: str) -> str:
    """Validate a concrete database target before development/test mutations.

    SQLite is allowed only for local filesystem or in-memory databases. PostgreSQL
    mutation is test-only and requires the existing disposable-name/provider
    checks, explicit DISPOSABLE authorization, an independently designated test
    URL matching the resolved target, and loopback networking.
    """
    env = (environment or "").strip().lower()
    if env not in MUTATION_ENVIRONMENTS:
        raise UnsafeDatabaseTarget(
            f"Database mutation refused: environment {env or '<unset>'!r} is not development/test."
        )
    from server.utils.config import get_environment

    try:
        configured_env = get_environment()
    except RuntimeError:
        raise UnsafeDatabaseTarget(
            "Database mutation refused: configured runtime environment is unknown or conflicting."
        ) from None
    if configured_env not in MUTATION_ENVIRONMENTS:
        raise UnsafeDatabaseTarget(
            f"Database mutation refused: configured runtime environment {configured_env!r} is not development/test."
        )

    raw_url = _engine_url(target)
    try:
        parsed = make_url(raw_url)
    except Exception:
        raise UnsafeDatabaseTarget("Database mutation refused: target URL is invalid.") from None

    driver = parsed.drivername.lower()
    if driver.startswith("sqlite"):
        database = parsed.database or ":memory:"
        if parsed.host:
            raise UnsafeDatabaseTarget("Database mutation refused: remote SQLite targets are not allowed.")
        # SQLite's //host/share form can refer to a network share on Windows.
        # POSIX permits a double-leading-slash absolute local path (SQLAlchemy
        # renders /tmp/... as sqlite:////tmp/...), so reject it only on Windows.
        normalized_path = database.replace("\\", "/")
        path_parts = [part.lower() for part in normalized_path.split("/") if part]
        file_tokens = re.split(r"[_.-]+", path_parts[-1].rsplit(".", 1)[0]) if path_parts else []
        production_named = any(part in _PRODUCTION_MARKERS for part in path_parts[:-1]) or any(
            token in _PRODUCTION_MARKERS for token in file_tokens
        )
        if (os.name == "nt" and normalized_path.startswith("//")) or production_named:
            raise UnsafeDatabaseTarget("Database mutation refused: SQLite target is remote or production-like.")
        return raw_url

    if driver not in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        raise UnsafeDatabaseTarget(
            f"Database mutation refused: unsupported or ambiguous target driver {driver!r}."
        )

    if env not in {"test", "testing"} or configured_env not in {"test", "testing"}:
        raise UnsafeDatabaseTarget(
            "PostgreSQL schema/seed mutation is permitted only in test environments."
        )

    from server.database.target_guard import (
        DISPOSABLE_AUTHORIZATION,
        TargetSafetyError,
        validate_target_url,
    )

    authorization = os.getenv("ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION")
    if authorization != DISPOSABLE_AUTHORIZATION:
        raise UnsafeDatabaseTarget(
            "PostgreSQL development mutation requires explicit disposable-target authorization."
        )
    designated_url = (os.getenv("ECOLPULSE_DISPOSABLE_POSTGRES_URL") or "").strip()
    if not designated_url:
        raise UnsafeDatabaseTarget(
            "PostgreSQL test mutation requires ECOLPULSE_DISPOSABLE_POSTGRES_URL."
        )
    try:
        normalized = validate_target_url(
            raw_url,
            disposable_authorization=authorization,
            require_disposable=True,
        )
        validated = make_url(normalized)
        designated = make_url(designated_url)
        # Compare the actual resolved target to the separately designated test
        # URL, including credentials and query parameters, without logging either.
        resolved_identity = (
            validated.drivername.replace("+psycopg2", "").replace("+psycopg", ""),
            validated.username,
            validated.password,
            (validated.host or "").lower(),
            validated.port,
            validated.database,
            tuple(sorted((validated.query or {}).items())),
        )
        designated_identity = (
            designated.drivername.replace("+psycopg2", "").replace("+psycopg", ""),
            designated.username,
            designated.password,
            (designated.host or "").lower(),
            designated.port,
            designated.database,
            tuple(sorted((designated.query or {}).items())),
        )
        if resolved_identity != designated_identity:
            raise UnsafeDatabaseTarget(
                "PostgreSQL mutation URL does not match the independently designated disposable test URL."
            )
        host = (validated.host or "").strip("[]").lower()
        if host == "localhost":
            return normalized
        try:
            if ipaddress.ip_address(host).is_loopback:
                return normalized
        except ValueError:
            pass
    except TargetSafetyError as exc:
        raise UnsafeDatabaseTarget(f"PostgreSQL development target refused: {exc}") from None

    raise UnsafeDatabaseTarget(
        "PostgreSQL development mutations are restricted to an explicitly authorized loopback disposable database."
    )

