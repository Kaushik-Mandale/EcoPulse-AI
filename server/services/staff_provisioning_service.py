"""Shared, transactional provisioning for Municipal Admins, Drivers and Collectors."""
import re
import secrets
import string
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from server.models.user import User
from server.models.municipality import Municipality
from server.models.ward import Ward
from server.services.auth_service import (
    TEMPORARY_PASSWORD_TTL, normalize_phone_number, validate_indian_mobile,
)
from server.services.iam_service import audit
from server.services.ward_service import actor_municipality_ids, ensure_staff_scope, resolve_active_ward
from server.utils.security import hash_password


LOGIN_PREFIXES = {"admin": "ADM", "driver": "DRV", "collector": "COL"}
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}$")
_TEMP_PASSWORD_UPPER = string.ascii_uppercase
_TEMP_PASSWORD_LOWER = string.ascii_lowercase
_TEMP_PASSWORD_DIGITS = string.digits
_TEMP_PASSWORD_SPECIAL = string.punctuation
_TEMP_PASSWORD_ALPHABET = (
    _TEMP_PASSWORD_UPPER + _TEMP_PASSWORD_LOWER + _TEMP_PASSWORD_DIGITS + _TEMP_PASSWORD_SPECIAL
)


def _authorize_creator(actor: User, target_role: str, target: User | None = None, db: Session | None = None) -> None:
    if actor.role.casefold() != "admin":
        raise HTTPException(status_code=403, detail="Only authorized administrators may provision staff.")
    is_super_admin = bool(actor.is_super_admin)
    if target_role == "admin" and not is_super_admin:
        raise HTTPException(status_code=403, detail="Only a Super Admin may provision Municipal Admins.")
    if not is_super_admin and target_role not in {"driver", "collector"}:
        raise HTTPException(status_code=403, detail="Municipal Admins may provision Drivers and Collectors only.")
    if target is not None:
        if bool(target.is_super_admin):
            raise HTTPException(status_code=403, detail="Super Admin credentials cannot be reset through staff management.")
        if not is_super_admin and target.role not in {"driver", "collector"}:
            raise HTTPException(status_code=403, detail="Municipal Admins may manage Driver and Collector credentials only.")
        if not is_super_admin and db is not None:
            ensure_staff_scope(db, actor, target)


def _next_login_id(db: Session, prefix: str) -> str:
    values = db.query(User.login_id, User.employee_id).all()
    highest = 0
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$", re.IGNORECASE)
    for login_id, employee_id in values:
        for value in (login_id, employee_id):
            match = pattern.fullmatch(value or "")
            if match:
                highest = max(highest, int(match.group(1)))
    return f"{prefix}{highest + 1:03d}"


def _temporary_password() -> str:
    characters = [
        secrets.choice(_TEMP_PASSWORD_UPPER),
        secrets.choice(_TEMP_PASSWORD_LOWER),
        secrets.choice(_TEMP_PASSWORD_DIGITS),
        secrets.choice(_TEMP_PASSWORD_SPECIAL),
    ]
    characters.extend(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(12))
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def _is_login_id_collision(exc: IntegrityError) -> bool:
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    raw_message = str(getattr(exc, "orig", exc)).lower()
    return constraint == "uq_users_login_id" or "users.login_id" in raw_message


def _is_transient_write_collision(exc: OperationalError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return "database is locked" in message or "deadlock detected" in message


def _validate_identity(db: Session, *, role: str, full_name: str, phone: str,
                       email: str | None, employee_id: str | None,
                       actor: User) -> tuple[str, str | None, str | None, str | None]:
    name = full_name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Full name must contain at least two characters.")
    clean_phone = validate_indian_mobile(phone)
    clean_email = (email or "").strip().lower() or None
    if clean_email and (len(clean_email) > 120 or not _EMAIL_RE.fullmatch(clean_email)):
        raise HTTPException(status_code=422, detail="Provide a valid email address.")
    official_employee_id = (employee_id or "").strip() or None
    if role == "admin":
        if not official_employee_id:
            raise HTTPException(status_code=422, detail="Official employee ID is required for Municipal Admins.")
    elif role in {"driver", "collector"}:
        if official_employee_id:
            raise HTTPException(status_code=422, detail="Official employee ID is only set for Municipal Admins.")

    if official_employee_id and db.query(User.id).filter(
        (func.lower(User.employee_id) == official_employee_id.casefold())
        | (func.lower(User.login_id) == official_employee_id.casefold())
    ).first():
        raise HTTPException(status_code=409, detail="That official employee ID is already assigned.")
    if clean_email and db.query(User.id).filter(func.lower(User.email) == clean_email).first():
        raise HTTPException(status_code=409, detail="That email address is already in use.")
    # Normalize legacy formatted values too (e.g. a stored +91 number).
    matches = db.query(User.phone).filter(User.phone.isnot(None)).all()
    if any(normalize_phone_number(value or "") == clean_phone for (value,) in matches):
        raise HTTPException(status_code=409, detail="That mobile number is already in use.")
    return name, clean_email, official_employee_id, None


def _credential_response(user: User, temporary_password: str) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "role": user.role,
        "employee_id": user.employee_id,
        "login_id": user.login_id,
        "temporary_password": temporary_password,
        "ward": user.ward,
        "ward_id": user.ward_id,
        "municipality_id": user.municipality_id,
        "account_status": user.account_status,
        "is_verified": bool(user.is_verified),
        "temporary_password_expires_at": user.temporary_password_expires_at,
    }


def provision_staff_account(db: Session, actor: User, payload) -> dict:
    role = payload.role.casefold()
    if role not in LOGIN_PREFIXES:
        raise HTTPException(status_code=422, detail="Unsupported staff role.")
    _authorize_creator(actor, role)
    name, email, employee_id, _ = _validate_identity(
        db,
        role=role,
        full_name=payload.full_name,
        phone=payload.phone,
        email=payload.email,
        employee_id=payload.employee_id,
        actor=actor,
    )
    ward = None
    ward_record = None
    municipality_id = None
    if role in {"driver", "collector"}:
        if not payload.ward_id:
            raise HTTPException(status_code=422, detail="Choose an assigned ward from the municipality registry.")
        ward_record = resolve_active_ward(db, actor, payload.ward_id)
        ward = ward_record.display_name
        municipality_id = ward_record.municipality_id
        if actor.ward_id and not actor.is_super_admin and actor.ward_id != ward_record.id:
            raise HTTPException(status_code=403, detail="You may provision staff only in your assigned ward.")
    elif payload.municipality_id:
        municipality = db.query(Municipality).filter(
            Municipality.id == payload.municipality_id, Municipality.is_active.is_(True)
        ).first()
        if not municipality:
            raise HTTPException(status_code=422, detail="Select an active municipality from the registry.")
        allowed = actor_municipality_ids(db, actor)
        if allowed is not None and municipality.id not in allowed:
            raise HTTPException(status_code=403, detail="You may provision accounts only within your municipality.")
        municipality_id = municipality.id
    else:
        allowed = actor_municipality_ids(db, actor)
        if allowed is None:
            active_ids = {row.id for row in db.query(Municipality.id).filter(Municipality.is_active.is_(True)).all()}
            if len(active_ids) != 1:
                raise HTTPException(status_code=422, detail="Choose a municipality for the Municipal Admin account.")
            allowed = active_ids
        municipality_id = next(iter(allowed))
    clean_phone = validate_indian_mobile(payload.phone)

    for _ in range(8):
        login_id = _next_login_id(db, LOGIN_PREFIXES[role])
        temporary_password = _temporary_password()
        now = datetime.now(timezone.utc)
        user = User(
            full_name=name,
            role=role,
            employee_id=employee_id,
            login_id=login_id,
            email=email,
            phone=clean_phone,
            ward=ward,
            ward_id=ward_record.id if ward_record else None,
            municipality_id=municipality_id,
            hashed_password=hash_password(temporary_password),
            must_change_password=True,
            temporary_password_expires_at=now + TEMPORARY_PASSWORD_TTL,
            is_super_admin=False,
            is_active=True,
            # Drivers must complete the existing phone verification flow;
            # privileged portal accounts still require MFA before sessions.
            is_verified=role in {"admin", "collector"},
            account_status="active",
            verified_at=now if role in {"admin", "collector"} else None,
            activated_at=now if role in {"admin", "collector"} else None,
        )
        db.add(user)
        try:
            db.flush()
        except OperationalError as exc:
            db.rollback()
            if _is_transient_write_collision(exc):
                continue
            raise HTTPException(status_code=503, detail="Staff account could not be saved safely.") from exc
        except IntegrityError as exc:
            db.rollback()
            if _is_login_id_collision(exc):
                continue
            raise HTTPException(status_code=409, detail="A staff identity value conflicts with an existing account.") from exc

        user.created_by_id = actor.id
        user.approved_by_id = actor.id
        audit(db, f"{role}_account_provisioned", actor=actor, target=user)
        try:
            db.commit()
        except OperationalError as exc:
            db.rollback()
            if _is_transient_write_collision(exc):
                continue
            raise HTTPException(status_code=503, detail="Staff account could not be saved safely.") from exc
        except IntegrityError as exc:
            db.rollback()
            if _is_login_id_collision(exc):
                continue
            raise HTTPException(status_code=409, detail="A staff identity value conflicts with an existing account.") from exc
        db.refresh(user)
        return _credential_response(user, temporary_password)

    raise HTTPException(status_code=503, detail="A unique staff login ID could not be allocated. Please retry.")


def reset_staff_password(db: Session, actor: User, target: User) -> dict:
    if target.role not in LOGIN_PREFIXES:
        raise HTTPException(status_code=409, detail="This account is not managed by centralized staff provisioning.")
    for _ in range(8):
        locked_target = db.query(User).filter(User.id == target.id).with_for_update().first()
        if not locked_target:
            raise HTTPException(status_code=404, detail="Staff account not found.")
        if locked_target.account_status in {"retired", "deactivated"}:
            raise HTTPException(status_code=409, detail="Retired accounts cannot receive new credentials.")
        _authorize_creator(actor, locked_target.role, locked_target, db=db)
        if not locked_target.login_id:
            locked_target.login_id = _next_login_id(db, LOGIN_PREFIXES[locked_target.role])
        temporary_password = _temporary_password()
        locked_target.hashed_password = hash_password(temporary_password)
        locked_target.must_change_password = True
        locked_target.temporary_password_expires_at = datetime.now(timezone.utc) + TEMPORARY_PASSWORD_TTL
        locked_target.session_version = (locked_target.session_version or 0) + 1
        locked_target.failed_attempts = 0
        audit(db, "staff_temporary_password_issued", actor=actor, target=locked_target)
        try:
            db.commit()
        except OperationalError as exc:
            db.rollback()
            if _is_transient_write_collision(exc):
                continue
            raise HTTPException(status_code=503, detail="Staff account could not be reset safely.") from exc
        except IntegrityError as exc:
            db.rollback()
            if _is_login_id_collision(exc):
                continue
            raise HTTPException(status_code=409, detail="Staff account could not be reset safely.") from exc
        db.refresh(locked_target)
        return _credential_response(locked_target, temporary_password)
    raise HTTPException(status_code=503, detail="A unique staff login ID could not be allocated. Please retry.")
