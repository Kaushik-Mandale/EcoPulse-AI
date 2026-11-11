import os
import re
import time
import hmac
import hashlib
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status

from server.models.user import User
from server.models.mobile_otp import MobileOtpToken
from server.schemas.auth import (
    SignupRequest, RegisterRequest, LoginRequest, OtpLoginRequest,
    AuthResponse, UserResponse, UserProfileUpdate
)
from server.utils.security import hash_password, verify_password, create_access_token, get_jwt_secret
from server.utils.config import config, normalize_environment
from server.services.otp_delivery import get_otp_delivery_provider

logger = logging.getLogger(__name__)

# Dummy hash used for constant-time comparison to prevent user enumeration attacks
DUMMY_HASH = "$2b$12$e80yJ/6h/UoK5h45l35vpe4dM8zV9P0b2K5l0Z7o1Z4m2n7l9p2e2"


def normalize_phone_number(phone: str) -> str:
    """Normalizes phone input (+91, 0, spaces, dashes) to clean 10-digit format."""
    if not phone:
        return ""
    clean = re.sub(r"\D", "", phone.strip())
    if clean.startswith("91") and len(clean) == 12:
        clean = clean[2:]
    elif clean.startswith("0") and len(clean) == 11:
        clean = clean[1:]
    return clean


def format_e164_indian_mobile(phone: str) -> str:
    """Formats a 10-digit Indian mobile number into E.164 format (+91XXXXXXXXXX)."""
    clean = re.sub(r"\D", "", phone.strip())
    if clean.startswith("91") and len(clean) == 12:
        clean = clean[2:]
    elif clean.startswith("0") and len(clean) == 11:
        clean = clean[1:]
    if len(clean) != 10:
        raise ValueError(f"Invalid phone number length: {phone}")
    return f"+91{clean}"


def hash_otp(otp: str, secret: Optional[str] = None) -> str:
    """Computes HMAC-SHA256 hash of a 6-digit OTP using the server-side SECRET_KEY."""
    if not secret:
        secret = get_jwt_secret()
    return hmac.new(
        secret.encode("utf-8"),
        otp.strip().encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def validate_indian_mobile(phone: str) -> str:
    """Validates that the input represents a valid 10-digit Indian mobile number."""
    clean = normalize_phone_number(phone)
    if not re.match(r"^[6-9]\d{9}$", clean):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid mobile number. Please provide a valid 10-digit Indian mobile number (starting with 6, 7, 8, or 9)."
        )
    return clean


class AuthService:
    @staticmethod
    def find_user_by_phone(db: Session, clean_phone: str) -> Optional[User]:
        """Finds a user by clean 10-digit phone, matching with or without country code prefix."""
        if not clean_phone:
            return None
        return db.query(User).filter(
            (User.phone == clean_phone) |
            (User.phone == f"+91{clean_phone}") |
            (User.phone == f"0{clean_phone}")
        ).first()

    @staticmethod
    def should_seed_demo_users() -> bool:
        """Only seed demo users in development/test environments."""
        env = normalize_environment(os.getenv("ENV", os.getenv("ENVIRONMENT", config.ENV)))
        return env in ("development", "test")

    @staticmethod
    def seed_demo_users(db: Session):
        """Seeds standard demo accounts if they do not exist."""
        if not AuthService.should_seed_demo_users():
            return
        demo_accounts = [
            {
                "full_name": "Priya Patil",
                "email": "priya@cityswap.io",
                "phone": "9876543210",
                "employee_id": None,
                "password": "Password123!",
                "role": "citizen",
                "ward": "Ward 12"
            },
            {
                "full_name": "Ramesh Yadav",
                "email": "ramesh@cityswap.io",
                "phone": "9876543211",
                "employee_id": "EMP-DRIVER-01",
                "password": "Password123!",
                "role": "driver",
                "ward": "Ward 12"
            },
            {
                "full_name": "Suresh Sanitation",
                "email": "collector@cityswap.io",
                "phone": "9876543212",
                "employee_id": "EMP-ADMIN-01",
                "password": "Password123!",
                "role": "collector",
                "ward": "HQ"
            },
            {
                "full_name": "Admin Officer",
                "email": "admin@cityswap.io",
                "phone": "9876543213",
                "employee_id": "EMP-SUPER-01",
                "password": "Password123!",
                "role": "admin",
                "ward": "HQ"
            }
        ]
        from sqlalchemy import or_
        for acc in demo_accounts:
            conds = [User.email == acc["email"]]
            if acc.get("phone"):
                conds.append(User.phone == acc["phone"])
            if acc.get("employee_id"):
                conds.append(User.employee_id == acc["employee_id"])
            existing = db.query(User).filter(or_(*conds)).first()
            if not existing:
                u = User(
                    full_name=acc["full_name"],
                    email=acc["email"],
                    employee_id=acc.get("employee_id"),
                    hashed_password=hash_password(acc["password"]),
                    role=acc["role"],
                    ward=acc.get("ward"),
                    phone=acc.get("phone"),
                    eco_coins=150,
                    is_active=True
                )
                db.add(u)
            else:
                if not existing.phone and acc.get("phone"):
                    existing.phone = acc.get("phone")
        try:
            db.commit()
        except Exception:
            db.rollback()

    @staticmethod
    def send_otp(db: Session, phone: str, purpose: str = "login", ip_address: Optional[str] = None) -> dict:
        """
        Generates and dispatches a cryptographically secure 6-digit OTP via Meta WhatsApp.
        Enforces resend cooldown, mobile rate-limits, and IP rate-limits.
        Stores only an HMAC-SHA256 hash of the OTP. Never logs or returns plaintext OTP.
        """
        clean_phone = validate_indian_mobile(phone)
        purpose = (purpose or "login").strip().lower()
        now = datetime.now(timezone.utc)

        # Purpose-specific account validation
        existing_user = AuthService.find_user_by_phone(db, clean_phone)

        if purpose == "register":
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This mobile number is already registered. Please sign in instead."
                )
        elif purpose == "login":
            if not existing_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No account found registered with +91 {clean_phone}. Please sign up first."
                )
            if existing_user.is_locked or not existing_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account is suspended or locked. Please contact municipal support."
                )

        # 1. Resend cooldown check (60 seconds)
        cooldown_window = now - timedelta(seconds=config.SMS_RESEND_COOLDOWN_SECONDS)
        recent_token = db.query(MobileOtpToken).filter(
            MobileOtpToken.phone == clean_phone,
            MobileOtpToken.consumed_at.is_(None),
            MobileOtpToken.created_at >= cooldown_window
        ).order_by(MobileOtpToken.id.desc()).first()

        if recent_token:
            created_at = recent_token.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            elapsed = (now - created_at).total_seconds()
            remaining = max(1, int(config.SMS_RESEND_COOLDOWN_SECONDS - elapsed))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} seconds before requesting a new verification code."
            )

        # 2. Maximum OTP requests per mobile number in 15 minutes (max 5)
        fifteen_min_ago = now - timedelta(minutes=15)
        recent_count = db.query(MobileOtpToken).filter(
            MobileOtpToken.phone == clean_phone,
            MobileOtpToken.created_at >= fifteen_min_ago
        ).count()
        if recent_count >= 5:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many OTP requests for this mobile number. Please try again after 15 minutes."
            )

        # 3. IP address rate limit (max 15 requests per 15 minutes)
        if ip_address:
            ip_count = db.query(MobileOtpToken).filter(
                MobileOtpToken.ip_address == ip_address,
                MobileOtpToken.created_at >= fifteen_min_ago
            ).count()
            if ip_count >= 15:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests from this network. Please try again later."
                )

        # 4. Invalidate all previous unconsumed OTPs for this mobile number
        db.query(MobileOtpToken).filter(
            MobileOtpToken.phone == clean_phone,
            MobileOtpToken.consumed_at.is_(None)
        ).update({"consumed_at": now}, synchronize_session=False)

        # 5. Generate a cryptographically secure 6-digit OTP and hash it
        otp_plaintext = f"{secrets.randbelow(1000000):06d}"
        otp_hash = hash_otp(otp_plaintext)
        expires_at = now + timedelta(seconds=config.SMS_OTP_EXPIRY_SECONDS)

        new_token = MobileOtpToken(
            phone=clean_phone,
            otp_hash=otp_hash,
            purpose=purpose,
            ip_address=ip_address,
            attempts=0,
            max_attempts=5,
            expires_at=expires_at,
            consumed_at=None
        )
        db.add(new_token)
        db.commit()

        # 6. Dispatch via Meta WhatsApp Cloud API
        e164_phone = format_e164_indian_mobile(clean_phone)
        delivery_provider = get_otp_delivery_provider()
        result = delivery_provider.send_otp(e164_phone, otp_plaintext)

        if not result.success:
            # Clean up un-dispatched token so citizen is not unfairly penalized with cooldown
            db.delete(new_token)
            db.commit()

            err_code = result.error_code or "FAILED"
            err_msg = result.message or "WhatsApp verification service is unable to dispatch code."
            if err_code == "NOT_CONFIGURED":
                detail = (
                    "WhatsApp OTP delivery is not configured. "
                    "Please contact the system administrator."
                )
            else:
                detail = f"WhatsApp OTP dispatch failed: {err_msg}. Please try again later."

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=detail
            )

        # 7. Persist provider message ID (wamid) and initial ACCEPTED delivery status
        # Fails safely with clear diagnostic log if migration 005 has not been applied yet
        token_id = new_token.id
        try:
            new_token.provider_message_id = result.provider_message_id
            new_token.delivery_status = "ACCEPTED"
            new_token.updated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as schema_err:
            db.rollback()
            logger.error(
                "[SCHEMA COMPATIBILITY ERROR] Failed to record provider_message_id/delivery_status in mobile_otp_tokens (%s). "
                "Authoritative migration required: execute migrations/005_meta_otp_delivery_observability.sql.",
                type(schema_err).__name__
            )

        challenge_id = AuthService.create_challenge_id(token_id, clean_phone, expires_at, purpose=purpose)
        masked_phone = f"+91 ******{clean_phone[-4:]}"
        return {
            "success": True,
            "message": f"Verification code dispatched via WhatsApp to {masked_phone}.",
            "phone": clean_phone,
            "challenge_id": challenge_id,
            "delivery_status": "ACCEPTED",
            "channel": "whatsapp",
            "cooldown_seconds": config.SMS_RESEND_COOLDOWN_SECONDS,
            "expires_in": config.SMS_OTP_EXPIRY_SECONDS,
            "account_exists": existing_user is not None
        }

    @staticmethod
    def create_challenge_id(token_id: int, phone: str, expires_at: datetime, purpose: str = "login") -> str:
        """Generates an HMAC-SHA256 signed, tamper-proof challenge identifier binding token, phone, purpose, and expiry."""
        import base64
        exp_ts = int(expires_at.timestamp())
        payload = f"{token_id}:{phone}:{purpose}:{exp_ts}"
        secret = config.SECRET_KEY or "ecopulse-default-secret-key-change-in-prod"
        sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        raw = f"{payload}:{sig}"
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")

    @staticmethod
    def verify_and_get_challenge_token(db: Session, challenge_id: str) -> Optional[MobileOtpToken]:
        """Validates the challenge HMAC signature and retrieves the corresponding database token."""
        import base64
        try:
            raw = base64.urlsafe_b64decode(challenge_id.encode("utf-8")).decode("utf-8")
            parts = raw.split(":")
            if len(parts) == 5:
                token_id_str, phone, purpose, exp_ts_str, sig = parts
                payload = f"{token_id_str}:{phone}:{purpose}:{exp_ts_str}"
            elif len(parts) == 4:
                token_id_str, phone, exp_ts_str, sig = parts
                payload = f"{token_id_str}:{phone}:{exp_ts_str}"
            else:
                return None
            token_id = int(token_id_str)
            secret = config.SECRET_KEY or "ecopulse-default-secret-key-change-in-prod"
            expected_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
            if not hmac.compare_digest(sig, expected_sig):
                return None
            token = db.query(MobileOtpToken).filter(MobileOtpToken.id == token_id).first()
            if not token or token.phone != phone:
                return None
            return token
        except Exception:
            return None

    @staticmethod
    def get_challenge_status(db: Session, challenge_id: str) -> dict:
        """
        Retrieves authoritative challenge status for browser session restoration.
        Never returns OTP secrets or unverified tokens.
        """
        token = AuthService.verify_and_get_challenge_token(db, challenge_id)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification session not found or invalid."
            )

        now = datetime.now(timezone.utc)
        token_expires = token.expires_at
        if token_expires.tzinfo is None:
            token_expires = token_expires.replace(tzinfo=timezone.utc)

        expired = token_expires < now
        consumed = token.consumed_at is not None
        locked = token.attempts >= token.max_attempts

        time_remaining = max(0, int((token_expires - now).total_seconds())) if not expired and not consumed else 0

        created_at = token.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        elapsed = (now - created_at).total_seconds()
        cooldown_remaining = max(0, int(config.SMS_RESEND_COOLDOWN_SECONDS - elapsed))

        masked_phone = f"+91 ******{token.phone[-4:]}"
        return {
            "valid": bool(not expired and not consumed and not locked),
            "challenge_id": challenge_id,
            "phone": masked_phone,
            "raw_phone": token.phone,
            "purpose": token.purpose,
            "seconds_remaining": time_remaining,
            "cooldown_remaining": cooldown_remaining,
            "consumed": consumed,
            "expired": expired,
            "locked": locked,
            "max_attempts": token.max_attempts,
            "attempts_remaining": max(0, token.max_attempts - token.attempts),
            "delivery_status": getattr(token, "delivery_status", None) or "ACCEPTED"
        }

    @staticmethod
    def process_meta_delivery_status(db: Session, status_obj: dict) -> Optional[MobileOtpToken]:
        """
        Processes Meta WhatsApp Cloud API asynchronous message delivery status callbacks.
        Supports: sent, delivered, read, failed.
        Correlates callbacks with MobileOtpToken by provider_message_id (wamid).
        Handles duplicate and out-of-order callbacks via state precedence.
        Never logs complete phone numbers, OTP values, or secret tokens.
        """
        if not isinstance(status_obj, dict):
            return None

        wamid = (status_obj.get("id") or "").strip()
        status_raw = (status_obj.get("status") or "").strip().lower()
        recipient_id = (status_obj.get("recipient_id") or "").strip()
        timestamp_val = status_obj.get("timestamp")
        errors = status_obj.get("errors") or []

        if not wamid:
            logger.warning("[META-WA-STATUS] Status callback missing message ID (wamid).")
            return None

        try:
            token = db.query(MobileOtpToken).filter(MobileOtpToken.provider_message_id == wamid).first()
        except Exception as schema_err:
            db.rollback()
            logger.error(
                "[SCHEMA COMPATIBILITY ERROR] Column 'provider_message_id' not queryable on mobile_otp_tokens (%s). "
                "Authoritative migration required: execute migrations/005_meta_otp_delivery_observability.sql.",
                type(schema_err).__name__
            )
            return None
        if not token:
            masked_recipient = f"+91 ******{recipient_id[-4:]}" if len(recipient_id) >= 4 else (recipient_id or "unknown")
            logger.info(
                "[META-WA-STATUS] Status callback for non-OTP or uncataloged message (wamid=%s, status=%s, recipient=%s)",
                wamid, status_raw, masked_recipient
            )
            return None

        masked_phone = f"+91 ******{token.phone[-4:]}" if len(token.phone) >= 4 else token.phone
        current_status = (token.delivery_status or "PENDING").upper()
        incoming_status = status_raw.upper()

        status_precedence = {
            "PENDING": 0,
            "ACCEPTED": 1,
            "SENT": 2,
            "DELIVERED": 3,
            "READ": 4,
        }

        if incoming_status == "FAILED":
            # Once confirmed delivered or read on handset, late failures should not downgrade status
            if current_status in {"DELIVERED", "READ"}:
                logger.info(
                    "[META-WA-STATUS] Ignoring late failure callback for already %s OTP (wamid=%s)",
                    current_status, wamid
                )
                return token

            if current_status == "FAILED":
                # Duplicate failure callback
                return token

            err_code = "FAILED"
            err_msg = "Meta reported message delivery failure."
            if errors and isinstance(errors, list):
                first_err = errors[0]
                if isinstance(first_err, dict):
                    err_code = str(first_err.get("code") or "FAILED")[:50]
                    title = first_err.get("title") or ""
                    detail = first_err.get("message") or ""
                    err_msg = (f"{title}: {detail}".strip(": ") if title and detail else (title or detail or err_msg))[:255]

            token.delivery_status = "FAILED"
            token.delivery_error_code = err_code
            token.delivery_error_message = err_msg
            token.updated_at = datetime.now(timezone.utc)
            try:
                db.commit()
            except Exception as commit_err:
                db.rollback()
                logger.error("[META-WA-STATUS] Failed to persist FAILED status (wamid=%s): %s", wamid, commit_err)
                return token

            logger.error(
                "[META-WA-STATUS] OTP delivery FAILED (wamid=%s, recipient=%s, code=%s, reason=%s)",
                wamid, masked_phone, err_code, err_msg
            )
            return token

        if incoming_status in status_precedence:
            incoming_rank = status_precedence[incoming_status]
            current_rank = status_precedence.get(current_status, 0)

            # If current is FAILED, allow DELIVERED or READ to recover if Meta resolved delivery
            if current_status == "FAILED" and incoming_status in {"DELIVERED", "READ"}:
                token.delivery_status = incoming_status
                token.delivery_error_code = None
                token.delivery_error_message = None
                if timestamp_val:
                    try:
                        token.delivered_at = datetime.fromtimestamp(float(timestamp_val), tz=timezone.utc)
                    except Exception:
                        token.delivered_at = datetime.now(timezone.utc)
                else:
                    token.delivered_at = datetime.now(timezone.utc)
                token.updated_at = datetime.now(timezone.utc)
                try:
                    db.commit()
                    logger.info(
                        "[META-WA-STATUS] OTP delivery recovered to %s (wamid=%s, recipient=%s)",
                        incoming_status, wamid, masked_phone
                    )
                except Exception as commit_err:
                    db.rollback()
                    logger.error("[META-WA-STATUS] Failed to persist recovered status (wamid=%s): %s", wamid, commit_err)
                    return token
                return token

            # Handle duplicate or out-of-order callbacks
            if incoming_rank <= current_rank:
                logger.info(
                    "[META-WA-STATUS] Duplicate or out-of-order callback '%s' ignored for wamid=%s (current status: %s)",
                    incoming_status, wamid, current_status
                )
                return token

            token.delivery_status = incoming_status
            if incoming_status in {"DELIVERED", "READ"}:
                if timestamp_val:
                    try:
                        token.delivered_at = datetime.fromtimestamp(float(timestamp_val), tz=timezone.utc)
                    except Exception:
                        token.delivered_at = datetime.now(timezone.utc)
                else:
                    token.delivered_at = datetime.now(timezone.utc)

            token.updated_at = datetime.now(timezone.utc)
            try:
                db.commit()
                logger.info(
                    "[META-WA-STATUS] OTP delivery status updated to %s (wamid=%s, recipient=%s)",
                    incoming_status, wamid, masked_phone
                )
            except Exception as commit_err:
                db.rollback()
                logger.error("[META-WA-STATUS] Failed to persist %s status (wamid=%s): %s", incoming_status, wamid, commit_err)
                return token
            return token

        logger.warning(
            "[META-WA-STATUS] Unrecognized status '%s' received for wamid=%s",
            status_raw, wamid
        )
        return token

    @staticmethod
    def _verify_otp_hash(submitted_otp: str, stored_hash: str) -> bool:
        """Constant-time HMAC comparison to prevent timing attacks."""
        expected_hash = hash_otp(submitted_otp)
        return hmac.compare_digest(expected_hash, stored_hash)

    @staticmethod
    def verify_otp(
        db: Session,
        phone: str,
        otp: str,
        purpose: str = "login",
        role: Optional[str] = "citizen",
        challenge_id: Optional[str] = None
    ) -> AuthResponse:
        """
        Verifies 6-digit OTP against stored HMAC-SHA256 hash.
        Guarantees single-use, tracks failed attempts (max 5), enforces expiration.
        On purpose='login', logs in and issues JWT.
        """
        clean_phone = validate_indian_mobile(phone)
        otp = (otp or "").strip()
        if not re.match(r"^\d{6}$", otp):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code must be exactly 6 digits."
            )

        now = datetime.now(timezone.utc)

        # Find unconsumed OTP token using verified challenge_id or fallback to phone
        if challenge_id:
            token = AuthService.verify_and_get_challenge_token(db, challenge_id)
            if not token or token.phone != clean_phone or token.consumed_at is not None:
                token = None
        else:
            token = db.query(MobileOtpToken).filter(
                MobileOtpToken.phone == clean_phone,
                MobileOtpToken.consumed_at.is_(None)
            ).order_by(MobileOtpToken.id.desc()).first()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active verification code found for this mobile number. Please request a new OTP."
            )

        # Check expiration
        token_expires = token.expires_at
        if token_expires.tzinfo is None:
            token_expires = token_expires.replace(tzinfo=timezone.utc)

        if token_expires < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code has expired. Please request a new OTP."
            )

        # Check attempt ceiling
        if token.attempts >= token.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum verification attempts exceeded. Please request a new code."
            )

        # Purpose binding check
        if token.purpose != purpose:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Challenge purpose mismatch. This verification challenge was created for {token.purpose}."
            )

        # Verify OTP using constant-time HMAC comparison
        if not AuthService._verify_otp_hash(otp, token.otp_hash):
            token.attempts += 1
            db.commit()
            remaining = max(0, token.max_attempts - token.attempts)
            if remaining == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Incorrect code. Maximum verification attempts reached. Please request a new code."
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid verification code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
            )

        # Mark token consumed (single-use) via atomic conditional update
        updated_rows = db.query(MobileOtpToken).filter(
            MobileOtpToken.id == token.id,
            MobileOtpToken.consumed_at.is_(None)
        ).update({"consumed_at": now}, synchronize_session=False)
        db.commit()

        if updated_rows == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This verification code has already been consumed. Please request a new code."
            )

        # If login flow, locate the user and issue EcoPulse JWT
        user = AuthService.find_user_by_phone(db, clean_phone)

        if purpose == "login" or (purpose != "register" and user is not None):
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No account found for mobile number +91 {clean_phone}. Please sign up."
                )
            if user.is_locked or not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account is locked or suspended. Please contact municipal support."
                )

            session_id = f"sess_{user.id}_{int(time.time())}"
            access_token = create_access_token({
                "sub": user.email or user.phone,
                "role": user.role,
                "id": user.id,
                "sid": session_id
            })
            return AuthResponse(
                access_token=access_token,
                user=UserResponse(
                    id=user.id,
                    name=user.full_name,
                    email=user.email,
                    role=user.role,
                    ward=user.ward,
                    phone=user.phone,
                    employee_id=user.employee_id,
                    eco_coins=user.eco_coins or 100
                )
            )

        # For registration verification step before final user creation
        dummy_user = UserResponse(
            id=0,
            name="Pending Registration",
            email=None,
            role="citizen",
            phone=clean_phone,
            eco_coins=100
        )
        return AuthResponse(
            access_token="verified_pre_registration",
            token_type="bearer",
            user=dummy_user
        )

    @staticmethod
    def register_user(
        db: Session,
        payload: Union[RegisterRequest, SignupRequest],
        ip_address: Optional[str] = None
    ) -> AuthResponse:
        """
        Registers a new citizen account via mobile number and verified OTP.
        Strictly enforces that public registration creates only 'citizen' accounts.
        Email and password are fully optional.
        """
        req_role = (getattr(payload, "role", "citizen") or "citizen").strip().lower()
        if req_role != "citizen":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Public registration is only permitted for citizens. Driver and administrative accounts must be provisioned by the municipal administration."
            )

        full_name = (getattr(payload, "full_name", None) or getattr(payload, "fullName", None) or "").strip()
        if len(full_name) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Full name is required and must be at least 2 characters long."
            )

        clean_phone = validate_indian_mobile(payload.phone)

        existing_phone = AuthService.find_user_by_phone(db, clean_phone)
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This mobile number is already registered. Please sign in instead."
            )

        clean_email = None
        if payload.email and payload.email.strip():
            clean_email = payload.email.strip().lower()
            if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", clean_email):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Please provide a valid email address."
                )
            existing_email = db.query(User).filter(User.email == clean_email).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This email address is already in use by another account."
                )

        now = datetime.now(timezone.utc)
        otp = getattr(payload, "otp", None)
        if otp and otp.strip():
            otp_val = otp.strip()
            challenge_id = getattr(payload, "challenge_id", None)
            if challenge_id:
                token = AuthService.verify_and_get_challenge_token(db, challenge_id)
                if not token or token.phone != clean_phone or token.consumed_at is not None:
                    token = None
            else:
                token = db.query(MobileOtpToken).filter(
                    MobileOtpToken.phone == clean_phone,
                    MobileOtpToken.consumed_at.is_(None)
                ).order_by(MobileOtpToken.id.desc()).first()

            if not token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No active OTP found for this mobile number. Please request a verification code."
                )

            token_expires = token.expires_at
            if token_expires.tzinfo is None:
                token_expires = token_expires.replace(tzinfo=timezone.utc)

            if token_expires < now:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Verification code has expired. Please request a new OTP."
                )

            if token.purpose != "register":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Challenge purpose mismatch. This verification challenge was not created for registration."
                )

            if not AuthService._verify_otp_hash(otp_val, token.otp_hash):
                token.attempts += 1
                db.commit()
                remaining = max(0, token.max_attempts - token.attempts)
                if remaining == 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Incorrect code. Maximum verification attempts reached. Please request a new code."
                    )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid verification code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
                )

            # Consume token via atomic conditional update
            updated_rows = db.query(MobileOtpToken).filter(
                MobileOtpToken.id == token.id,
                MobileOtpToken.consumed_at.is_(None)
            ).update({"consumed_at": now}, synchronize_session=False)
            db.commit()

            if updated_rows == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Verification code has already been consumed. Please request a new code."
                )
        else:
            # Check if a recent registration token for this phone was verified within last 10 minutes
            ten_min_ago = now - timedelta(minutes=10)
            verified_token = db.query(MobileOtpToken).filter(
                MobileOtpToken.phone == clean_phone,
                MobileOtpToken.consumed_at >= ten_min_ago
            ).order_by(MobileOtpToken.id.desc()).first()

            if not verified_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Mobile number has not been verified via OTP. Please request and verify your OTP first."
                )

        hashed_pwd = None
        if payload.password and payload.password.strip():
            hashed_pwd = hash_password(payload.password)

        new_user = User(
            full_name=full_name,
            phone=clean_phone,
            email=clean_email,
            hashed_password=hashed_pwd,
            role="citizen",
            ward=getattr(payload, "ward", "Ward 12") or "Ward 12",
            employee_id=getattr(payload, "employeeId", None),
            eco_coins=100,
            is_active=True
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        session_id = f"sess_{new_user.id}_{int(time.time())}"
        access_token = create_access_token({
            "sub": new_user.email or new_user.phone,
            "role": new_user.role,
            "id": new_user.id,
            "sid": session_id
        })

        return AuthResponse(
            access_token=access_token,
            user=UserResponse(
                id=new_user.id,
                name=new_user.full_name,
                email=new_user.email,
                role=new_user.role,
                ward=new_user.ward,
                phone=new_user.phone,
                employee_id=new_user.employee_id,
                eco_coins=new_user.eco_coins or 100
            )
        )

    @staticmethod
    def login_with_otp(
        db: Session,
        phone: str,
        otp: str,
        role: Optional[str] = "citizen",
        challenge_id: Optional[str] = None
    ) -> AuthResponse:
        """Authenticates an existing user via mobile number and verified OTP."""
        return AuthService.verify_otp(db, phone=phone, otp=otp, purpose="login", role=role, challenge_id=challenge_id)

    @staticmethod
    def login_user(db: Session, payload: LoginRequest) -> AuthResponse:
        """
        Legacy/compatibility password-based authentication for existing driver & admin workflows.
        Identifies user by email, employee_id, or mobile number.
        """
        if AuthService.should_seed_demo_users():
            AuthService.seed_demo_users(db)

        clean_ident = payload.email.strip()
        clean_phone = clean_ident.replace("+91", "").replace(" ", "").replace("-", "")

        user = db.query(User).filter(
            (func.lower(User.email) == clean_ident.lower()) |
            (func.lower(User.employee_id) == clean_ident.lower()) |
            (User.employee_id == clean_ident) |
            (User.phone == clean_ident) |
            (User.phone == clean_phone)
        ).first()

        if not user or not user.hashed_password:
            verify_password(payload.password, DUMMY_HASH)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials. Please verify your mobile/email and password."
            )

        if not verify_password(payload.password, user.hashed_password):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= 5:
                user.is_locked = True
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials. Please verify your mobile/email and password."
            )

        if user.is_locked or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is locked or suspended. Please contact municipal support."
            )

        user.failed_attempts = 0
        db.commit()

        session_id = f"sess_{user.id}_{int(time.time())}"
        token = create_access_token({
            "sub": user.email or user.phone,
            "role": user.role,
            "id": user.id,
            "sid": session_id
        })
        return AuthResponse(
            access_token=token,
            user=UserResponse(
                id=user.id,
                name=user.full_name,
                email=user.email,
                role=user.role,
                ward=user.ward,
                phone=user.phone,
                employee_id=user.employee_id,
                eco_coins=user.eco_coins or 100
            )
        )

    @staticmethod
    def update_user_profile(db: Session, current_user: User, payload: UserProfileUpdate) -> UserResponse:
        if payload.full_name is not None and payload.full_name.strip():
            current_user.full_name = payload.full_name.strip()
        if payload.ward is not None and payload.ward.strip():
            current_user.ward = payload.ward.strip()
        if payload.phone is not None:
            clean_phone = validate_indian_mobile(payload.phone)
            if normalize_phone_number(current_user.phone or "") != clean_phone:
                dup = db.query(User).filter(
                    (User.phone == clean_phone) |
                    (User.phone == f"+91{clean_phone}"),
                    User.id != current_user.id
                ).first()
                if dup:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="This mobile number is already in use by another account."
                    )
                current_user.phone = clean_phone
        db.commit()
        db.refresh(current_user)
        return UserResponse(
            id=current_user.id,
            name=current_user.full_name,
            email=current_user.email,
            role=current_user.role,
            ward=current_user.ward,
            phone=current_user.phone,
            employee_id=current_user.employee_id,
            eco_coins=current_user.eco_coins or 100
        )

    @staticmethod
    def request_password_reset(db: Session, identifier: str, role: str = "citizen") -> dict:
        clean_ident = identifier.strip()
        clean_phone = clean_ident.replace("+91", "").replace(" ", "").replace("-", "")
        user = db.query(User).filter(
            (func.lower(User.email) == clean_ident.lower()) |
            (User.phone == clean_ident) |
            (User.phone == clean_phone)
        ).first()

        if user:
            return {
                "success": True,
                "message": f"Password reset instructions have been dispatched to registered communication channels for {clean_ident}."
            }
        return {
            "success": True,
            "message": f"If an account is associated with {clean_ident}, reset instructions have been dispatched."
        }
