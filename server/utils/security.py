import os
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from server.database.db import get_db
from server.models.user import User

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 hours

def get_jwt_secret() -> str:
    secret = os.getenv("SECRET_KEY", "").strip()
    if secret:
        return secret
    env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()
    if env == "production":
        raise RuntimeError("CRITICAL: SECRET_KEY environment variable is missing or empty in production mode.")
    return "ecopulse-dev-secret-key-not-for-production"

SECRET_KEY = os.getenv("SECRET_KEY", "")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def is_strong_password(password: str) -> bool:
    if not isinstance(password, str):
        return False
    byte_length = len(password.encode("utf-8"))
    return (
        12 <= byte_length <= 72
        and any(character.islower() for character in password)
        and any(character.isupper() for character in password)
        and any(character.isdigit() for character in password)
        and any(not character.isalnum() for character in password)
    )

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = plain_password.encode('utf-8')[:72]
        hash_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, get_jwt_secret(), algorithm=ALGORITHM)

def get_current_user_optional(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
        sub: str = payload.get("sub")
        if sub is None:
            return None
    except (JWTError, RuntimeError):
        return None
    user_id = payload.get("id")
    if user_id is not None:
        user = db.query(User).filter(User.id == user_id).first()
    else:
        user = db.query(User).filter((User.email == sub) | (User.phone == sub) | (User.phone == f"+91{sub}")).first()
    if not user or not user.is_active or user.is_locked or getattr(user, "account_status", "active") != "active":
        return None
    # A stale or manually constructed token must never bypass first-login
    # onboarding, even if it predates a must-change-password flag update.
    if getattr(user, "must_change_password", False):
        return None
    token_role = payload.get("role")
    if not isinstance(token_role, str) or token_role.casefold() != user.role.casefold():
        return None
    if user.role == "driver" and not getattr(user, "is_verified", False):
        return None
    if int(payload.get("sv", 0)) != int(getattr(user, "session_version", 0) or 0):
        return None
    if user.role in {"admin", "collector"} and (
        not getattr(user, "mfa_enabled", False) or payload.get("mfa") is not True
    ):
        return None
    return user

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user = get_current_user_optional(token, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials. Authorization required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user or current_user.role.lower() not in ["admin", "collector"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin or Collector privileges required."
        )
    return current_user


def require_municipal_admin(current_user: User) -> User:
    """Require a municipal administrator; collectors are never admin substitutes."""
    if current_user.role.lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Municipal administrator privileges are required.",
        )
    return current_user


def require_collector_ward(current_user: User) -> str:
    """Return a collector's canonical ward, denying unassigned collectors."""
    if current_user.role.lower() != "collector":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Collector privileges are required.")
    ward = (current_user.ward or "").strip()
    if not ward:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Collector has no assigned ward.")
    return ward


def get_current_super_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role.lower() != "admin" or not getattr(current_user, "is_super_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin privileges are required."
        )
    return current_user

def get_current_driver_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user or current_user.role.lower() != "driver":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Driver privileges required."
        )
    return current_user
