"""Explicit, ordered SQL migration runner.

Production startup never executes migrations. The operator CLI and guarded
non-production initialization share this runner; both use migration history,
ordering, checksums, and target authorization. Every applied version is
recorded in ``schema_migrations``.

Safety properties:
- Applied versions are recorded with a checksum; edited files are rejected.
- Out-of-order execution is refused once a newer version is applied.
- Duplicate version filenames are refused.
- A non-empty database with no migration history must be adopted first, so an
  unknown existing schema is never mutated blindly.
- Rollback files and manual approval scripts are excluded from discovery.
- ``status`` and ``diagnose`` are strictly read-only.

Crash-window handling (history is a small state machine):
- Runner-managed scripts (no leading ``BEGIN;``) are executed on PostgreSQL in
  one transaction that also inserts the history row, so DDL and history commit
  together or not at all.
- Self-managed scripts (``BEGIN; ... COMMIT;``) cannot be wrapped. A row with
  method ``applying`` is committed first, the script runs, then the row is
  finalized. A crash between the script's COMMIT and finalization leaves an
  ``applying`` row that blocks further execution.
- Recovery is always explicit, after human review:
    1. ``python -m server.scripts.migrate check`` lists the incomplete version.
    2. If the expected objects exist, ``reconcile --record VERSION --yes``
       finalizes the row as ``reconciled``.
    3. If they do not exist, ``reconcile --clear VERSION --yes`` removes the
       marker so the migration can be applied again.
  The runner never adopts or reconciles automatically.
"""
from __future__ import annotations

import hashlib
import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

HISTORY_TABLE = "schema_migrations"
BASELINE_VERSION = "000"

# A migration row is inserted with method='applying' before a self-managed
# script runs and moved to a terminal method after it commits. Rows with a
# non-terminal method block further execution until an operator reconciles them.
APPLYING_METHOD = "applying"
TERMINAL_METHODS = frozenset({"applied", "adopted", "reconciled", "baseline"})

# Session-scoped PostgreSQL advisory lock; stable across processes/releases.
MIGRATION_LOCK_KEY = (
    int.from_bytes(hashlib.sha256(b"ecopulse:schema-migrations").digest()[:8], "big")
    & 0x7FFF_FFFF_FFFF_FFFF
)

_VERSION_RE = re.compile(r"^(\d{3})_([a-z0-9_]+)\.sql$", re.IGNORECASE)
_TRANSACTION_START_RE = re.compile(r"^\s*BEGIN\s*;", re.IGNORECASE | re.MULTILINE)
_EXCLUDED_STEM_MARKERS = ("_down", "_legacy_")

# Tables that must exist before an existing database may be adopted as baseline.
BASE_SCHEMA_TABLES = frozenset(
    {
        "users",
        "complaints",
        "tasks",
        "items",
        "fuel_logs",
        "driver_performances",
        "messages",
        "smart_bins",
        "notifications",
        "whatsapp_citizens",
        "whatsapp_processed_messages",
    }
)

# Objects each incremental migration must have produced, used only for adoption
# verification (never for execution decisions).
SENTINELS = {
    "001": {
        "tables": ("complaints",),
        "columns": {
            "complaints": {
                "whatsapp_citizen_id": {
                    "type": ("INTEGER", "INT", "BIGINT"),
                    "nullable": True,
                }
            }
        },
        "foreign_keys": (
            {
                "table": "complaints",
                "columns": ("whatsapp_citizen_id",),
                "referred_table": "whatsapp_citizens",
                "referred_columns": ("id",),
                "ondelete": "SET NULL",
            },
        ),
        "indexes": (
            {
                "table": "complaints",
                "columns": ("whatsapp_citizen_id",),
                "name": "ix_complaints_whatsapp_citizen_id",
            },
        ),
    },
    "002": {
        "tables": ("complaints",),
        "columns": {
            "complaints": {
                "tracking_secret": {
                    "type": ("VARCHAR",),
                    "length": 64,
                    "nullable": True,
                }
            }
        },
        "indexes": (
            {
                "table": "complaints",
                "columns": ("tracking_secret",),
                "name": "ix_complaints_tracking_secret",
            },
        ),
    },
    "003": {
        "tables": ("whatsapp_citizens", "whatsapp_link_tokens"),
        "columns": {
            "whatsapp_citizens": {
                "user_id": {
                    "type": ("INTEGER", "INT", "BIGINT"),
                    "nullable": True,
                },
                "full_name": {
                    "default_contains": "Dhule Citizen",
                },
            },
            "whatsapp_link_tokens": {
                "id": {"type": ("INTEGER", "INT", "BIGINT")},
                "user_id": {"type": ("INTEGER", "INT", "BIGINT"), "nullable": False},
                "token_hash": {"type": ("VARCHAR",), "length": 64, "nullable": False},
                "expires_at": {"nullable": False},
                "consumed_at": {"nullable": True},
                "whatsapp_phone": {"nullable": True},
                "attempt_count": {"nullable": False},
                "created_at": {"nullable": False},
            },
        },
        "foreign_keys": (
            {
                "table": "whatsapp_citizens",
                "columns": ("user_id",),
                "referred_table": "users",
                "referred_columns": ("id",),
                "ondelete": "SET NULL",
            },
            {
                "table": "whatsapp_link_tokens",
                "columns": ("user_id",),
                "referred_table": "users",
                "referred_columns": ("id",),
                "ondelete": "CASCADE",
            },
        ),
        "indexes": (
            # Regular (non-unique) index for FK join performance — ix_whatsapp_citizens_user_id
            {
                "table": "whatsapp_citizens",
                "columns": ("user_id",),
                "name": "ix_whatsapp_citizens_user_id",
                "unique": False,
            },
            # Partial unique index — one User <-> at most one WhatsApp identity.
            # A plain full unique index is NOT equivalent: NULL rows must be excluded.
            {
                "table": "whatsapp_citizens",
                "columns": ("user_id",),
                "name": "uq_whatsapp_citizens_user_id_notnull",
                "unique": True,
                "partial_predicate": "user_id IS NOT NULL",
            },
            {
                "table": "whatsapp_link_tokens",
                "columns": ("token_hash",),
                "name": "ix_whatsapp_link_tokens_token_hash",
            },
            {
                "table": "whatsapp_link_tokens",
                "columns": ("user_id",),
                "name": "ix_whatsapp_link_tokens_user_id",
            },
        ),
    },
    "004": {
        "tables": ("mobile_otp_tokens", "users"),
        "columns": {
            "mobile_otp_tokens": {
                "id": {"type": ("INTEGER", "INT", "BIGINT")},
                "id": {"type": ("INTEGER", "INT", "BIGINT")},
                "phone": {"type": ("VARCHAR",), "length": 20, "nullable": False},
                "otp_hash": {"type": ("VARCHAR",), "length": 64, "nullable": False},
                "purpose": {"type": ("VARCHAR",), "length": 20, "nullable": False},
                "ip_address": {"nullable": True},
                "attempts": {"nullable": False},
                "max_attempts": {"nullable": False},
                "expires_at": {"nullable": False},
                "consumed_at": {"nullable": True},
                "created_at": {"nullable": False},
            },
            "users": {
                "email": {"nullable": True},
                "hashed_password": {"nullable": True},
                "phone": {"nullable": True},
            },
        },
        "indexes": (
            {
                "table": "mobile_otp_tokens",
                "columns": ("phone",),
                "name": "ix_mobile_otp_tokens_phone",
            },
            {
                "table": "mobile_otp_tokens",
                "columns": ("created_at",),
                "name": "ix_mobile_otp_tokens_created_at",
            },
            # Partial unique index — excludes NULLs and empty strings.
            # A plain full unique index is NOT equivalent.
            {
                "table": "users",
                "columns": ("phone",),
                "name": "uq_users_phone",
                "unique": True,
                "partial_predicate": "phone IS NOT NULL AND phone != ''",
            },
        ),
    },
    "011": {
        "tables": ("municipalities", "wards", "users"),
        "columns": {
            "municipalities": {
                "id": {"type": ("INTEGER", "INT", "BIGINT")},
                "code": {"type": ("VARCHAR",), "length": 40, "nullable": False},
                "name": {"type": ("VARCHAR",), "length": 120, "nullable": False},
                "is_active": {"nullable": False},
            },
            "wards": {
                "id": {"type": ("INTEGER", "INT", "BIGINT")},
                "municipality_id": {"type": ("INTEGER", "INT", "BIGINT"), "nullable": False},
                "ward_number": {"type": ("VARCHAR",), "length": 30, "nullable": False},
                "display_name": {"type": ("VARCHAR",), "length": 120, "nullable": False},
                "locality_description": {"nullable": True},
                "is_active": {"nullable": False},
            },
            "users": {
                "municipality_id": {"type": ("INTEGER", "INT", "BIGINT"), "nullable": True},
                "ward_id": {"type": ("INTEGER", "INT", "BIGINT"), "nullable": True},
                "ward": {"type": ("VARCHAR",), "length": 120, "nullable": True},
            },
        },
        "foreign_keys": (
            {"table": "wards", "columns": ("municipality_id",), "referred_table": "municipalities", "referred_columns": ("id",), "ondelete": "RESTRICT"},
            {"table": "users", "columns": ("municipality_id",), "referred_table": "municipalities", "referred_columns": ("id",), "ondelete": "RESTRICT"},
            {"table": "users", "columns": ("ward_id",), "referred_table": "wards", "referred_columns": ("id",), "ondelete": "RESTRICT"},
        ),
        "indexes": (
            {"table": "municipalities", "columns": ("code",), "name": "uq_municipalities_code", "unique": True},
            {"table": "municipalities", "columns": ("code",), "name": "ix_municipalities_code"},
            {"table": "wards", "columns": ("municipality_id", "ward_number"), "name": "uq_wards_municipality_number", "unique": True},
            {"table": "wards", "columns": ("municipality_id",), "name": "ix_wards_municipality_id"},
            {"table": "users", "columns": ("municipality_id",), "name": "ix_users_municipality_id"},
            {"table": "users", "columns": ("ward_id",), "name": "ix_users_ward_id"},
        ),
    },
    "012": {
        "tables": ("event_reports",),
        "columns": {
            "event_reports": {
                "id": {"type": ("INTEGER", "INT", "BIGINT")},
                "reference_id": {"type": ("VARCHAR",), "length": 32, "nullable": False},
                "source_message_id": {"type": ("VARCHAR",), "length": 100, "nullable": True},
                "citizen_id": {"type": ("INTEGER", "INT", "BIGINT"), "nullable": True},
                "whatsapp_citizen_id": {"type": ("INTEGER", "INT", "BIGINT"), "nullable": False},
                "category": {"type": ("VARCHAR",), "length": 80, "nullable": False},
                "event_date": {"nullable": False},
                "event_time": {"type": ("VARCHAR",), "length": 8, "nullable": False},
                "location_address": {"type": ("VARCHAR",), "length": 512, "nullable": False},
                "latitude": {"nullable": True},
                "longitude": {"nullable": True},
                "status": {"type": ("VARCHAR",), "length": 20, "nullable": False},
                "created_at": {"nullable": False},
            },
        },
        "foreign_keys": (
            {"table": "event_reports", "columns": ("citizen_id",), "referred_table": "users", "referred_columns": ("id",), "ondelete": "SET NULL"},
            {"table": "event_reports", "columns": ("whatsapp_citizen_id",), "referred_table": "whatsapp_citizens", "referred_columns": ("id",), "ondelete": "RESTRICT"},
        ),
        "indexes": (
            {"table": "event_reports", "columns": ("reference_id",), "name": "ix_event_reports_reference_id"},
            {"table": "event_reports", "columns": ("citizen_id",), "name": "ix_event_reports_citizen_id"},
            {"table": "event_reports", "columns": ("whatsapp_citizen_id",), "name": "ix_event_reports_whatsapp_citizen_id"},
        ),
    },
    "005": {
        "tables": ("mobile_otp_tokens",),
        "primary_keys": ({"table": "mobile_otp_tokens", "columns": ("id",)},),
        "columns": {
            "mobile_otp_tokens": {
                "phone": {"type": ("VARCHAR",), "length": 20, "nullable": False},
                "otp_hash": {"type": ("VARCHAR",), "length": 64, "nullable": False},
                "purpose": {
                    "type": ("VARCHAR",), "length": 20, "nullable": False,
                    "default_equals_any": ("'login'", "'login'::character varying"),
                },
                "ip_address": {"type": ("VARCHAR",), "length": 50, "nullable": True},
                "attempts": {"type": ("INTEGER", "INT"), "nullable": False, "default_equals_any": ("0",)},
                "max_attempts": {"type": ("INTEGER", "INT"), "nullable": False, "default_equals_any": ("5",)},
                "expires_at": {"type": ("TIMESTAMP", "DATETIME"), "nullable": False},
                "consumed_at": {"type": ("TIMESTAMP", "DATETIME"), "nullable": True},
                "created_at": {"type": ("TIMESTAMP", "DATETIME"), "nullable": False, "default_equals_any": ("CURRENT_TIMESTAMP", "now()")},
                "provider_message_id": {
                    "type": ("VARCHAR",),
                    "length": 100,
                    "nullable": True,
                },
                "delivery_status": {
                    "type": ("VARCHAR",),
                    "length": 30,
                    "nullable": True,
                    "default_equals_any": ("'PENDING'", "'PENDING'::character varying"),
                },
                "delivery_error_code": {
                    "type": ("VARCHAR",),
                    "length": 50,
                    "nullable": True,
                },
                "delivery_error_message": {
                    "type": ("VARCHAR",),
                    "length": 255,
                    "nullable": True,
                },
                "delivered_at": {"type": ("TIMESTAMP", "DATETIME"), "nullable": True},
                "updated_at": {"type": ("TIMESTAMP", "DATETIME"), "nullable": True, "default_equals_any": ("CURRENT_TIMESTAMP", "now()")},
            }
        },
        "indexes": (
            {
                "table": "mobile_otp_tokens",
                "columns": ("provider_message_id",),
                "name": "ix_mobile_otp_tokens_provider_message_id",
            },
            {
                "table": "mobile_otp_tokens",
                "columns": ("delivery_status",),
                "name": "ix_mobile_otp_tokens_delivery_status",
            },
        ),
    },
    "006": {
        "tables": ("whatsapp_registration_challenges",),
        "primary_keys": ({"table": "whatsapp_registration_challenges", "columns": ("id",)},),
        "columns": {
            "whatsapp_registration_challenges": {
                "id": {"type": ("INTEGER", "INT", "BIGINT")},
                "phone": {"type": ("VARCHAR",), "length": 20, "nullable": False},
                "otp_hash": {"type": ("VARCHAR",), "length": 64, "nullable": False},
                "secret_hash": {"type": ("VARCHAR",), "length": 64, "nullable": True},
                "purpose": {"type": ("VARCHAR",), "length": 50, "nullable": False, "default_equals_any": ("'citizen_registration'", "'citizen_registration'::character varying")},
                "profile_data": {"type": ("TEXT",), "nullable": True},
                "attempts": {"type": ("INTEGER", "INT"), "nullable": False, "default_equals_any": ("0",)},
                "max_attempts": {"type": ("INTEGER", "INT"), "nullable": False, "default_equals_any": ("5",)},
                "status": {"type": ("VARCHAR",), "length": 30, "nullable": False, "default_equals_any": ("'PENDING'", "'PENDING'::character varying")},
                "expires_at": {"type": ("TIMESTAMP", "DATETIME"), "nullable": False},
                "verified_at": {"type": ("TIMESTAMP", "DATETIME"), "nullable": True},
                "consumed_at": {"type": ("TIMESTAMP", "DATETIME"), "nullable": True},
                "ip_address": {"type": ("VARCHAR",), "length": 50, "nullable": True},
                "user_id": {"type": ("INTEGER", "INT", "BIGINT"), "nullable": True},
                "created_at": {"type": ("TIMESTAMP", "DATETIME"), "nullable": False, "default_equals_any": ("CURRENT_TIMESTAMP", "now()")},
                "updated_at": {"type": ("TIMESTAMP", "DATETIME"), "nullable": False, "default_equals_any": ("CURRENT_TIMESTAMP", "now()")},
            }
        },
        "foreign_keys": (
            {
                "table": "whatsapp_registration_challenges",
                "columns": ("user_id",),
                "referred_table": "users",
                "referred_columns": ("id",),
                "ondelete": "SET NULL",
            },
        ),
        "indexes": (
            {
                "table": "whatsapp_registration_challenges",
                "columns": ("phone",),
                "name": "ix_whatsapp_reg_challenges_phone",
            },
            {
                "table": "whatsapp_registration_challenges",
                "columns": ("status",),
                "name": "ix_whatsapp_reg_challenges_status",
            },
            {
                "table": "whatsapp_registration_challenges",
                "columns": ("created_at",),
                "name": "ix_whatsapp_reg_challenges_created_at",
            },
            {
                "table": "whatsapp_registration_challenges",
                "columns": ("user_id",),
                "name": "ix_whatsapp_reg_challenges_user_id",
            },
        ),
    },
    "007": {
        "tables": ("account_invitations", "security_audit_events"),
        "columns": {
            "users": {
                "is_verified": {"nullable": False},
                "is_super_admin": {"nullable": False},
                "session_version": {"nullable": False},
                "account_status": {"nullable": False},
            },
            "account_invitations": {
                "id": {"type": ("INTEGER", "INT", "BIGINT")},
                "user_id": {"nullable": False},
                "role": {"nullable": False},
                "token_hash": {"nullable": False},
                "expires_at": {"nullable": False},
            },
            "security_audit_events": {
                "id": {"type": ("INTEGER", "INT", "BIGINT")},
                "action": {"nullable": False},
                "created_at": {"nullable": False},
            },
        },
        "foreign_keys": (
            {
                "table": "account_invitations",
                "columns": ("user_id",),
                "referred_table": "users",
                "referred_columns": ("id",),
                "ondelete": "CASCADE",
            },
        ),
        "indexes": (
            {
                "table": "account_invitations",
                "columns": ("user_id",),
                "name": "ix_account_invitations_user_id",
            },
            {
                "table": "security_audit_events",
                "columns": ("actor_id",),
                "name": "ix_security_audit_events_actor_id",
            },
            {
                "table": "security_audit_events",
                "columns": ("target_user_id",),
                "name": "ix_security_audit_events_target_user_id",
            },
            {
                "table": "security_audit_events",
                "columns": ("action",),
                "name": "ix_security_audit_events_action",
            },
            {
                "table": "security_audit_events",
                "columns": ("created_at",),
                "name": "ix_security_audit_events_created_at",
            },
        ),
    },
    "008": {
        "tables": ("task_evidence", "task_events"),
        "columns": {
            "task_evidence": {
                "task_id": {"nullable": False}, "complaint_id": {"nullable": False},
                "driver_id": {"nullable": False}, "after_image_ref": {"nullable": False},
                "collected_at": {"nullable": False}, "status": {"nullable": False},
                "reviewed_by_id": {"nullable": True}, "rejection_reason": {"nullable": True},
            },
            "task_events": {
                "task_id": {"nullable": False}, "event_type": {"nullable": False},
                "from_status": {"nullable": True}, "to_status": {"nullable": True},
                "created_at": {"nullable": False},
            },
        },
        "foreign_keys": (
            {"table": "task_evidence", "columns": ("task_id",), "referred_table": "tasks", "referred_columns": ("id",), "ondelete": "RESTRICT"},
            {"table": "task_evidence", "columns": ("complaint_id",), "referred_table": "complaints", "referred_columns": ("id",), "ondelete": "RESTRICT"},
            {"table": "task_events", "columns": ("task_id",), "referred_table": "tasks", "referred_columns": ("id",), "ondelete": "RESTRICT"},
        ),
        "indexes": (
            {"table": "task_evidence", "columns": ("task_id",), "name": "ix_task_evidence_task_id"},
            {"table": "task_evidence", "columns": ("complaint_id",), "name": "ix_task_evidence_complaint_id"},
            {"table": "task_evidence", "columns": ("driver_id",), "name": "ix_task_evidence_driver_id"},
            {"table": "task_evidence", "columns": ("task_id", "created_at"), "name": "ix_task_evidence_task_created"},
            {"table": "task_events", "columns": ("task_id",), "name": "ix_task_events_task_id"},
            {"table": "task_events", "columns": ("task_id", "created_at"), "name": "ix_task_events_task_created"},
        ),
    },
    "009": {
        "columns": {
            "users": {
                "login_id": {"nullable": True, "type": "VARCHAR", "length": 50},
                "must_change_password": {
                    "nullable": False,
                    "type": ("BOOLEAN", "BOOL"),
                    "default_contains_any": ("false", "0"),
                },
            },
        },
        "indexes": (
            {
                "table": "users", "columns": ("login_id",),
                "name": "uq_users_login_id", "unique": True,
                "partial_predicate": "login_id IS NOT NULL AND login_id != ''",
                "partial_predicate_by_dialect": {
                    "sqlite": "login_id IS NOT NULL AND login_id != ''",
                },
            },
            {
                "table": "users", "columns": ("is_super_admin",),
                "name": "uq_users_single_super_admin", "unique": True,
                "partial_predicate": "is_super_admin",
                "partial_predicate_by_dialect": {"sqlite": "is_super_admin = 1"},
            },
        ),
    },
    "010": {
        "columns": {
            "users": {
                "temporary_password_expires_at": {
                    "nullable": True,
                    "type": ("TIMESTAMP", "TIMESTAMPTZ", "DATETIME"),
                },
                "mfa_enrollment_expires_at": {
                    "nullable": True,
                    "type": ("TIMESTAMP", "TIMESTAMPTZ", "DATETIME"),
                },
            },
        },
    },
}


class MigrationError(RuntimeError):
    """Raised when a migration cannot be applied safely."""


class PrerequisiteError(MigrationError):
    """Raised when the target database is not in an expected state."""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    sql: str
    checksum: str


def default_migrations_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations"


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def discover_migrations(directory: Optional[Path] = None) -> list[Migration]:
    directory = Path(directory) if directory is not None else default_migrations_dir()
    by_version: dict[str, Migration] = {}
    for path in sorted(directory.glob("*.sql")):
        stem = path.stem.lower()
        if any(marker in stem for marker in _EXCLUDED_STEM_MARKERS):
            continue
        match = _VERSION_RE.match(path.name)
        if not match:
            continue
        version = match.group(1)
        if version in by_version:
            raise PrerequisiteError(
                f"Duplicate migration version {version}: "
                f"{by_version[version].path.name} and {path.name}"
            )
        sql = path.read_text(encoding="utf-8")
        by_version[version] = Migration(
            version=version,
            name=match.group(2),
            path=path,
            sql=sql,
            checksum=_checksum(sql),
        )
    return [by_version[version] for version in sorted(by_version)]


def ensure_history_table(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} ("
                "version VARCHAR(20) PRIMARY KEY, "
                "name VARCHAR(255) NOT NULL, "
                "checksum VARCHAR(64) NOT NULL, "
                "method VARCHAR(20) NOT NULL DEFAULT 'applied', "
                "applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        )


def history_table_exists(engine) -> bool:
    return HISTORY_TABLE in inspect(engine).get_table_names()


def history_rows(engine) -> dict[str, dict]:
    """Read the migration history without creating anything (read-only)."""
    if not history_table_exists(engine):
        return {}
    with engine.connect() as connection:
        rows = connection.execute(
            text(f"SELECT version, name, checksum, method FROM {HISTORY_TABLE}")
        ).mappings().all()
    return {row["version"]: dict(row) for row in rows}


def applied_migrations(engine) -> dict[str, dict]:
    """Terminal history rows only; incomplete ('applying') rows are excluded."""
    return {
        version: row
        for version, row in history_rows(engine).items()
        if row["method"] != APPLYING_METHOD
    }


def plan(engine, migrations: Optional[Iterable[Migration]] = None) -> tuple[dict, list[Migration]]:
    migrations = list(migrations) if migrations is not None else discover_migrations()
    rows = history_rows(engine)

    incomplete = sorted(
        version for version, row in rows.items() if row["method"] == APPLYING_METHOD
    )
    if incomplete:
        raise MigrationError(
            f"Incomplete migration state for version(s) {incomplete}: the process stopped "
            "between intent and completion. Run `python -m server.scripts.migrate check` "
            "and reconcile explicitly before continuing."
        )
    applied = rows

    for migration in migrations:
        if migration.version in applied:
            record = applied[migration.version]
            if record["checksum"] != migration.checksum:
                raise MigrationError(
                    f"Checksum mismatch for {migration.version}_{migration.name}: "
                    "the file changed after it was recorded as applied."
                )

    known_versions = {migration.version for migration in migrations} | {BASELINE_VERSION}
    for version in applied:
        if version not in known_versions:
            logger.warning(
                "Migration history references %s but no migration file is present.", version
            )

    pending = [m for m in migrations if m.version not in applied]
    if pending and applied:
        newest_applied = max(int(version) for version in applied)
        for migration in pending:
            if int(migration.version) < newest_applied:
                raise MigrationError(
                    f"Out-of-order migration {migration.version}_{migration.name}: "
                    f"a newer version ({newest_applied:03d}) is already applied."
                )
    return applied, pending


@contextmanager
def migration_lock(engine):
    """Serialize migrations on PostgreSQL; no-op on SQLite.

    PostgreSQL uses a session-scoped advisory lock so two operators cannot apply
    migrations concurrently. The lock is non-blocking: the second process fails
    immediately instead of waiting. SQLite is single-writer and used only for
    development/tests, so no lock is taken there.
    """
    if engine.dialect.name != "postgresql":
        yield
        return

    connection = engine.raw_connection()
    cursor = None
    locked = False
    try:
        try:
            connection.autocommit = True
        except Exception:
            pass
        cursor = connection.cursor()
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        locked = bool(cursor.fetchone()[0])
        cursor.close()
        cursor = None
        if not locked:
            raise MigrationError(
                "Another migration process is running against this database "
                "(advisory lock is held)."
            )
        try:
            yield
        finally:
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))
                cursor.close()
                cursor = None
            except Exception:
                # Dropping the underlying session also releases its advisory lock.
                try:
                    connection.invalidate()
                except Exception:
                    pass
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        connection.close()


def _execute_script(engine, migration: Migration, *, record_inline: bool = False) -> bool:
    """Execute one migration script.

    Returns True when the history row was written inside the same PostgreSQL
    transaction as the DDL (atomic). Self-managed scripts and SQLite return False
    and are recorded by the caller.
    """
    connection = engine.raw_connection()
    try:
        if engine.dialect.name == "sqlite":
            # The later IAM/ward migrations use PostgreSQL-specific syntax.
            # Keep SQLite local bootstrap on the same ordered migration
            # contract, using equivalent transactional DDL/DML here.
            sqlite_handlers = {
                "009": _apply_sqlite_009,
                "010": _apply_sqlite_010,
                "011": _apply_sqlite_011,
                "012": _apply_sqlite_012,
            }
            handler = sqlite_handlers.get(migration.version)
            if handler is None:
                connection.executescript(migration.sql)
            else:
                cursor = connection.cursor()
                try:
                    cursor.execute("BEGIN IMMEDIATE")
                    handler(cursor)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    cursor.close()
            connection.commit()
            return False
        try:
            connection.autocommit = True
        except Exception:
            pass
        cursor = None
        managed_transaction = False
        try:
            cursor = connection.cursor()
            # Migration files that do not manage their own transaction are
            # wrapped so DDL + history commit atomically.
            managed_transaction = not _TRANSACTION_START_RE.search(migration.sql)
            if managed_transaction:
                cursor.execute("BEGIN")
            cursor.execute(migration.sql)
            if managed_transaction and record_inline:
                cursor.execute(
                    f"INSERT INTO {HISTORY_TABLE} (version, name, checksum, method) "
                    "VALUES (%s, %s, %s, %s)",
                    (migration.version, migration.name, migration.checksum, "applied"),
                )
            if managed_transaction:
                cursor.execute("COMMIT")
        except Exception as exc:  # noqa: BLE001 - surfaced as a clear migration error
            if managed_transaction and cursor is not None:
                try:
                    cursor.execute("ROLLBACK")
                except Exception:
                    pass
            raise MigrationError(
                f"Migration {migration.version}_{migration.name} failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        finally:
            if cursor is not None:
                cursor.close()
        return managed_transaction and record_inline
    finally:
        connection.close()


def _sqlite_columns(cursor, table: str) -> set[str]:
    return {row[1] for row in cursor.execute(f'PRAGMA table_info("{table}")')}


def _sqlite_add_column(cursor, table: str, column: str, definition: str) -> None:
    if column not in _sqlite_columns(cursor, table):
        cursor.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def _apply_sqlite_009(cursor) -> None:
    _sqlite_add_column(cursor, "users", "login_id", "VARCHAR(50)")
    _sqlite_add_column(
        cursor, "users", "must_change_password", "BOOLEAN NOT NULL DEFAULT 0"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_login_id ON users(login_id) "
        "WHERE login_id IS NOT NULL AND login_id <> ''"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_single_super_admin "
        "ON users(is_super_admin) WHERE is_super_admin = 1"
    )


def _apply_sqlite_010(cursor) -> None:
    _sqlite_add_column(cursor, "users", "temporary_password_expires_at", "DATETIME")
    _sqlite_add_column(cursor, "users", "mfa_enrollment_expires_at", "DATETIME")


def _apply_sqlite_011(cursor) -> None:
    # Use the ORM table definitions for the registry itself, but only create
    # missing tables. Existing user data and operational references stay put.
    from server.models.municipality import Municipality
    from server.models.ward import Ward
    from sqlalchemy.dialects import sqlite
    from sqlalchemy.schema import CreateIndex, CreateTable

    existing_tables = {
        row[0]
        for row in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    existing_indexes = {
        row[0]
        for row in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    }
    for table in (Municipality.__table__, Ward.__table__):
        if table.name not in existing_tables:
            cursor.execute(str(CreateTable(table).compile(dialect=sqlite.dialect())))
        for index in table.indexes:
            if index.name not in existing_indexes:
                cursor.execute(str(CreateIndex(index).compile(dialect=sqlite.dialect())))
    _sqlite_add_column(
        cursor, "users", "municipality_id",
        "INTEGER REFERENCES municipalities(id) ON DELETE RESTRICT",
    )
    _sqlite_add_column(
        cursor, "users", "ward_id", "INTEGER REFERENCES wards(id) ON DELETE RESTRICT"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_municipality_id ON users(municipality_id)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_ward_id ON users(ward_id)")
    cursor.execute(
        "INSERT INTO municipalities (code, name) VALUES ('DHULE', 'Dhule') "
        "ON CONFLICT(code) DO NOTHING"
    )
    municipality_id = cursor.execute(
        "SELECT id FROM municipalities WHERE code = 'DHULE'"
    ).fetchone()[0]
    for number in range(1, 20):
        value = str(number)
        cursor.execute(
            "INSERT INTO wards (municipality_id, ward_number, display_name) "
            "VALUES (?, ?, ?) ON CONFLICT(municipality_id, ward_number) DO NOTHING",
            (municipality_id, value, f"Ward {number}"),
        )
    cursor.execute(
        "UPDATE users SET ward_id = ("
        "SELECT w.id FROM wards AS w WHERE w.municipality_id = ? "
        "AND lower(trim(w.display_name)) = lower(trim(users.ward)) LIMIT 1), "
        "municipality_id = ? WHERE ward_id IS NULL "
        "AND (municipality_id IS NULL OR municipality_id = ?) "
        "AND EXISTS (SELECT 1 FROM wards AS w WHERE w.municipality_id = ? "
        "AND lower(trim(w.display_name)) = lower(trim(users.ward)))",
        (municipality_id, municipality_id, municipality_id, municipality_id),
    )


def _apply_sqlite_012(cursor) -> None:
    from server.models.event_report import EventReport
    from sqlalchemy.dialects import sqlite
    from sqlalchemy.schema import CreateIndex, CreateTable

    table = EventReport.__table__
    exists = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table.name,),
    ).fetchone()
    if not exists:
        cursor.execute(str(CreateTable(table).compile(dialect=sqlite.dialect())))
    existing_indexes = {
        row[0]
        for row in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    }
    for index in table.indexes:
        if index.name not in existing_indexes:
            cursor.execute(str(CreateIndex(index).compile(dialect=sqlite.dialect())))


def _record(engine, migration: Migration, method: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO {HISTORY_TABLE} (version, name, checksum, method) "
                "VALUES (:version, :name, :checksum, :method)"
            ),
            {
                "version": migration.version,
                "name": migration.name,
                "checksum": migration.checksum,
                "method": method,
            },
        )


def _finalize_record(engine, migration: Migration, method: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f"UPDATE {HISTORY_TABLE} SET name = :name, checksum = :checksum, "
                "method = :method, applied_at = CURRENT_TIMESTAMP WHERE version = :version"
            ),
            {
                "version": migration.version,
                "name": migration.name,
                "checksum": migration.checksum,
                "method": method,
            },
        )


def _delete_record(engine, version: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(f"DELETE FROM {HISTORY_TABLE} WHERE version = :version"),
            {"version": version},
        )


def _application_tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {HISTORY_TABLE}


def apply_pending(
    engine,
    migrations: Optional[Iterable[Migration]] = None,
    *,
    dry_run: bool = False,
) -> list[str]:
    migrations = list(migrations) if migrations is not None else discover_migrations()
    applied, pending = plan(engine, migrations)

    if pending and not applied and _application_tables(engine):
        raise PrerequisiteError(
            "The target database already contains tables but has no migration "
            "history. Run `adopt` first so the existing schema is recognized "
            "instead of mutated blindly."
        )

    if not pending:
        logger.info("No pending migrations.")
        return []

    if dry_run:
        for migration in pending:
            logger.info("[DRY RUN] would apply %s_%s", migration.version, migration.name)
        return [migration.version for migration in pending]

    applied_versions: list[str] = []
    with migration_lock(engine):
        ensure_history_table(engine)
        # Re-plan under the lock: another operator may have applied migrations
        # between the first plan and lock acquisition.
        applied, pending = plan(engine, migrations)
        if not pending:
            logger.info("No pending migrations (already applied).")
            return []
        for migration in pending:
            logger.info("Applying migration %s_%s", migration.version, migration.name)
            managed = not _TRANSACTION_START_RE.search(migration.sql)
            inline_capable = managed and engine.dialect.name == "postgresql"
            if not inline_capable:
                # Intent marker: if the process dies mid-script, the version is
                # left incomplete and blocks automatic re-execution.
                _record(engine, migration, method=APPLYING_METHOD)
            try:
                _execute_script(engine, migration, record_inline=inline_capable)
            except Exception:
                if not inline_capable:
                    # The file's own transaction rolled back; drop the marker so
                    # a corrected re-run is possible after inspection.
                    _delete_record(engine, migration.version)
                raise
            if not inline_capable:
                _finalize_record(engine, migration, method="applied")
            applied_versions.append(migration.version)
            logger.info("Applied migration %s_%s", migration.version, migration.name)
    return applied_versions


def _inspect_foreign_keys(engine, inspector, table: str) -> list[dict]:
    fks = inspector.get_foreign_keys(table)
    if engine.dialect.name == "sqlite":
        try:
            with engine.connect() as conn:
                p_rows = conn.execute(text(f"PRAGMA foreign_key_list({table})")).fetchall()
                for fk in fks:
                    if not (fk.get("options") or {}).get("ondelete"):
                        for pr in p_rows:
                            if pr[2] == fk.get("referred_table") and [pr[3]] == fk.get("constrained_columns"):
                                fk.setdefault("options", {})["ondelete"] = str(pr[6]).upper()
        except Exception:
            pass
    return fks


def _normalize_predicate(predicate: str) -> str:
    """Normalize a partial-index predicate for dialect-agnostic comparison.

    PostgreSQL stores predicates with extra parentheses and type casts, e.g.:
        ``((phone IS NOT NULL) AND ((phone)::text <> ''::text))``
    while migrations are written as:
        ``phone IS NOT NULL AND phone != ''``

    This function strips PostgreSQL type casts, normalises ``<>`` to ``!=``,
    removes only redundant parentheses around atoms or the whole expression,
    then upper-cases and collapses whitespace. Parentheses around boolean
    groups remain significant, so precedence changes cannot compare equal.
    """
    def quoted_end(value: str, start: int) -> int:
        quote = value[start]
        pos = start + 1
        while pos < len(value):
            if value[pos] == quote:
                if pos + 1 < len(value) and value[pos + 1] == quote:
                    pos += 2
                    continue
                return pos + 1
            pos += 1
        return len(value)

    def parenthesis_pairs(value: str) -> list[tuple[int, int]]:
        stack: list[int] = []
        pairs: list[tuple[int, int]] = []
        pos = 0
        while pos < len(value):
            if value[pos] in "'\"":
                pos = quoted_end(value, pos)
                continue
            if value[pos] == "(":
                stack.append(pos)
            elif value[pos] == ")" and stack:
                pairs.append((stack.pop(), pos))
            pos += 1
        return pairs

    def has_boolean_connector(value: str) -> bool:
        pos = 0
        while pos < len(value):
            if value[pos] in "'\"":
                pos = quoted_end(value, pos)
                continue
            if value[pos].isalpha() or value[pos] == "_":
                end = pos + 1
                while end < len(value) and (value[end].isalnum() or value[end] == "_"):
                    end += 1
                if value[pos:end].upper() in {"AND", "OR"}:
                    return True
                pos = end
                continue
            pos += 1
        return False

    p = predicate.strip()
    # PostgreSQL may render varchar comparisons as ::text. Remove that known
    # harmless coercion outside quoted strings only; other casts and literal
    # contents can change semantics and must remain part of the comparison.
    p_without_text_casts: list[str] = []
    pos = 0
    while pos < len(p):
        if p[pos] in "'\"":
            end = quoted_end(p, pos)
            p_without_text_casts.append(p[pos:end])
            pos = end
            continue
        if p[pos:pos + 6].lower() == "::text" and (
            pos + 6 == len(p) or not (p[pos + 6].isalnum() or p[pos + 6] == "_")
        ):
            pos += 6
            continue
        p_without_text_casts.append(p[pos])
        pos += 1
    p = "".join(p_without_text_casts)

    # Remove parenthetical atom wrappers, but preserve groups containing
    # boolean connectors. This keeps operator precedence significant.
    while True:
        removable = next(
            (
                (start, end)
                for start, end in parenthesis_pairs(p)
                if not has_boolean_connector(p[start + 1:end])
            ),
            None,
        )
        if removable is None:
            break
        start, end = removable
        p = p[:start] + p[start + 1:end] + p[end + 1:]

    # One pair wrapping the complete expression does not alter precedence.
    while True:
        pairs = parenthesis_pairs(p)
        if not pairs or pairs[-1] != (0, len(p) - 1):
            break
        p = p[1:-1].strip()

    # Canonicalize only unquoted SQL text. Literal and quoted-identifier case,
    # spacing, and punctuation remain exact.
    normalized: list[str] = []
    pos = 0
    while pos < len(p):
        if p[pos] in "'\"":
            end = quoted_end(p, pos)
            normalized.append(p[pos:end])
            pos = end
        elif p[pos:pos + 2] == "<>":
            normalized.append("!=")
            pos += 2
        elif p[pos].isspace():
            if not normalized or normalized[-1] != " ":
                normalized.append(" ")
            pos += 1
        else:
            normalized.append(p[pos].upper())
            pos += 1
    return "".join(normalized).strip()


def _inspect_index_definitions(engine, table: str) -> dict[str, dict]:
    """Return a mapping of index name -> rich info dict for *table*.

    Each value is::

        {
            "sql": str,           # raw DDL string from the catalog
            "is_unique": bool,
            "predicate": str,     # text after WHERE (empty string if none)
        }

    Supports SQLite (via ``sqlite_master``) and PostgreSQL (via ``pg_index``
    and its catalog relations, including validity and readiness flags).
    """
    defs: dict[str, dict] = {}
    if engine.dialect.name == "sqlite":
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = :tbl"),
                    {"tbl": table},
                ).fetchall()
                for r in rows:
                    sql = r[1] or ""
                    is_unique = bool(re.search(r"\bUNIQUE\b", sql, re.IGNORECASE))
                    # Extract predicate: everything after the first WHERE keyword
                    where_match = re.search(r"\bWHERE\b(.*)", sql, re.IGNORECASE | re.DOTALL)
                    predicate = where_match.group(1).strip() if where_match else ""
                    defs[r[0]] = {"sql": sql, "is_unique": is_unique, "predicate": predicate}
        except Exception:
            pass
    elif engine.dialect.name == "postgresql":
        # Do not suppress catalog errors: inability to inspect a required
        # PostgreSQL index must abort adoption rather than look like success.
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT idx.relname, pg_get_indexdef(ix.indexrelid), "
                "       ix.indisunique, ix.indisvalid, ix.indisready, "
                "       pg_get_expr(ix.indpred, ix.indrelid), "
                "       ARRAY(SELECT CASE WHEN k.attnum = 0 THEN NULL::text "
                "                          ELSE a.attname::text END "
                "             FROM unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ord) "
                "             LEFT JOIN pg_attribute a "
                "               ON a.attrelid = tbl.oid AND a.attnum = k.attnum "
                "             WHERE k.ord <= ix.indnkeyatts ORDER BY k.ord), "
                "       ARRAY(SELECT a.attname::text "
                "             FROM unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ord) "
                "             JOIN pg_attribute a "
                "               ON a.attrelid = tbl.oid AND a.attnum = k.attnum "
                "             WHERE k.ord > ix.indnkeyatts AND k.ord <= ix.indnatts "
                "             ORDER BY k.ord) "
                "FROM pg_class tbl "
                "JOIN pg_namespace ns ON ns.oid = tbl.relnamespace "
                "JOIN pg_index ix ON ix.indrelid = tbl.oid "
                "JOIN pg_class idx ON idx.oid = ix.indexrelid "
                "WHERE tbl.relname = :tbl "
                "  AND ns.nspname = current_schema() "
                "  AND ns.nspname NOT IN ('pg_catalog', 'information_schema') "
                "  AND tbl.relkind IN ('r', 'p') "
                "  AND idx.relnamespace = ns.oid"
            ), {"tbl": table}).fetchall()
            for r in rows:
                defs[r[0]] = {
                    "sql": r[1] or "",
                    "is_unique": bool(r[2]),
                    "is_valid": bool(r[3]),
                    "is_ready": bool(r[4]),
                    "predicate": r[5] or "",
                    # indnkeyatts counts key attributes only; any attnum=0
                    # remains None and therefore cannot masquerade as a column.
                    "columns": list(r[6] or []),
                    "included_columns": list(r[7] or []),
                }
    return defs


def _missing_objects(engine, version: str) -> list[str]:
    spec = SENTINELS.get(version)
    if not spec:
        return []
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing: list[str] = []

    # 1. Table presence
    for table in spec.get("tables", ()):  # type: ignore[arg-type]
        if table not in tables:
            missing.append(f"table {table}")

    # 1b. Primary keys
    for pk_req in spec.get("primary_keys", ()):
        table = pk_req["table"]
        if table not in tables:
            continue
        actual_pk = inspect(engine).get_pk_constraint(table).get("constrained_columns") or []
        if actual_pk != list(pk_req["columns"]):
            missing.append(
                f"primary key on {table} mismatch (expected {list(pk_req['columns'])}, found {actual_pk})"
            )

    # 2. Columns, types, nullability, defaults
    for table, columns in spec.get("columns", {}).items():  # type: ignore[union-attr]
        if table not in tables:
            continue
        existing = {column["name"]: column for column in inspector.get_columns(table)}
        if isinstance(columns, (list, tuple)):
            for column in columns:
                if column not in existing:
                    missing.append(f"{table}.{column}")
            continue

        for col_name, rules in columns.items():
            if col_name not in existing:
                missing.append(f"{table}.{col_name}")
                continue
            col_info = existing[col_name]
            if "nullable" in rules:
                expected_nullable = rules["nullable"]
                actual_nullable = col_info.get("nullable")
                if actual_nullable is not None and actual_nullable != expected_nullable:
                    exp_str = "nullable" if expected_nullable else "NOT NULL"
                    act_str = "nullable" if actual_nullable else "NOT NULL"
                    missing.append(
                        f"{table}.{col_name} nullability mismatch (expected {exp_str}, found {act_str})"
                    )
            if "type" in rules:
                allowed_types = rules["type"]
                if isinstance(allowed_types, str):
                    allowed_types = (allowed_types,)
                actual_type = str(col_info.get("type", "")).upper()
                if not any(actual_type.startswith(t.upper()) for t in allowed_types):
                    missing.append(
                        f"{table}.{col_name} type mismatch (expected {allowed_types}, found {actual_type})"
                    )
            if "length" in rules:
                expected_len = rules["length"]
                col_t = col_info.get("type")
                actual_len = getattr(col_t, "length", None)
                # SQLite does not support ALTER COLUMN TYPE; VARCHAR length
                # is advisory there, so migration 011's ward widening is
                # represented by the PostgreSQL schema contract only.
                sqlite_unenforced_length = (
                    engine.dialect.name == "sqlite"
                    and table == "users"
                    and col_name == "ward"
                )
                if (
                    not sqlite_unenforced_length
                    and actual_len is not None
                    and actual_len != expected_len
                ):
                    missing.append(
                        f"{table}.{col_name} length mismatch (expected {expected_len}, found {actual_len})"
                    )
            if "default_contains" in rules:
                expected_def = rules["default_contains"]
                actual_def = str(col_info.get("default") or "")
                if expected_def.lower() not in actual_def.lower():
                    missing.append(
                        f"{table}.{col_name} default mismatch (expected to contain '{expected_def}', found '{actual_def}')"
                    )
            if "default_contains_any" in rules:
                expected_defs = rules["default_contains_any"]
                actual_def = str(col_info.get("default") or "")
                if not any(value.lower() in actual_def.lower() for value in expected_defs):
                    missing.append(
                        f"{table}.{col_name} default mismatch (expected one of {expected_defs}, found '{actual_def}')"
                    )
            if "default_equals_any" in rules:
                expected_defs = rules["default_equals_any"]

                def normalize_default(value: str) -> str:
                    value = value.strip().lower()
                    value = re.sub(r"::[a-z_ ]+$", "", value)
                    while value.startswith("(") and value.endswith(")"):
                        value = value[1:-1].strip()
                    return value

                actual_def = str(col_info.get("default") or "")
                if normalize_default(actual_def) not in {normalize_default(str(value)) for value in expected_defs}:
                    missing.append(
                        f"{table}.{col_name} default mismatch (expected one of {expected_defs}, found '{actual_def}')"
                    )

    # 3. Foreign keys
    for fk_req in spec.get("foreign_keys", ()):
        table = fk_req["table"]
        if table not in tables:
            continue
        req_cols = list(fk_req["columns"])
        ref_table = fk_req["referred_table"]
        ref_cols = list(fk_req.get("referred_columns", ("id",)))
        req_ondelete = fk_req.get("ondelete")

        fks = _inspect_foreign_keys(engine, inspector, table)
        matched_fk = None
        for fk in fks:
            if (
                fk.get("constrained_columns") == req_cols
                and fk.get("referred_table") == ref_table
                and (not ref_cols or fk.get("referred_columns") == ref_cols)
            ):
                matched_fk = fk
                break

        if not matched_fk:
            missing.append(
                f"foreign key {table}({', '.join(req_cols)}) -> {ref_table}({', '.join(ref_cols)})"
            )
            continue

        if req_ondelete:
            actual_ondelete = (matched_fk.get("options") or {}).get("ondelete")
            if actual_ondelete:
                actual_ondelete = str(actual_ondelete).upper()
            if actual_ondelete != req_ondelete.upper():
                missing.append(
                    f"foreign key {table}({', '.join(req_cols)}) ondelete mismatch (expected {req_ondelete}, found {actual_ondelete})"
                )

    # 4. Indexes and unique constraints
    for idx_req in spec.get("indexes", ()):
        table = idx_req["table"]
        if table not in tables:
            continue
        req_cols = list(idx_req["columns"])
        req_name = idx_req.get("name")
        req_unique = idx_req.get("unique")
        req_predicate = (idx_req.get("partial_predicate_by_dialect") or {}).get(
            engine.dialect.name, idx_req.get("partial_predicate")
        )

        indexes = inspector.get_indexes(table)
        unique_constraints = inspector.get_unique_constraints(table)

        matched_idx = None
        # When a specific index name is required, match by name first so two
        # indexes on the same column don't shadow each other (e.g. the regular
        # ix_whatsapp_citizens_user_id must not be matched instead of the
        # partial unique uq_whatsapp_citizens_user_id_notnull).
        if req_name:
            for idx in indexes:
                if idx.get("name") == req_name:
                    matched_idx = idx
                    break
            if not matched_idx:
                for uc in unique_constraints:
                    if uc.get("name") == req_name and uc.get("column_names") == req_cols:
                        matched_idx = {
                            "name": uc.get("name"),
                            "column_names": req_cols,
                            "unique": True,
                        }
                        break
        if not matched_idx:
            for idx in indexes:
                idx_cols = idx.get("column_names") or []
                if idx_cols == req_cols and not req_name:
                    matched_idx = idx
                    break

        if not matched_idx and req_unique and not req_name:
            for uc in unique_constraints:
                if uc.get("column_names") == req_cols:
                    matched_idx = {
                        "name": uc.get("name"),
                        "column_names": req_cols,
                        "unique": True,
                    }
                    break

        if not matched_idx:
            missing.append(f"index on {table}({', '.join(req_cols)})")
            continue

        idx_name = matched_idx.get("name")
        idx_defs = _inspect_index_definitions(engine, table)
        idx_info = idx_defs.get(idx_name) if idx_name else None
        actual_cols = (idx_info or {}).get("columns") or matched_idx.get("column_names") or []
        if actual_cols != req_cols:
            missing.append(
                f"index '{idx_name}' columns mismatch (expected {req_cols}, found {actual_cols})"
            )
        if engine.dialect.name == "postgresql":
            if idx_info is None:
                missing.append(
                    f"index '{idx_name}' catalog definition could not be verified"
                )
            elif not idx_info.get("is_valid") or not idx_info.get("is_ready"):
                missing.append(
                    f"index '{idx_name}' is invalid or not ready "
                    f"(valid={idx_info.get('is_valid')}, ready={idx_info.get('is_ready')})"
                )

        if req_unique is not None:
            is_unique = bool(matched_idx.get("unique"))
            if engine.dialect.name == "postgresql" and idx_info is not None:
                is_unique = bool(idx_info.get("is_unique"))
            if is_unique != req_unique:
                missing.append(
                    f"index on {table}({', '.join(req_cols)}) uniqueness mismatch (expected unique={req_unique}, found {is_unique})"
                )

        if req_predicate:
            if idx_info is None:
                # Index exists via inspector but we cannot retrieve its DDL — treat as missing predicate.
                missing.append(
                    f"index '{idx_name}' predicate could not be verified (no DDL found)"
                )
            else:
                actual_pred = idx_info.get("predicate", "")
                if not actual_pred:
                    missing.append(
                        f"index '{idx_name}' is not a partial index "
                        f"(expected predicate: '{req_predicate}')"
                    )
                elif _normalize_predicate(actual_pred) != _normalize_predicate(req_predicate):
                    missing.append(
                        f"index '{idx_name}' predicate mismatch: "
                        f"expected '{req_predicate}', "
                        f"found '{actual_pred}'"
                    )

    return missing


def adopt_existing(
    engine,
    migrations: Optional[Iterable[Migration]] = None,
    *,
    through_version: str,
    verify: bool = True,
) -> list[str]:
    """Record an existing schema as applied without running any DDL."""
    migrations = list(migrations) if migrations is not None else discover_migrations()
    through = int(through_version)

    with migration_lock(engine):
        ensure_history_table(engine)
        rows = history_rows(engine)
        incomplete = sorted(
            version for version, row in rows.items() if row["method"] == APPLYING_METHOD
        )
        if incomplete:
            raise PrerequisiteError(
                f"Cannot adopt while version(s) {incomplete} are incomplete. Run `check` "
                "and reconcile them first."
            )
        tables = set(inspect(engine).get_table_names())
        missing_base = sorted(BASE_SCHEMA_TABLES - tables)
        if missing_base:
            raise PrerequisiteError(
                "Cannot adopt: base schema tables are missing "
                f"({missing_base}). Use development initialization for an empty database."
            )

        applied = applied_migrations(engine)
        to_adopt: list[Migration] = []
        for migration in migrations:
            if int(migration.version) > through or migration.version in applied:
                continue
            if verify:
                missing = _missing_objects(engine, migration.version)
            else:
                missing = []
            if missing:
                raise PrerequisiteError(
                    f"Cannot adopt {migration.version}_{migration.name}; expected "
                    f"objects are missing ({missing}). Apply it explicitly instead."
                )
            to_adopt.append(migration)

        # Validate the complete requested range before writing any history rows.
        # Commit the baseline and migration records together so a failed
        # adoption cannot leave a misleading partially-adopted history.
        recorded: list[str] = []
        with engine.begin() as connection:
            if BASELINE_VERSION not in applied:
                connection.execute(
                    text(
                        f"INSERT INTO {HISTORY_TABLE} (version, name, checksum, method) "
                        "VALUES (:version, 'baseline', '', 'adopted')"
                    ),
                    {"version": BASELINE_VERSION},
                )
                recorded.append(BASELINE_VERSION)
            for migration in to_adopt:
                connection.execute(
                    text(
                        f"INSERT INTO {HISTORY_TABLE} (version, name, checksum, method) "
                        "VALUES (:version, :name, :checksum, 'adopted')"
                    ),
                    {
                        "version": migration.version,
                        "name": migration.name,
                        "checksum": migration.checksum,
                    },
                )
                recorded.append(migration.version)

        logger.info(
            "Adopted existing schema through %s: %s",
            through_version,
            recorded or "already current",
        )
    return recorded


def status(engine, migrations: Optional[Iterable[Migration]] = None) -> dict:
    """Read-only migration status. Never creates or modifies the history table."""
    migrations = list(migrations) if migrations is not None else discover_migrations()
    initialized = history_table_exists(engine)
    rows = history_rows(engine)
    applied = {
        version: row for version, row in rows.items() if row["method"] != APPLYING_METHOD
    }
    in_progress = sorted(
        version for version, row in rows.items() if row["method"] == APPLYING_METHOD
    )
    pending = [m for m in migrations if m.version not in applied]
    return {
        "initialized": initialized,
        "baseline": BASELINE_VERSION in applied,
        "applied": sorted(applied.keys()),
        "in_progress": in_progress,
        "pending": [f"{m.version}_{m.name}" for m in pending],
    }


@dataclass(frozen=True)
class MigrationIssue:
    code: str
    detail: str
    version: Optional[str] = None


def diagnose(
    engine, migrations: Optional[Iterable[Migration]] = None
) -> list[MigrationIssue]:
    """Read-only diagnostic covering every state the runner can encounter."""
    migrations = list(migrations) if migrations is not None else discover_migrations()
    known = {migration.version: migration for migration in migrations}
    tables = set(inspect(engine).get_table_names())
    app_tables = tables - {HISTORY_TABLE}
    initialized = HISTORY_TABLE in tables
    issues: list[MigrationIssue] = []

    if not initialized:
        if app_tables:
            issues.append(
                MigrationIssue(
                    "uninitialized_existing_schema",
                    "Schema tables exist but schema_migrations is missing; run `adopt` "
                    "after review so the existing schema is recognized.",
                )
            )
        else:
            issues.append(
                MigrationIssue(
                    "uninitialized_empty_schema",
                    "Database is empty and has no migration history; provision it "
                    "deliberately or use development initialization.",
                )
            )
        return issues

    rows = history_rows(engine)
    applied = {}
    for version, row in rows.items():
        if row["method"] == APPLYING_METHOD:
            issues.append(
                MigrationIssue(
                    "incomplete_application",
                    "Migration started but was not finalized; verify the schema and "
                    "reconcile explicitly.",
                    version,
                )
            )
            continue
        applied[version] = row
        if version == BASELINE_VERSION:
            missing_base = sorted(BASE_SCHEMA_TABLES - tables)
            if missing_base:
                issues.append(
                    MigrationIssue(
                        "applied_but_missing",
                        f"Baseline is recorded but base tables are missing: {missing_base}.",
                        version,
                    )
                )
        elif version not in known:
            issues.append(
                MigrationIssue(
                    "unknown_version",
                    "History references a version with no migration file.",
                    version,
                )
            )
        else:
            migration = known[version]
            if row["checksum"] != migration.checksum:
                issues.append(
                    MigrationIssue(
                        "checksum_mismatch",
                        "Recorded checksum differs from the migration file; the file "
                        "changed after it was applied.",
                        version,
                    )
                )
            missing = _missing_objects(engine, version)
            if missing:
                issues.append(
                    MigrationIssue(
                        "applied_but_missing",
                        f"Recorded as {row['method']} but objects are missing: {missing}.",
                        version,
                    )
                )

    pending = [migration for migration in migrations if migration.version not in applied]
    if pending:
        missing_base = sorted(BASE_SCHEMA_TABLES - tables)
        if missing_base:
            issues.append(
                MigrationIssue(
                    "missing_base_schema",
                    "Pending migrations require base tables that do not exist: "
                    f"{missing_base}.",
                )
            )
        for migration in pending:
            if SENTINELS.get(migration.version) and not _missing_objects(
                engine, migration.version
            ):
                issues.append(
                    MigrationIssue(
                        "present_but_unrecorded",
                        "Expected objects already exist but the version is not recorded; "
                        "this is the crash window—reconcile only after review.",
                        migration.version,
                    )
                )
        if applied:
            newest_applied = max(int(version) for version in applied)
            for migration in pending:
                if int(migration.version) < newest_applied:
                    issues.append(
                        MigrationIssue(
                            "out_of_order",
                            f"Pending version is older than applied version "
                            f"{newest_applied:03d}.",
                            migration.version,
                        )
                    )
    return issues


def reconcile(
    engine,
    migrations: Optional[Iterable[Migration]] = None,
    *,
    record_version: Optional[str] = None,
    clear_version: Optional[str] = None,
) -> dict:
    """Apply one explicit, operator-approved reconciliation action.

    Recording is only allowed when every sentinel object for the version exists.
    Clearing is only allowed for an incomplete marker whose sentinels are all
    absent. No reconciliation ever happens automatically.
    """
    migrations = list(migrations) if migrations is not None else discover_migrations()
    known = {migration.version: migration for migration in migrations}

    with migration_lock(engine):
        ensure_history_table(engine)
        rows = history_rows(engine)

        if record_version:
            migration = known.get(record_version)
            if migration is None:
                raise PrerequisiteError(f"Unknown migration version {record_version}.")
            row = rows.get(record_version)
            if row and row["method"] == APPLYING_METHOD:
                pass
            elif row:
                raise PrerequisiteError(
                    f"Version {record_version} is already recorded as {row['method']}."
                )
            if not SENTINELS.get(record_version):
                raise PrerequisiteError(
                    f"Version {record_version} has no verification rules; reconcile manually."
                )
            missing = _missing_objects(engine, record_version)
            if missing:
                raise PrerequisiteError(
                    f"Cannot record {record_version}; expected objects are missing ({missing})."
                )
            if row:
                _finalize_record(engine, migration, method="reconciled")
            else:
                _record(engine, migration, method="reconciled")
            return {"recorded": record_version}

        if clear_version:
            row = rows.get(clear_version)
            if not row or row["method"] != APPLYING_METHOD:
                raise PrerequisiteError(
                    f"Version {clear_version} is not in an incomplete state."
                )
            if not SENTINELS.get(clear_version):
                raise PrerequisiteError(
                    f"Version {clear_version} has no verification rules; reconcile manually."
                )
            if not _missing_objects(engine, clear_version):
                raise PrerequisiteError(
                    f"Cannot clear {clear_version}; expected objects exist—record it instead."
                )
            _delete_record(engine, clear_version)
            return {"cleared": clear_version}

        raise PrerequisiteError("Specify --record VERSION or --clear VERSION.")
