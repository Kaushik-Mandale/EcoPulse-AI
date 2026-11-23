"""Target-database safety checks for the migration CLI.

The migration runner must never guess its target and must never reach a hosted
production database by accident. Every command therefore requires an explicit
URL, and this module enforces:

- no URL fallback (the caller rejects a missing URL before engine creation);
- supported drivers only;
- blocked hosted providers, public PostgreSQL hosts, system databases, and
  production-like database names are refused;
- private PostgreSQL IPs require both a disposable-style database name and an
  explicit disposable-target designation;
- credentials are redacted from every log line and error message.

Confirmed mutations require an explicit disposable-target designation.
Production targets have no override or bypass in this runner.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Optional

from sqlalchemy.engine import make_url

ALLOWED_DRIVERS = frozenset(
    {
        "sqlite",
        "sqlite+pysqlite",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }
)

# Hosted providers that must never be targeted by the migration CLI.
BLOCKED_HOST_SUFFIXES = (
    ".neon.tech",
    ".neon.build",
    ".render.com",
    ".supabase.co",
    ".supabase.com",
    ".railway.app",
)

SYSTEM_DATABASES = frozenset({"postgres", "template0", "template1"})
DISPOSABLE_DATABASE_RE = re.compile(r"(?:^|[_-])(test|testing|dev|development|local|disposable|ci)(?:$|[_-])", re.I)
PRODUCTION_DATABASE_RE = re.compile(r"(?:^|[_-])(prod|production|live)(?:$|[_-])", re.I)
DISPOSABLE_AUTHORIZATION = "DISPOSABLE"

# scheme://userinfo@ -> scheme://***@
_USERINFO_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^/@\s]+@")
_PASSWORD_PARAM_RE = re.compile(r"(?i)(password\s*=\s*)[^&\s;]+")


class TargetSafetyError(RuntimeError):
    """Raised when a migration target is missing, unsupported, or refused."""


def normalize_database_url(url: str) -> str:
    normalized = (url or "").strip()
    if normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", "postgresql://", 1)
    return normalized


def redact_text(value: object) -> str:
    """Remove credentials from arbitrary text (log lines, exception messages)."""
    redacted = _USERINFO_RE.sub(r"\1***@", str(value))
    return _PASSWORD_PARAM_RE.sub(r"\1***", redacted)


def describe_target(url: str) -> str:
    """Human-readable target without user, password, or query parameters."""
    try:
        parsed = make_url(normalize_database_url(url))
    except Exception:
        return "<invalid-database-url>"
    if parsed.drivername.startswith("sqlite"):
        return f"{parsed.drivername}://{parsed.database or '<default>'}"
    host = parsed.host or "<no-host>"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return f"{parsed.drivername}://{host}/{parsed.database or '<no-database>'}"


# Backwards-compatible alias used by earlier call sites/tests.
redact_url = describe_target


def _is_loopback_postgres_host(host: str) -> bool:
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback


def _is_private_postgres_host(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private and not address.is_loopback


def validate_target_url(
    url: Optional[str],
    *,
    disposable_authorization: Optional[str] = None,
    require_disposable: bool = False,
) -> str:
    """Validate and normalize an explicit migration target URL.

    Raises TargetSafetyError with a credential-free message when the target is
    missing, unsupported, or refused. Returns the normalized URL.
    """
    raw = (url or "").strip()
    if not raw:
        raise TargetSafetyError(
            "An explicit --url is required; the application DATABASE_URL is never used."
        )
    if "://" not in raw:
        raise TargetSafetyError("The target URL must include a scheme (e.g. postgresql://).")

    normalized = normalize_database_url(raw)
    try:
        parsed = make_url(normalized)
    except Exception:
        raise TargetSafetyError("The target URL is not a valid SQLAlchemy database URL.") from None

    driver = parsed.drivername.lower()
    if driver not in ALLOWED_DRIVERS:
        raise TargetSafetyError(
            f"Unsupported database driver '{parsed.drivername}'. "
            f"Allowed drivers: {sorted(ALLOWED_DRIVERS)}."
        )

    if driver.startswith("sqlite"):
        if require_disposable and disposable_authorization != DISPOSABLE_AUTHORIZATION:
            raise TargetSafetyError(
                "Migration execution requires --authorize-disposable-target DISPOSABLE."
            )
        return normalized

    host = (parsed.host or "").strip().lower()
    if not host:
        raise TargetSafetyError("The target PostgreSQL URL must include a host.")
    if host.endswith(BLOCKED_HOST_SUFFIXES):
        raise TargetSafetyError(
            f"Refusing blocked production host '{host}'. "
            "Neon, Render, and other hosted providers are not permitted for migrations."
        )
    database = (parsed.database or "").strip()
    if not database:
        raise TargetSafetyError("The target PostgreSQL URL must include a database name.")
    if database.lower() in SYSTEM_DATABASES:
        raise TargetSafetyError(
            f"Refusing PostgreSQL system database '{database}'. Select the application database."
        )
    if PRODUCTION_DATABASE_RE.search(database):
        raise TargetSafetyError(
            f"Refusing production-like PostgreSQL database name '{database}'."
        )

    is_loopback = _is_loopback_postgres_host(host)
    is_private = _is_private_postgres_host(host)
    if not is_loopback and not is_private:
        raise TargetSafetyError(
            f"Refusing non-local PostgreSQL host '{host}'. "
            "Only loopback or explicitly designated disposable private targets are permitted."
        )
    if not DISPOSABLE_DATABASE_RE.search(database):
        raise TargetSafetyError(
            f"Refusing PostgreSQL database '{database}'; disposable database names must identify test, dev, local, disposable, or CI use."
        )
    if is_private and disposable_authorization != DISPOSABLE_AUTHORIZATION:
        raise TargetSafetyError(
            "Private-network PostgreSQL targets require --authorize-disposable-target DISPOSABLE."
        )
    if require_disposable and disposable_authorization != DISPOSABLE_AUTHORIZATION:
        raise TargetSafetyError(
            "Migration execution requires --authorize-disposable-target DISPOSABLE."
        )
    return normalized


def validate_connection(engine) -> None:
    """Fail fast if the validated target cannot be reached."""
    from sqlalchemy import text

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - surfaced as a credential-free error
        raise TargetSafetyError(
            f"Target database validation failed ({type(exc).__name__}): {redact_text(exc)}"
        ) from None
