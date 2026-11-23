import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from server.models.account_invitation import AccountInvitation
from server.models.security_audit_event import SecurityAuditEvent
from server.models.user import User
from server.utils.security import create_access_token, hash_password, verify_password


INVITATION_TTL_HOURS = 24


def _fernet() -> Fernet:
    key = os.getenv("MFA_ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError("MFA_ENCRYPTION_KEY must be configured before privileged MFA can be used.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("MFA_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def encrypt_mfa_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_mfa_secret(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("Stored MFA secret could not be decrypted.") from exc


def _totp_code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp(secret: str, code: str, now: Optional[float] = None) -> Optional[int]:
    if not code or len(code) != 6 or not code.isdigit():
        return None
    step = int((time.time() if now is None else now) // 30)
    for candidate in (step - 1, step, step + 1):
        if hmac.compare_digest(_totp_code(secret, candidate), code):
            return candidate
    return None


def audit(
    db: Session,
    action: str,
    actor: Optional[User] = None,
    target: Optional[User] = None,
    details: Optional[str] = None,
) -> None:
    db.add(SecurityAuditEvent(
        actor_id=actor.id if actor else None,
        target_user_id=target.id if target else None,
        actor_employee_id=actor.employee_id if actor else None,
        target_employee_id=target.employee_id if target else None,
        action=action,
        details=details,
    ))


def issue_invitation(
    db: Session,
    user: User,
    role: str,
    actor: User,
    approved_by: Optional[User] = None,
) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AccountInvitation(
        user_id=user.id,
        role=role,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        created_by_id=actor.id,
        approved_by_id=approved_by.id if approved_by else None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=INVITATION_TTL_HOURS),
    ))
    audit(db, f"{role}_invitation_created", actor=actor, target=user)
    return token


def get_valid_invitation(db: Session, token: str, role: Optional[str] = None) -> tuple[AccountInvitation, User]:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    invitation = db.query(AccountInvitation).filter(
        AccountInvitation.token_hash == token_hash,
        AccountInvitation.consumed_at.is_(None),
        AccountInvitation.revoked_at.is_(None),
        AccountInvitation.expires_at > datetime.now(timezone.utc),
    ).first()
    if not invitation or (role and invitation.role != role):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation is invalid or expired.")
    user = db.query(User).filter(User.id == invitation.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invited account no longer exists.")
    if user.account_status in {"retired", "deactivated", "suspended"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This account is not eligible for invitation activation.")
    return invitation, user


def consume_invitation(db: Session, invitation: AccountInvitation, role: str) -> None:
    now = datetime.now(timezone.utc)
    updated = db.query(AccountInvitation).filter(
        AccountInvitation.id == invitation.id,
        AccountInvitation.role == role,
        AccountInvitation.consumed_at.is_(None),
        AccountInvitation.revoked_at.is_(None),
        AccountInvitation.expires_at > now,
    ).update({"consumed_at": now}, synchronize_session=False)
    if updated != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is invalid, expired, revoked, or already used.",
        )


def validate_employee_allowlist(employee_id: str) -> None:
    allowlist = {
        value.strip().casefold()
        for value in os.getenv("MUNICIPAL_EMPLOYEE_ALLOWLIST", "").split(",")
        if value.strip()
    }
    if not allowlist:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Municipal employee allowlist is not configured.",
        )
    if employee_id.strip().casefold() not in allowlist:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employee identity is not authorized.")


def make_access_token(user: User, sid: str) -> str:
    claims = {
        "sub": user.email or user.phone,
        "role": user.role,
        "id": user.id,
        "sid": sid,
        "sv": user.session_version or 0,
    }
    if user.role in {"admin", "collector"}:
        claims["mfa"] = bool(user.mfa_enabled)
    return create_access_token(claims)


def change_password(db: Session, user: User, password: str, actor: Optional[User] = None) -> None:
    user.hashed_password = hash_password(password)
    user.session_version = (user.session_version or 0) + 1
    user.failed_attempts = 0
    user.is_locked = False
    audit(db, "password_changed", actor=actor, target=user)


def authenticate_password(user: User, password: str) -> bool:
    return bool(user.hashed_password and verify_password(password, user.hashed_password))
