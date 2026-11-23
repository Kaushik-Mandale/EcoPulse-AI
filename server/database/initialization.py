"""Database schema initialization policy.

Production startup is verification-only: it must never execute DDL. Development
and test initialization may create or patch the schema from the ORM models.

Schema ownership (canonical):
- Empty non-production databases: SQLAlchemy models create a fresh current schema.
- Existing non-production databases: verify/adopt the frozen legacy baseline,
  then run ordered pending migrations before ORM queries use new columns.
- Production: verify_required_schema() only; fail fast on missing objects.

See server/database/migrations_runner.py for the explicit migration runner.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import inspect
from server.database.target_policy import validate_development_target

logger = logging.getLogger(__name__)

# Only these environments may mutate schema during application initialization.
MUTATION_ALLOWED_ENVIRONMENTS = frozenset(
    {"development", "dev", "local", "test", "testing"}
)

# Tables the application requires. Mirrors server/models/__init__.py.
REQUIRED_TABLES = frozenset(
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
        "whatsapp_link_tokens",
        "mobile_otp_tokens",
        "whatsapp_registration_challenges",
        "account_invitations",
        "security_audit_events",
        "task_evidence",
        "task_events",
        "municipalities",
        "wards",
        "event_reports",
    }
)

# Security-sensitive columns required by the IAM and staff onboarding migrations.
REQUIRED_USER_COLUMNS = frozenset(
    {
        "login_id",
        "must_change_password",
        "temporary_password_expires_at",
        "mfa_enrollment_expires_at",
        "is_verified",
        "is_super_admin",
        "mfa_secret_enc",
        "mfa_enabled",
        "mfa_last_verified_step",
        "session_version",
        "account_status",
        "vehicle_assignment",
        "created_by_id",
        "approved_by_id",
        "verified_at",
        "activated_at",
        "suspended_at",
        "deactivated_at",
        "mfa_enrolled_at",
        "municipality_id",
        "ward_id",
    }
)


class SchemaValidationError(RuntimeError):
    """Raised when a production database is missing required schema objects."""


# Tables whose integer primary-key sequence may need resynchronising after a
# development import or manual seed. PostgreSQL-only.
IDENTIFIER_SEQUENCE_TABLES = (
    "tasks",
    "complaints",
    "users",
    "items",
    "notifications",
    "fuel_logs",
    "whatsapp_citizens",
    "whatsapp_processed_messages",
)


def normalize_environment(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def schema_mutation_allowed(env: Optional[str]) -> bool:
    return normalize_environment(env) in MUTATION_ALLOWED_ENVIRONMENTS


def verify_migration_contracts(engine, versions=("005", "006", "007", "008", "009", "010", "011", "012")) -> bool:
    """Raise on an incomplete contract or inspection failure; never fail open."""
    try:
        from server.database.migrations_runner import _missing_objects

        issues = {version: _missing_objects(engine, version) for version in versions}
    except Exception as exc:
        raise SchemaValidationError(
            f"Database schema inspection failed closed ({type(exc).__name__})."
        ) from exc
    issues = {version: missing for version, missing in issues.items() if missing}
    if issues:
        raise SchemaValidationError(f"Database schema is incompatible with migration contracts: {issues}.")
    return True


def _create_base_schema(engine, env: Optional[str] = None) -> None:
    """Create a truly empty local schema; migrate verified existing schemas."""
    # Validate the resolved target before importing/calling any DDL helper. This
    # is deliberately repeated by direct compatibility-helper entry points too.
    validate_development_target(engine, env)
    import server.models  # noqa: F401 - register every table on Base.metadata
    from server.database.db import (
        Base,
    )

    from server.database.migrations_runner import (
        HISTORY_TABLE,
        adopt_existing,
        apply_pending,
        discover_migrations,
        history_table_exists,
    )

    tables = set(inspect(engine).get_table_names())
    application_tables = tables - {HISTORY_TABLE}
    if not application_tables:
        # create_all is supported only for an empty disposable database.
        Base.metadata.create_all(bind=engine)
        _ensure_initial_ward_registry(engine)
        migrations = discover_migrations()
        if migrations:
            adopt_existing(engine, migrations, through_version=migrations[-1].version)
        logger.info("[SCHEMA] Fresh non-production ORM schema initialized.")
        return

    migrations = discover_migrations()
    if not history_table_exists(engine):
        # Existing schemas must prove the frozen legacy baseline before any
        # migration runs. In particular, never use create_all to patch them.
        adopt_existing(engine, migrations, through_version="008", verify=True)
    apply_pending(engine, migrations)
    logger.info("[SCHEMA] Verified existing schema upgraded through migrations.")


def _ensure_initial_ward_registry(engine) -> None:
    """Create the verified Dhule ward names in non-production local schemas."""
    from sqlalchemy.orm import Session
    from server.models.municipality import Municipality
    from server.models.ward import Ward
    from server.models.user import User

    with Session(engine) as db:
        municipality = db.query(Municipality).filter(Municipality.code == "DHULE").first()
        if municipality is None:
            municipality = Municipality(code="DHULE", name="Dhule", is_active=True)
            db.add(municipality)
            db.flush()
        existing = {ward.ward_number for ward in db.query(Ward).filter(Ward.municipality_id == municipality.id).all()}
        for number in range(1, 20):
            ward_number = str(number)
            if ward_number not in existing:
                db.add(Ward(municipality_id=municipality.id, ward_number=ward_number,
                            display_name=f"Ward {number}", is_active=True))
        db.flush()
        labels = {ward.display_name.strip().casefold(): ward for ward in
                  db.query(Ward).filter(Ward.municipality_id == municipality.id).all()}
        for user in db.query(User).filter(User.ward_id.is_(None), User.ward.isnot(None)).all():
            match = labels.get(user.ward.strip().casefold())
            if match and (user.municipality_id is None or user.municipality_id == municipality.id):
                user.ward_id = match.id
                user.municipality_id = municipality.id
        db.commit()


def verify_required_schema(engine) -> None:
    """Read-only schema verification, including current required contracts."""
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        missing_tables = sorted(REQUIRED_TABLES - tables)

        missing_user_columns: list[str] = []
        if "users" in tables:
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            missing_user_columns = sorted(REQUIRED_USER_COLUMNS - user_columns)

    except Exception as exc:
        raise SchemaValidationError(
            f"Database schema inspection failed closed ({type(exc).__name__})."
        ) from exc

    try:
        verify_migration_contracts(engine)
    except SchemaValidationError as exc:
        contract_error = str(exc)
    else:
        contract_error = "none"
    if missing_tables or missing_user_columns or contract_error != "none":
        raise SchemaValidationError(
            "Database schema is incomplete; apply migrations before application "
            f"startup (missing tables: {missing_tables}; "
            f"missing users columns: {missing_user_columns}; "
            f"migration contract incompatibilities: {contract_error})."
        )
    logger.info("[SCHEMA] Required schema verified (read-only).")


def initialize_database(engine, env: Optional[str], *, allow_mutation: Optional[bool] = None) -> None:
    """Initialize or verify the database according to the environment policy.

    Non-production:
        create_all only for an empty database; verified existing databases are
        adopted through the frozen baseline and upgraded in migration order.
    Production:
        read-only verification only; raises SchemaValidationError when objects
        are missing. No create_all, ALTER TABLE, or CREATE INDEX is ever run.
    """
    if allow_mutation is None:
        allow_mutation = schema_mutation_allowed(env)
    if allow_mutation:
        # Never permit an override flag or a mismatched ENV to bypass target
        # classification. Validation must precede the first create/alter call.
        validate_development_target(engine, env)
        _create_base_schema(engine, env)
    else:
        logger.info("[SCHEMA] Production startup: verification-only mode (no DDL).")
    verify_required_schema(engine)


def resynchronize_sequences(
    db, env: Optional[str], *, allow_mutation: Optional[bool] = None
) -> None:
    """Advance PostgreSQL id sequences past the current max id.

    This mutates sequence state, so it is skipped together with every other
    startup mutation (production and any unrecognised environment). On SQLite
    the pg_* calls fail and are ignored, preserving development behaviour.
    """
    if allow_mutation is None:
        allow_mutation = schema_mutation_allowed(env)
    if not allow_mutation:
        logger.info("[SCHEMA] Sequence resynchronisation skipped (no schema mutation allowed).")
        return

    validate_development_target(db.get_bind(), env)

    from sqlalchemy import text

    for table in IDENTIFIER_SEQUENCE_TABLES:
        try:
            sequence = db.execute(
                text(f"SELECT pg_get_serial_sequence('{table}', 'id')")
            ).scalar()
            if sequence:
                max_id = db.execute(
                    text(f"SELECT COALESCE(MAX(id), 0) FROM {table}")
                ).scalar()
                db.execute(
                    text("SELECT setval(CAST(:sequence AS regclass), :value, false)"),
                    {"sequence": sequence, "value": int(max_id) + 1},
                )
        except Exception:
            pass
    db.commit()
    logger.info("[SCHEMA] Sequence resynchronisation complete.")
