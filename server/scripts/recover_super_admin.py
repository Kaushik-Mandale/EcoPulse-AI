import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[2]))

from server.database.db import SessionLocal
from server.models.user import User
from server.services.auth_service import TEMPORARY_PASSWORD_TTL, temporary_password_expired
from server.services.iam_service import audit, validate_employee_allowlist
from server.utils.config import is_production_environment
from server.utils.security import hash_password, is_strong_password


def reissue_expired_bootstrap_password(db, *, employee_id: str, password: str) -> str:
    """Reissue an expired first-login secret only for the existing Super Admin."""
    user = db.query(User).filter(User.is_super_admin.is_(True)).one_or_none()
    if (
        not user or user.role != "admin" or user.employee_id != employee_id
        or not user.is_active
        or user.account_status != "active" or not user.must_change_password
        or not temporary_password_expired(user)
    ):
        raise RuntimeError("Recovery is limited to the matching active Super Admin with an expired onboarding password.")
    if not is_strong_password(password):
        raise ValueError("Recovery password does not meet the required strength.")
    user.hashed_password = hash_password(password)
    user.temporary_password_expires_at = datetime.now(timezone.utc) + TEMPORARY_PASSWORD_TTL
    user.session_version = (user.session_version or 0) + 1
    user.failed_attempts = 0
    user.is_locked = False
    audit(
        db,
        "super_admin_onboarding_password_reissued",
        actor=user,
        target=user,
        details="Operator-approved recovery of expired first-login credentials.",
    )
    db.commit()
    return user.login_id or user.employee_id


def main() -> int:
    if not is_production_environment() or os.getenv("MUNICIPAL_IAM_RECOVERY_APPROVED") != "YES":
        print("Recovery requires ENV=production and MUNICIPAL_IAM_RECOVERY_APPROVED=YES after municipal approval.")
        return 2
    employee_id = os.getenv("MUNICIPAL_SUPER_ADMIN_EMPLOYEE_ID", "").strip()
    login_id = os.getenv("MUNICIPAL_SUPER_ADMIN_LOGIN_ID", "").strip()
    full_name = os.getenv("MUNICIPAL_SUPER_ADMIN_NAME", "").strip()
    if not employee_id or not login_id or not full_name:
        print("MUNICIPAL_SUPER_ADMIN_EMPLOYEE_ID, MUNICIPAL_SUPER_ADMIN_LOGIN_ID and MUNICIPAL_SUPER_ADMIN_NAME are required.")
        return 2
    try:
        validate_employee_allowlist(employee_id)
    except HTTPException as exc:
        print(f"Recovery employee verification failed: {exc}")
        return 2
    password = getpass.getpass("Set strong recovery Super Admin password (12-72 UTF-8 bytes): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation or not is_strong_password(password):
        print("Passwords must match, be 12-72 UTF-8 bytes, and contain upper/lowercase letters, a number, and a symbol.")
        return 2

    db = SessionLocal()
    try:
        existing_super_admins = db.query(User).filter(User.is_super_admin.is_(True)).all()
        if existing_super_admins:
            if len(existing_super_admins) != 1:
                print("Super Admin state is inconsistent; recovery refused.")
                return 2
            try:
                recovered_login_id = reissue_expired_bootstrap_password(
                    db, employee_id=employee_id, password=password,
                )
            except (RuntimeError, ValueError) as exc:
                db.rollback()
                print(f"Recovery refused: {exc}")
                return 2
            print(f"Expired first-login credentials reissued for {recovered_login_id}. Rotate the password and complete MFA enrollment.")
            return 0
        if db.query(User).filter(
            (User.employee_id == employee_id) | (User.login_id == login_id)
        ).first():
            print("The requested employee or login ID already belongs to an account; recovery refused.")
            return 2
        user = User(
            full_name=full_name,
            employee_id=employee_id,
            login_id=login_id,
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
        db.flush()
        user.created_by_id = user.id
        user.approved_by_id = user.id
        audit(
            db,
            "super_admin_recovered",
            actor=user,
            target=user,
            details="Operator-approved offline recovery utility.",
        )
        db.commit()
        print(f"Recovery Super Admin {login_id} created. Rotate the temporary password and enroll authenticator-app MFA within 72 hours.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Super Admin recovery failed ({type(exc).__name__}); no credentials were logged.")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
