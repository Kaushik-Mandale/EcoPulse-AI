"""One-time, operator-run bootstrap for the predefined Super Admin.

Identity values are supplied through protected operator environment inputs;
the initial password is accepted only through a no-echo prompt. This script
never changes an existing account and is intentionally not part of app startup.
"""
import getpass
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

sys.path.append(str(Path(__file__).resolve().parents[2]))

from server.database.db import SessionLocal
from server.models.user import User
from server.services.auth_service import (
    TEMPORARY_PASSWORD_TTL, normalize_phone_number, validate_indian_mobile,
)
from server.services.iam_service import audit, validate_employee_allowlist
from server.utils.config import is_production_environment
from server.utils.security import hash_password, is_strong_password


class BootstrapConflict(RuntimeError):
    """A requested identity is already owned or the one-time bootstrap ran."""


def _read_password_no_echo(prompt: str) -> str:
    if not sys.stdin.isatty():
        raise RuntimeError("A terminal is required for the protected no-echo password prompt.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except getpass.GetPassWarning as exc:
        raise RuntimeError("The terminal cannot securely disable password echo; bootstrap stopped.") from exc


def provision_super_admin(
    db: Session,
    *,
    employee_id: str,
    login_id: str,
    full_name: str,
    email: str,
    phone: str,
    password: str,
) -> bool:
    """Create the predefined account once; return False for an exact rerun."""
    employee_id = employee_id.strip()
    login_id = login_id.strip()
    full_name = full_name.strip()
    email = email.strip().lower()
    if not all((employee_id, login_id, full_name, email, phone, password)):
        raise ValueError("All Super Admin identity inputs are required.")
    if not is_strong_password(password):
        raise ValueError("Initial password must be 12-72 UTF-8 bytes and include upper/lowercase letters, a number, and a symbol.")
    normalized_phone = validate_indian_mobile(phone)
    validate_employee_allowlist(employee_id)

    existing_super = db.query(User).filter(User.is_super_admin.is_(True)).all()
    if existing_super:
        if len(existing_super) == 1:
            existing = existing_super[0]
            if (
                existing.employee_id == employee_id
                and existing.login_id == login_id
                and (existing.email or "").casefold() == email.casefold()
                and normalize_phone_number(existing.phone or "") == normalized_phone
                and existing.role == "admin"
            ):
                # A rerun is a no-op: in particular, do not reset the password.
                db.rollback()
                return False
        raise BootstrapConflict("A different Super Admin is already provisioned.")

    # Compare normalized phone values across legacy formats as well as exact
    # identifiers. This prevents a Citizen account from being claimed/changed.
    conflicts = {
        "employee_id": db.query(User).filter(func.lower(User.employee_id) == employee_id.lower()).first(),
        "login_id": db.query(User).filter(func.lower(User.login_id) == login_id.lower()).first(),
        "email": db.query(User).filter(func.lower(User.email) == email.lower()).first(),
    }
    for user in db.query(User).filter(User.phone.isnot(None)).all():
        if normalize_phone_number(user.phone or "") == normalized_phone:
            conflicts["phone"] = user
            break
    if any(conflicts.values()):
        raise BootstrapConflict("One or more requested identity values already belong to an account.")

    user = User(
        full_name=full_name,
        employee_id=employee_id,
        login_id=login_id,
        email=email,
        phone=normalized_phone,
        hashed_password=hash_password(password),
        role="admin",
        is_super_admin=True,
        must_change_password=True,
        temporary_password_expires_at=datetime.now(timezone.utc) + TEMPORARY_PASSWORD_TTL,
        is_active=True,
        is_verified=True,
        account_status="active",
    )
    db.add(user)
    try:
        # The unique partial index on is_super_admin is the concurrency guard;
        # the identity indexes also close preflight/insert races.
        db.flush()
        user.created_by_id = user.id
        user.approved_by_id = user.id
        audit(
            db,
            "super_admin_bootstrapped",
            actor=user,
            target=user,
            details="Secure one-time bootstrap utility.",
        )
        db.commit()
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise BootstrapConflict(
            "A requested identity or Super Admin slot was claimed concurrently; no account was created."
        ) from exc
    return True


def main() -> int:
    if not is_production_environment():
        print("Set ENV=production and apply migration 009 before using this bootstrap.")
        return 2
    identity = {
        "employee_id": os.getenv("MUNICIPAL_SUPER_ADMIN_EMPLOYEE_ID", "").strip(),
        "login_id": os.getenv("MUNICIPAL_SUPER_ADMIN_LOGIN_ID", "").strip(),
        "full_name": os.getenv("MUNICIPAL_SUPER_ADMIN_NAME", "").strip(),
        "email": os.getenv("MUNICIPAL_SUPER_ADMIN_EMAIL", "").strip(),
        "phone": os.getenv("MUNICIPAL_SUPER_ADMIN_PHONE", "").strip(),
    }
    if not all(identity.values()):
        print("All MUNICIPAL_SUPER_ADMIN identity inputs are required.")
        return 2
    try:
        password = _read_password_no_echo("Set strong initial Super Admin password (12-72 UTF-8 bytes): ")
        confirmation = _read_password_no_echo("Confirm initial password: ")
    except RuntimeError as exc:
        print(str(exc))
        return 2
    if password != confirmation:
        print("Passwords do not match.")
        return 2

    db = SessionLocal()
    try:
        created = provision_super_admin(db, **identity, password=password)
        if created:
            print("Super Admin account created. Change the initial password, then enroll authenticator-app MFA.")
        else:
            print("The predefined Super Admin is already provisioned; no account data was changed.")
        return 0
    except (BootstrapConflict, ValueError, HTTPException) as exc:
        db.rollback()
        print(f"Super Admin bootstrap refused: {exc}")
        return 2
    except Exception as exc:
        db.rollback()
        print(f"Super Admin bootstrap failed ({type(exc).__name__}); no credentials were logged.")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
