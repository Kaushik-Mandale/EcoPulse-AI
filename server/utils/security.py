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
    user = db.query(User).filter((User.email == sub) | (User.phone == sub) | (User.phone == f"+91{sub}")).first()
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

def get_current_driver_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user or current_user.role.lower() not in ["driver", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Driver privileges required."
        )
    return current_user
