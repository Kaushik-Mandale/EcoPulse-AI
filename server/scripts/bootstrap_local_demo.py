"""Create an isolated local portal-demo database and Super Admin.

This utility is intentionally separate from the production-only Super Admin
bootstrap. It accepts only a new SQLite file directly under the OS temp
directory, requires ENV=development and an explicit DATABASE_URL, and validates
the resolved SQLAlchemy target before schema creation or demo seeding.
"""
from __future__ import annotations

import getpass
import os
import sys
import tempfile
import warnings
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url


class LocalDemoSetupError(RuntimeError):
    """Expected local demo validation failure with a safe user-facing message."""


def _local_demo_database_path(environ=None, temp_root: Path | None = None) -> Path:
    environ = os.environ if environ is None else environ
    environment = (environ.get("ENV") or "").strip().lower()
    secondary_environment = (environ.get("ENVIRONMENT") or "").strip().lower()
    if environment != "development" or secondary_environment not in {"", "development"}:
        raise LocalDemoSetupError("Set ENV=development and remove any conflicting ENVIRONMENT value.")

    raw_url = (environ.get("DATABASE_URL") or "").strip()
    if not raw_url:
        raise LocalDemoSetupError("Set DATABASE_URL to a new local SQLite file directly inside the OS temp directory.")
    try:
        parsed = make_url(raw_url)
    except Exception:
        raise LocalDemoSetupError("DATABASE_URL is not a valid SQLAlchemy URL. Use a local absolute SQLite file URL.") from None
    if parsed.drivername != "sqlite" or parsed.host or parsed.username or parsed.password or parsed.query:
        raise LocalDemoSetupError("Only local SQLite file URLs are allowed; remote database targets are refused.")
    if not parsed.database or parsed.database == ":memory:":
        raise LocalDemoSetupError("Use a new SQLite file rather than an in-memory database.")

    configured_path = Path(parsed.database)
    if not configured_path.is_absolute():
        raise LocalDemoSetupError("DATABASE_URL must contain an absolute SQLite file path.")
    path = configured_path.resolve()
    allowed_root = Path(temp_root or tempfile.gettempdir()).resolve()
    if path.parent != allowed_root:
        raise LocalDemoSetupError("Place the new demo database directly inside the operating-system temp directory.")
    if not path.name.lower().startswith("ecopulse-demo-") or path.suffix.lower() != ".sqlite3":
        raise LocalDemoSetupError("Name the new database ecopulse-demo-*.sqlite3.")
    if path.exists() or path.is_symlink():
        raise LocalDemoSetupError("Choose a new database filename; existing files are never overwritten.")
    return path


def _validate_initial_password(password: str) -> None:
    """Keep the local prompt aligned with the production bootstrap password rule."""
    from server.utils.security import is_strong_password

    if not is_strong_password(password):
        raise LocalDemoSetupError(
            "Initial password must be 12–72 UTF-8 bytes and include uppercase and lowercase letters, a number, and a symbol."
        )


def _safe_failure_message(exc: Exception, phase: str) -> str:
    """Map expected failures to actionable messages without echoing user input."""
    if isinstance(exc, LocalDemoSetupError):
        return str(exc)

    status_code = getattr(exc, "status_code", None)
    if status_code == 400:
        return "The local Super Admin phone number is invalid. Use a 10-digit Indian mobile number starting with 6–9."
    if status_code == 403:
        return "The local Super Admin employee ID is not in MUNICIPAL_EMPLOYEE_ALLOWLIST. Add the local ID to that variable and retry."
    if status_code == 503:
        return "MUNICIPAL_EMPLOYEE_ALLOWLIST is missing or invalid. Set it to the local Super Admin employee ID and retry."

    if isinstance(exc, ValueError):
        if phase == "validating the initial password":
            return "Initial password must be 12–72 UTF-8 bytes and include uppercase and lowercase letters, a number, and a symbol."
        if phase == "validating Super Admin identity":
            return "The local Super Admin identity is incomplete or invalid. Check the required local identity fields and phone format."
        if phase == "creating Super Admin account":
            return "The Super Admin account could not be created because an identity value or password failed validation. Check the local ID, email, phone, and password requirements."
        if phase == "initializing disposable SQLite schema":
            return "SQLite schema initialization rejected a value. Check that DATABASE_URL is an absolute Windows SQLite file URL in the temp directory and retry with a new filename."

    if type(exc).__name__ == "BootstrapConflict":
        return "A local account identity conflicts with the requested Super Admin. Choose unique local identity values and a new disposable database filename."
    if type(exc).__name__ == "SchemaValidationError":
        return "Fresh local schema initialization or verification failed. Check the backend dependencies and retry with a new disposable database filename."
    if type(exc).__name__ == "UnsafeDatabaseTarget":
        return "The resolved database target is not authorized for local development initialization. Use the explicitly configured new SQLite file under the OS temp directory."
    if isinstance(exc, FileExistsError):
        return "The target database filename was claimed or already exists. Choose a new ecopulse-demo-*.sqlite3 filename."

    return (
        f"Local demo bootstrap failed during {phase} ({type(exc).__name__}). "
        "Sensitive exception details were withheld. Check the local configuration and retry with a new disposable SQLite filename."
    )


def _read_password_no_echo(prompt: str) -> str:
    if not sys.stdin.isatty():
        raise LocalDemoSetupError("Run this command in an interactive terminal so the password can be entered without echo.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except getpass.GetPassWarning as exc:
        raise LocalDemoSetupError("This terminal cannot securely hide password input. Use a terminal that supports no-echo prompts.") from None


def _disable_external_delivery() -> None:
    """Ensure the local demo cannot inherit messaging/storage credentials from dotenv."""
    os.environ["OTP_DELIVERY_PROVIDER"] = "development"
    os.environ["SMS_PROVIDER"] = "mock"
    os.environ["WHATSAPP_PROVIDER"] = "meta"
    os.environ["MEDIA_STORAGE_BACKEND"] = "local"
    for name in (
        "WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_VERIFY_TOKEN",
        "WHATSAPP_BUSINESS_PHONE", "META_WHATSAPP_ACCESS_TOKEN",
        "META_WHATSAPP_PHONE_NUMBER_ID", "META_APP_SECRET", "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_NUMBER", "TWILIO_WEBHOOK_URL",
        "SMS_API_KEY", "SMS_TEMPLATE_ID",
    ):
        os.environ[name] = ""


def main() -> int:
    phase = "validating local environment and SQLite target"
    try:
        database_path = _local_demo_database_path()
        required = (
            "DATABASE_URL", "MUNICIPAL_EMPLOYEE_ALLOWLIST",
            "MUNICIPAL_SUPER_ADMIN_EMPLOYEE_ID", "MUNICIPAL_SUPER_ADMIN_LOGIN_ID",
            "MUNICIPAL_SUPER_ADMIN_NAME", "MUNICIPAL_SUPER_ADMIN_EMAIL",
            "MUNICIPAL_SUPER_ADMIN_PHONE", "SECRET_KEY", "MFA_ENCRYPTION_KEY",
        )
        missing = [name for name in required if not (os.environ.get(name) or "").strip()]
        if missing:
            raise LocalDemoSetupError("Set the required local demo configuration variables: " + ", ".join(missing))
        if len(os.environ["SECRET_KEY"].strip()) < 32:
            raise LocalDemoSetupError("Local SECRET_KEY must contain at least 32 characters. Generate a new local-only key and retry.")
        try:
            Fernet(os.environ["MFA_ENCRYPTION_KEY"].strip().encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            raise LocalDemoSetupError("MFA_ENCRYPTION_KEY must be a valid Fernet key generated for this local demo.") from None

        phase = "reading the no-echo password prompt"
        password = _read_password_no_echo("Set initial local Super Admin password: ")
        confirmation = _read_password_no_echo("Confirm local Super Admin password: ")
        if password != confirmation:
            raise LocalDemoSetupError("Passwords do not match. Run the helper again and enter the same value twice.")
        phase = "validating the initial password"
        _validate_initial_password(password)

        # Pin both environment aliases before dotenv-backed modules are loaded.
        os.environ["ENVIRONMENT"] = "development"
        _disable_external_delivery()

        # Imports that resolve the engine are deliberately delayed until after
        # the explicit environment and temp-file target have been checked.
        from server.database.db import engine, SessionLocal
        from server.database.initialization import initialize_database
        from server.database.target_policy import validate_development_target
        from server.models.user import User
        import server.models  # noqa: F401
        from server.scripts.bootstrap_super_admin import provision_super_admin
        from server.services.auth_service import AuthService
        from server.utils.config import get_environment
        from server.services.iam_service import validate_employee_allowlist

        phase = "validating the resolved SQLite target"
        environment = get_environment()
        if environment != "development":
            raise LocalDemoSetupError("Resolved application environment must be development.")
        validate_development_target(engine, environment)

        phase = "validating Super Admin identity"
        identity = {
            "employee_id": os.environ["MUNICIPAL_SUPER_ADMIN_EMPLOYEE_ID"].strip(),
            "login_id": os.environ["MUNICIPAL_SUPER_ADMIN_LOGIN_ID"].strip(),
            "full_name": os.environ["MUNICIPAL_SUPER_ADMIN_NAME"].strip(),
            "email": os.environ["MUNICIPAL_SUPER_ADMIN_EMAIL"].strip(),
            "phone": os.environ["MUNICIPAL_SUPER_ADMIN_PHONE"].strip(),
        }
        from server.services.auth_service import validate_indian_mobile
        validate_indian_mobile(identity["phone"])
        validate_employee_allowlist(identity["employee_id"])

        # Reserve the new file atomically after target validation, so a race or
        # pre-existing temp file cannot be overwritten by SQLite initialization.
        phase = "reserving the new disposable SQLite file"
        descriptor = os.open(database_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)

        phase = "initializing disposable SQLite schema"
        initialize_database(engine, environment)
        db = SessionLocal()
        try:
            phase = "creating Super Admin account"
            if not provision_super_admin(db, **identity, password=password):
                raise LocalDemoSetupError("A Super Admin already exists; local demo bootstrap requires a new disposable database.")
            phase = "seeding local demo accounts"
            if not AuthService.should_seed_demo_users(db):
                raise LocalDemoSetupError("Development demo seeding was refused by the database target policy.")
            AuthService.seed_demo_users(db)
            seeded_roles = {row[0] for row in db.query(User.role).all()}
            missing_roles = {"citizen", "admin", "driver", "collector"} - seeded_roles
            if missing_roles:
                raise RuntimeError("Local role demo accounts were not fully seeded.")
        finally:
            db.close()
            engine.dispose()

        print("Local disposable demo database initialized; development accounts seeded.")
        print("Super Admin created with forced password rotation and mandatory MFA.")
        print(f"Database file: {database_path}")
        print("Start the API with this same database target so it can find these accounts:")
        print(f"$env:DATABASE_URL = 'sqlite:///{database_path.as_posix()}'")
        print("$env:ENV = 'development'; $env:ENVIRONMENT = 'development'")
        print("No passwords, OTPs, or messaging credentials were printed or delivered.")
        return 0
    except Exception as exc:
        # Do not display exception text from third-party providers or database
        # drivers because it could contain connection details.
        print(f"Local demo bootstrap refused or failed during {phase}.")
        print(_safe_failure_message(exc, phase))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
