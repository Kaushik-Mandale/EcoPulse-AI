"""Explicit migration CLI.

Run migrations deliberately against a verified disposable target. There is no
fallback: every command requires ``--url`` and the application's configured
DATABASE_URL is never consulted. Confirmed mutations require the disposable
designation; production-like names and blocked or public hosts are refused.

Examples:
    python -m server.scripts.migrate status --url postgresql://127.0.0.1:5432/ecopulse_test
    python -m server.scripts.migrate check --url postgresql://127.0.0.1:5432/ecopulse_test
    python -m server.scripts.migrate up --dry-run --url postgresql://127.0.0.1:5432/ecopulse_test
    python -m server.scripts.migrate up --yes --authorize-disposable-target DISPOSABLE --url postgresql://127.0.0.1:5432/ecopulse_test

Exit codes: 0 success, 1 migration/diagnostic failure, 2 refused/usage error.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine

from server.database.migrations_runner import (
    MigrationError,
    PrerequisiteError,
    adopt_existing,
    apply_pending,
    default_migrations_dir,
    diagnose,
    discover_migrations,
    reconcile,
    status as migration_status,
)
from server.database.target_guard import (
    TargetSafetyError,
    describe_target,
    redact_text,
    validate_connection,
    validate_target_url,
)

logger = logging.getLogger("ecopulse.migrate")


def _add_target_options(parser: argparse.ArgumentParser, *, suppress_defaults: bool = False) -> None:
    """Shared options; accepted before or after the subcommand."""
    default = argparse.SUPPRESS if suppress_defaults else None
    parser.add_argument(
        "--url",
        default=default,
        help="Explicit target database URL (required; never defaults to DATABASE_URL).",
    )
    parser.add_argument(
        "--migrations-dir",
        default=default,
        help="Directory containing NNN_name.sql migrations.",
    )
    parser.add_argument(
        "--authorize-disposable-target",
        default=default,
        help="Explicitly designate the URL target disposable; the only accepted value is DISPOSABLE.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Explicit database migration runner.")
    _add_target_options(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show applied and pending migrations.")
    _add_target_options(status_parser, suppress_defaults=True)

    check_parser = subparsers.add_parser(
        "check", help="Read-only diagnostic of migration and schema consistency."
    )
    _add_target_options(check_parser, suppress_defaults=True)

    up = subparsers.add_parser("up", help="Apply pending migrations in order.")
    _add_target_options(up, suppress_defaults=True)
    up.add_argument("--dry-run", action="store_true", help="Print the plan without executing.")
    up.add_argument("--yes", action="store_true", help="Confirm execution.")

    adopt = subparsers.add_parser(
        "adopt", help="Record an existing schema as applied without running DDL."
    )
    _add_target_options(adopt, suppress_defaults=True)
    adopt.add_argument(
        "--through", required=True, help="Highest migration version to record (e.g. 006)."
    )
    adopt.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip sentinel verification (only after manual review).",
    )
    adopt.add_argument("--yes", action="store_true", help="Confirm adoption.")

    reconcile_parser = subparsers.add_parser(
        "reconcile", help="Explicitly reconcile one migration state after review."
    )
    _add_target_options(reconcile_parser, suppress_defaults=True)
    action = reconcile_parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--record",
        metavar="VERSION",
        help="Record a version whose expected objects already exist.",
    )
    action.add_argument(
        "--clear",
        metavar="VERSION",
        help="Clear an incomplete marker whose expected objects are absent.",
    )
    reconcile_parser.add_argument("--yes", action="store_true", help="Confirm reconciliation.")
    return parser


def _resolve_target(args) -> tuple[str | None, int]:
    """Validate the explicit target before any engine exists."""
    if not (args.url or "").strip():
        logger.error(
            "An explicit --url is required. The application DATABASE_URL is never used "
            "as a fallback for migrations."
        )
        return None, 2
    requires_disposable = (args.command == "adopt" and args.yes) or (
        args.command == "reconcile" and args.yes
    ) or (
        args.command == "up" and args.yes and not args.dry_run
    )
    try:
        url = validate_target_url(
            args.url,
            disposable_authorization=args.authorize_disposable_target,
            require_disposable=requires_disposable,
        )
    except TargetSafetyError as exc:
        logger.error("Target refused: %s", redact_text(exc))
        return None, 2
    logger.info("Target database: %s", describe_target(url))
    return url, 0


def _known_versions(migrations) -> set[str]:
    return {"000"} | {migration.version for migration in migrations}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)

    url, exit_code = _resolve_target(args)
    if url is None:
        return exit_code

    directory = Path(args.migrations_dir) if args.migrations_dir else default_migrations_dir()
    engine = None
    try:
        migrations = discover_migrations(directory)
        if args.command == "adopt":
            through = (args.through or "").strip()
            if through not in _known_versions(migrations):
                logger.error(
                    "Invalid --through value %r; expected one of %s.",
                    through,
                    sorted(_known_versions(migrations)),
                )
                return 2

        engine = create_engine(url, pool_pre_ping=True)
        validate_connection(engine)

        if args.command == "status":
            state = migration_status(engine, migrations)
            logger.info(
                "initialized=%s baseline=%s applied=%s in_progress=%s pending=%s",
                state["initialized"],
                state["baseline"],
                state["applied"],
                state["in_progress"],
                state["pending"],
            )
            if not state["initialized"]:
                logger.info(
                    "Migration history has not been initialized; no records were created."
                )
            return 0

        if args.command == "check":
            issues = diagnose(engine, migrations)
            if not issues:
                logger.info("No migration or schema inconsistencies detected.")
                return 0
            for issue in issues:
                logger.error(
                    "%s%s: %s",
                    issue.code,
                    f" [{issue.version}]" if issue.version else "",
                    issue.detail,
                )
            return 1

        if args.command == "up":
            if not args.yes and not args.dry_run:
                state = migration_status(engine, migrations)
                logger.info(
                    "Pending migrations: %s. Re-run with --yes to apply.",
                    state["pending"],
                )
                return 2
            applied = apply_pending(engine, migrations, dry_run=args.dry_run)
            logger.info("%s migrations: %s", "Planned" if args.dry_run else "Applied", applied)
            return 0

        if args.command == "adopt":
            if not args.yes:
                logger.info(
                    "Adoption records an existing schema without DDL. Re-run with --yes to confirm."
                )
                return 2
            recorded = adopt_existing(
                engine,
                migrations,
                through_version=args.through,
                verify=not args.no_verify,
            )
            logger.info("Adoption complete: %s", recorded)
            return 0

        if args.command == "reconcile":
            if not args.yes:
                logger.info(
                    "Reconciliation changes migration history. Re-run with --yes to confirm."
                )
                return 2
            result = reconcile(
                engine,
                migrations,
                record_version=args.record,
                clear_version=args.clear,
            )
            logger.info("Reconciliation complete: %s", result)
            return 0

        return 2
    except TargetSafetyError as exc:
        logger.error("Target refused: %s", redact_text(exc))
        return 2
    except PrerequisiteError as exc:
        logger.error("Prerequisite check failed: %s", redact_text(exc))
        return 2
    except MigrationError as exc:
        logger.error("Migration failed: %s", redact_text(exc))
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        logger.error(
            "Unexpected failure: %s: %s", type(exc).__name__, redact_text(exc)
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
