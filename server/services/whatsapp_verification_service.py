"""
WhatsAppVerificationService — Website-Generated WhatsApp Registration Verification.

Security & Architectural Principles:
1. Citizen enters profile details on website.
2. Backend generates a cryptographically secure 6-digit verification code.
3. Plaintext code and high-entropy challenge secret (256 bits) are returned ONLY to
   the originating website registration response and never stored in plaintext.
4. Only HMAC-SHA256(code) (otp_hash) and SHA-256(challenge_secret) (secret_hash) are persisted.
5. Possession of challenge_id alone CANNOT retrieve a JWT session.
   A separate challenge_secret provided in X-Challenge-Secret header is required.
6. Single-use session issuance: once claimed, challenge is marked CONSUMED and cannot be re-issued.
7. Official WhatsApp Business phone number is strictly loaded from validated server configuration.
8. Challenge is bound strictly to the submitted 10-digit Indian mobile number.
9. Inbound WhatsApp webhook receives the message, normalizes sender phone, and verifies code.
10. Registration is completed atomically without duplicate user creation.
11. Never logs OTPs, challenge secrets, or JWT tokens.
"""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from typing import Optional, Dict, Any, Tuple

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server.models.user import User
from server.models.whatsapp_registration_challenge import WhatsAppRegistrationChallenge
from server.models.whatsapp_session import WhatsAppCitizen
from server.schemas.auth import UserResponse
from server.services.auth_service import hash_otp, validate_indian_mobile, hash_password
from server.utils.config import config
from server.utils.security import create_access_token, get_jwt_secret

logger = logging.getLogger(__name__)

CHALLENGE_TTL_SECONDS = 300          # 5 minutes
RESEND_COOLDOWN_SECONDS = 60         # 60 seconds
MAX_CHALLENGES_PER_WINDOW = 5        # max 5 requests per 15 minutes per phone
MAX_ATTEMPTS = 5                     # max 5 verification attempts per challenge


def _hash_secret(secret_str: str) -> str:
    """Return lowercase hex SHA-256 of high-entropy challenge secret."""
    return hashlib.sha256(secret_str.encode("utf-8")).hexdigest()


class WhatsAppVerificationService:

    @staticmethod
    def get_validated_business_phone() -> str:
        """
        Retrieves and validates the official WhatsApp Business phone number from configuration.
        Ensures a single canonical configuration source without hardcoded fallback defaults.
        """
        raw = (config.WHATSAPP_BUSINESS_PHONE or "").strip()
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Official WhatsApp Business phone number is not configured on the server."
            )
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configured WhatsApp Business phone number is invalid."
            )
        return raw

    @staticmethod
    def format_business_phone() -> str:
        """Returns clean formatted WhatsApp business phone for user-facing instructions."""
        raw = WhatsAppVerificationService.get_validated_business_phone()
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 12 and digits.startswith("91"):
            return f"+91 {digits[2:7]} {digits[7:]}"
        elif len(digits) == 10:
            return f"+91 {digits[:5]} {digits[5:]}"
        return raw

    @staticmethod
    def get_raw_business_phone() -> str:
        """Returns unspaced digits-only phone for wa.me deep links (e.g. 919876543210)."""
        raw = WhatsAppVerificationService.get_validated_business_phone()
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 10:
            digits = "91" + digits
        return digits

    @staticmethod
    def create_challenge_id(challenge_id: int, phone: str, expires_at: datetime, purpose: str = "citizen_registration") -> str:
        """Generates an HMAC-SHA256 signed tamper-proof challenge identifier."""
        exp_ts = int(expires_at.timestamp())
        payload = f"{challenge_id}:{phone}:{purpose}:{exp_ts}"
        secret = get_jwt_secret()
        sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
        raw = f"{payload}:{sig}"
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")

    @staticmethod
    def verify_and_get_challenge(db: Session, challenge_token: str) -> Optional[WhatsAppRegistrationChallenge]:
        """Validates the challenge HMAC signature and retrieves the corresponding database record."""
        try:
            raw = base64.urlsafe_b64decode(challenge_token.encode("utf-8")).decode("utf-8")
            parts = raw.split(":")
            if len(parts) != 5:
                return None
            id_str, phone, purpose, exp_ts_str, sig = parts
            payload = f"{id_str}:{phone}:{purpose}:{exp_ts_str}"
            secret = get_jwt_secret()
            expected_sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]
            if not hmac.compare_digest(sig, expected_sig):
                return None

            cid = int(id_str)
            challenge = db.query(WhatsAppRegistrationChallenge).filter(WhatsAppRegistrationChallenge.id == cid).first()
            if not challenge or challenge.phone != phone:
                return None
            return challenge
        except Exception:
            return None

    @staticmethod
    def generate_verification_challenge(
        db: Session,
        phone: str,
        full_name: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        ward: Optional[str] = "Ward 12",
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates a website verification code for WhatsApp-based citizen registration.
        Does NOT dispatch any outbound SMS or WhatsApp message.
        Returns the plaintext code and challenge secret once in the response.
        Never logs OTPs or challenge secrets.
        """
        clean_phone = validate_indian_mobile(phone)
        full_name = full_name.strip()
        if len(full_name) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please enter your full name (minimum 2 characters)."
            )

        clean_email = email.strip().lower() if email and email.strip() else None
        now = datetime.now(timezone.utc)

        # 0. Pre-flight check: ensure official WhatsApp business number is configured on server
        business_phone = WhatsAppVerificationService.format_business_phone()

        # 1. Check if user already exists
        existing_user = db.query(User).filter(User.phone == clean_phone).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This mobile number is already registered. Please sign in instead."
            )

        if clean_email:
            existing_email = db.query(User).filter(User.email == clean_email).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This email address is already in use by another account."
                )

        # 2. Resend Cooldown Check (60 seconds)
        cooldown_window = now - timedelta(seconds=RESEND_COOLDOWN_SECONDS)
        recent_challenge = db.query(WhatsAppRegistrationChallenge).filter(
            WhatsAppRegistrationChallenge.phone == clean_phone,
            WhatsAppRegistrationChallenge.created_at >= cooldown_window
        ).order_by(WhatsAppRegistrationChallenge.id.desc()).first()

        if recent_challenge:
            created_at = recent_challenge.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            elapsed = (now - created_at).total_seconds()
            remaining = max(1, int(RESEND_COOLDOWN_SECONDS - elapsed))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} seconds before generating a new verification code."
            )

        # 3. Mobile Rate Limit Check (5 requests per 15 minutes)
        fifteen_min_ago = now - timedelta(minutes=15)
        mobile_count = db.query(WhatsAppRegistrationChallenge).filter(
            WhatsAppRegistrationChallenge.phone == clean_phone,
            WhatsAppRegistrationChallenge.created_at >= fifteen_min_ago
        ).count()
        if mobile_count >= MAX_CHALLENGES_PER_WINDOW:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many verification requests for this mobile number. Please try again after 15 minutes."
            )

        # 4. IP Rate Limit Check (15 requests per 15 minutes)
        if ip_address:
            ip_count = db.query(WhatsAppRegistrationChallenge).filter(
                WhatsAppRegistrationChallenge.ip_address == ip_address,
                WhatsAppRegistrationChallenge.created_at >= fifteen_min_ago
            ).count()
            if ip_count >= 15:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests from this network. Please try again later."
                )

        # 5. Invalidate previous pending challenges for this mobile number
        db.query(WhatsAppRegistrationChallenge).filter(
            WhatsAppRegistrationChallenge.phone == clean_phone,
            WhatsAppRegistrationChallenge.status == "PENDING"
        ).update({"status": "EXPIRED", "consumed_at": now}, synchronize_session=False)

        # 6. Generate cryptographically secure 6-digit OTP and HMAC-SHA256 hash
        code = f"{secrets.randbelow(1000000):06d}"
        otp_hash = hash_otp(code)
        expires_at = now + timedelta(seconds=CHALLENGE_TTL_SECONDS)

        # 7. Generate high-entropy 256-bit challenge secret (authorization key for JWT issuance)
        challenge_secret = secrets.token_urlsafe(32)
        secret_hash = _hash_secret(challenge_secret)

        # Hash password if provided
        pwd_hash = hash_password(password) if password and password.strip() else None

        profile_data = {
            "full_name": full_name,
            "email": clean_email,
            "password_hash": pwd_hash,
            "ward": ward or "Ward 12",
        }

        challenge = WhatsAppRegistrationChallenge(
            phone=clean_phone,
            otp_hash=otp_hash,
            secret_hash=secret_hash,
            purpose="citizen_registration",
            profile_data=json.dumps(profile_data),
            attempts=0,
            max_attempts=MAX_ATTEMPTS,
            status="PENDING",
            expires_at=expires_at,
            ip_address=ip_address,
        )
        db.add(challenge)
        db.commit()
        db.refresh(challenge)

        challenge_token = WhatsAppVerificationService.create_challenge_id(challenge.id, clean_phone, expires_at)
        masked_phone = f"+91 ******{clean_phone[-4:]}"

        logger.info(
            "[WHATSAPP-REG] Verification challenge created for %s (challenge_id=%d, expires=%s). Secrets not logged.",
            masked_phone, challenge.id, expires_at.isoformat()
        )

        return {
            "success": True,
            "challenge_id": challenge_token,
            "challenge_secret": challenge_secret,
            "code": code,
            "whatsapp_number": business_phone,
            "verification_command": f"VERIFY {code}",
            "instructions": f"Send VERIFY {code} to {business_phone} from your WhatsApp account.",
            "expires_in": CHALLENGE_TTL_SECONDS,
            "expires_at": expires_at.isoformat(),
            "cooldown_seconds": RESEND_COOLDOWN_SECONDS,
            "phone_masked": masked_phone,
        }

    @staticmethod
    def process_verification_message(
        db: Session,
        sender_phone: str,
        raw_code: str,
        preferred_language: str = "mr"
    ) -> Dict[str, Any]:
        """
        Processes an incoming `VERIFY <code>` WhatsApp message from the webhook.
        Validates the code against active registration challenges for the normalized sender number.
        Atomically marks the challenge VERIFIED and creates the canonical User.
        """
        # Normalize sender phone to 10-digit Indian mobile
        clean_sender = re.sub(r"\D", "", sender_phone or "")
        if clean_sender.startswith("91") and len(clean_sender) == 12:
            clean_sender = clean_sender[2:]
        elif clean_sender.startswith("0") and len(clean_sender) == 11:
            clean_sender = clean_sender[1:]

        if len(clean_sender) != 10:
            reply = (
                "⚠️ अवैध मोबाईल क्रमांक. कृपया वैध भारतीय मोबाईल क्रमांकावरून संदेश पाठवा."
                if preferred_language == "mr"
                else "⚠️ Invalid mobile number. Please send from a valid 10-digit Indian mobile."
            )
            return {"status": "invalid_sender", "reply": reply, "verified": False}

        raw_code = (raw_code or "").strip()
        if not re.match(r"^\d{6}$", raw_code):
            reply = (
                "⚠️ कृपया योग्य 6-अंकी पडताळणी कोड पाठवा.\nउदा: *VERIFY 123456*"
                if preferred_language == "mr"
                else "⚠️ Please send a valid 6-digit verification code.\nExample: *VERIFY 123456*"
            )
            return {"status": "invalid_format", "reply": reply, "verified": False}

        now = datetime.now(timezone.utc)

        # Query active challenge strictly associated with this sender's phone
        challenge = db.query(WhatsAppRegistrationChallenge).filter(
            WhatsAppRegistrationChallenge.phone == clean_sender,
            WhatsAppRegistrationChallenge.status.in_(["PENDING", "VERIFIED"])
        ).order_by(WhatsAppRegistrationChallenge.id.desc()).first()

        if not challenge:
            frontend_url = getattr(config, "FRONTEND_URL", "https://ecopulse-ai-frontend.onrender.com/").rstrip("/")
            reply = (
                f"⚠️ या WhatsApp क्रमांकासाठी कोणतीही नोंदणी पडताळणी प्रलंबित नाही.\n\n"
                f"कृपया प्रथम वेबसाइटवर नागरिक नोंदणी सुरू करा:\n🌐 {frontend_url}/signup"
                if preferred_language == "mr"
                else f"⚠️ No active registration verification found for this WhatsApp number.\n\n"
                     f"Please first start registration on the EcoPulse AI website:\n🌐 {frontend_url}/signup"
            )
            return {"status": "no_challenge", "reply": reply, "verified": False}

        # Idempotent replay handling: if already VERIFIED with user created
        if challenge.status == "VERIFIED":
            user = db.query(User).filter(User.phone == clean_sender).first()
            user_name = user.full_name if user else "Citizen"
            reply = (
                f"✅ *इकोपल्स AI — मोबाईल नंबर आधीच पडताळला गेला आहे!*\n\n"
                f"नमस्कार {user_name}! आपले खाते आधीच यशस्वीरित्या पडताळले गेले आहे.\n"
                f"कृपया वेबसाइटवर सुरू ठेवा."
                if preferred_language == "mr"
                else f"✅ *EcoPulse AI — Mobile Number Already Verified!*\n\n"
                     f"Hello {user_name}! Your account has already been verified.\n"
                     f"Please return to the website to continue."
            )
            return {"status": "already_verified", "reply": reply, "verified": True, "challenge_id": challenge.id}

        # Check expiration
        exp = challenge.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            challenge.status = "EXPIRED"
            db.commit()
            reply = (
                "⏳ आपला पडताळणी कोड कालबाह्य (expired) झाला आहे. कृपया वेबसाइटवर नवीन कोड मिळवा."
                if preferred_language == "mr"
                else "⏳ Your verification code has expired. Please request a new code on the website."
            )
            return {"status": "expired", "reply": reply, "verified": False}

        # Check attempt ceiling
        if challenge.attempts >= challenge.max_attempts:
            challenge.status = "FAILED"
            db.commit()
            reply = (
                "🚫 कमाल पडताळणी मर्यादा ओलांडली आहे. कृपया वेबसाइटवर नवीन कोड मिळवा."
                if preferred_language == "mr"
                else "🚫 Maximum verification attempts reached. Please request a new code on the website."
            )
            return {"status": "locked", "reply": reply, "verified": False}

        # Constant-time HMAC comparison
        expected_hash = hash_otp(raw_code)
        if not hmac.compare_digest(expected_hash, challenge.otp_hash):
            challenge.attempts += 1
            if challenge.attempts >= challenge.max_attempts:
                challenge.status = "FAILED"
            db.commit()
            remaining = max(0, challenge.max_attempts - challenge.attempts)
            reply = (
                f"⚠️ अयोग्य पडताळणी कोड. {remaining} प्रयत्न शिल्लक आहेत."
                if preferred_language == "mr"
                else f"⚠️ Incorrect verification code. {remaining} attempt(s) remaining."
            )
            return {"status": "invalid_code", "reply": reply, "verified": False}

        # Code is VALID: Atomic transition to VERIFIED (only winning thread proceeds to provision user)
        updated_rows = db.query(WhatsAppRegistrationChallenge).filter(
            WhatsAppRegistrationChallenge.id == challenge.id,
            WhatsAppRegistrationChallenge.status == "PENDING"
        ).update({"status": "VERIFIED", "verified_at": now}, synchronize_session=False)
        db.commit()

        if updated_rows == 0:
            # Another concurrent thread or webhook event already claimed and verified this challenge
            user = db.query(User).filter(User.phone == clean_sender).first()
            user_name = user.full_name if user else "Citizen"
            reply = (
                f"✅ *इकोपल्स AI — मोबाईल नंबर आधीच पडताळला गेला आहे!*\n\n"
                f"नमस्कार {user_name}! आपले खाते आधीच यशस्वीरित्या पडताळले गेले आहे.\n"
                f"कृपया वेबसाइटवर सुरू ठेवा."
                if preferred_language == "mr"
                else f"✅ *EcoPulse AI — Mobile Number Already Verified!*\n\n"
                     f"Hello {user_name}! Your account has already been verified.\n"
                     f"Please return to the website to continue."
            )
            return {"status": "already_verified", "reply": reply, "verified": True, "challenge_id": challenge.id}

        # Create or link canonical User
        profile = challenge.get_profile()
        full_name = profile.get("full_name") or "Dhule Citizen"
        email = profile.get("email")
        password_hash = profile.get("password_hash")
        ward = profile.get("ward") or "Ward 12"

        user = db.query(User).filter(User.phone == clean_sender).first()
        if not user:
            try:
                user = User(
                    full_name=full_name,
                    phone=clean_sender,
                    email=email,
                    hashed_password=password_hash,
                    role="citizen",
                    ward=ward,
                    eco_coins=100,
                    is_active=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            except IntegrityError:
                db.rollback()
                user = db.query(User).filter(User.phone == clean_sender).first()

        if user:
            challenge.user_id = user.id

            # Link WhatsAppCitizen identity
            norm_full_phone = "91" + clean_sender
            citizen = db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == norm_full_phone).first()
            if not citizen:
                citizen = WhatsAppCitizen(
                    phone_number=norm_full_phone,
                    full_name=user.full_name,
                    ward=user.ward,
                    is_authorized=True,
                    user_id=user.id,
                    preferred_language=preferred_language
                )
                db.add(citizen)
            else:
                citizen.user_id = user.id
                citizen.is_authorized = True
                citizen.full_name = user.full_name

        db.commit()

        logger.info(
            "[WHATSAPP-REG] Challenge #%d VERIFIED successfully via WhatsApp for phone +91 ******%s (user_id=%s)",
            challenge.id, clean_sender[-4:], user.id if user else "none"
        )

        reply = (
            f"✅ *इकोपल्स AI — मोबाईल नंबर पडताळणी यशस्वी!*\n\n"
            f"नमस्कार {user.full_name if user else 'नागरिक'}! 🎉 आपले खाते यशस्वीरित्या सक्रिय झाले आहे.\n\n"
            f"कृपया आपल्या ब्राउझर / वेबसाइटवर जा, आपले Citizen Dashboard आपोआप सुरू होईल!"
            if preferred_language == "mr"
            else f"✅ *EcoPulse AI — Verification Successful!*\n\n"
                 f"Hello {user.full_name if user else 'Citizen'}! 🎉 Your mobile number +91 {clean_sender} is verified.\n\n"
                 f"Please return to the website, your Citizen Dashboard will open automatically!"
        )

        return {
            "status": "verified",
            "reply": reply,
            "verified": True,
            "challenge_id": challenge.id,
            "user_id": user.id if user else None
        }

    @staticmethod
    def get_challenge_status(
        db: Session,
        challenge_token: str,
        challenge_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Authoritative polling endpoint for website registration session.
        Never discloses OTP secrets or database keys.
        SECURITY ENFORCEMENT:
        - Possession of challenge_token alone reveals ONLY status (PENDING / VERIFIED).
        - A valid challenge_secret matching secret_hash is REQUIRED to claim the EcoPulse JWT.
        - Once claimed, challenge status transitions to CONSUMED (one-time session issuance).
        """
        challenge = WhatsAppVerificationService.verify_and_get_challenge(db, challenge_token)
        if not challenge:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification session not found or invalid."
            )

        now = datetime.now(timezone.utc)
        exp = challenge.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)

        # Auto-expire if time passed and still pending
        if challenge.status == "PENDING" and exp < now:
            challenge.status = "EXPIRED"
            db.commit()

        time_remaining = max(0, int((exp - now).total_seconds())) if challenge.status == "PENDING" else 0
        masked_phone = f"+91 ******{challenge.phone[-4:]}"
        try:
            business_phone = WhatsAppVerificationService.format_business_phone()
        except Exception:
            business_phone = ""

        # If VERIFIED: check if challenge_secret is presented to claim session
        if challenge.status == "VERIFIED":
            if not challenge_secret:
                # Safe status response without JWT: verifies status without exposing session
                return {
                    "status": "VERIFIED",
                    "verified": True,
                    "consumed": False,
                    "expired": False,
                    "phone_masked": masked_phone,
                    "seconds_remaining": 0,
                    "whatsapp_number": business_phone,
                    "access_token": None,
                    "token_type": None,
                    "user": None,
                    "message": "Mobile number verified on WhatsApp. Awaiting authorized session claim."
                }

            # Secret presented: verify against stored secret_hash using constant-time comparison
            provided_hash = _hash_secret(challenge_secret.strip())
            if not challenge.secret_hash or not hmac.compare_digest(provided_hash, challenge.secret_hash):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid or unauthorized challenge secret. Session cannot be issued."
                )

            # Atomic one-time session issuance: mark challenge CONSUMED
            updated = db.query(WhatsAppRegistrationChallenge).filter(
                WhatsAppRegistrationChallenge.id == challenge.id,
                WhatsAppRegistrationChallenge.status == "VERIFIED"
            ).update({"status": "CONSUMED", "consumed_at": now}, synchronize_session=False)
            db.commit()

            if updated == 0:
                # Concurrent claim won the race
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This verification session has already been claimed."
                )

            user = None
            if challenge.user_id:
                user = db.query(User).filter(User.id == challenge.user_id).first()
            if not user:
                user = db.query(User).filter(User.phone == challenge.phone).first()

            if not user:
                # Fallback: create user if webhook verified but user creation was delayed
                profile = challenge.get_profile()
                try:
                    user = User(
                        full_name=profile.get("full_name") or "Dhule Citizen",
                        phone=challenge.phone,
                        email=profile.get("email"),
                        hashed_password=profile.get("password_hash"),
                        role="citizen",
                        ward=profile.get("ward") or "Ward 12",
                        eco_coins=100,
                        is_active=True
                    )
                    db.add(user)
                    db.commit()
                    db.refresh(user)
                    challenge.user_id = user.id
                except IntegrityError:
                    db.rollback()
                    user = db.query(User).filter(User.phone == challenge.phone).first()

            session_id = f"sess_{user.id}_{int(time.time())}"
            access_token = create_access_token({
                "sub": user.email or user.phone,
                "role": user.role,
                "id": user.id,
                "sid": session_id
            })

            return {
                "status": "VERIFIED",
                "verified": True,
                "consumed": True,
                "expired": False,
                "phone_masked": masked_phone,
                "seconds_remaining": 0,
                "whatsapp_number": business_phone,
                "access_token": access_token,
                "token_type": "bearer",
                "user": UserResponse(
                    id=user.id,
                    name=user.full_name,
                    email=user.email,
                    role=user.role,
                    ward=user.ward,
                    phone=user.phone,
                    employee_id=user.employee_id,
                    eco_coins=user.eco_coins or 100
                ),
                "message": "Mobile number successfully verified via WhatsApp."
            }

        if challenge.status == "CONSUMED":
            return {
                "status": "CONSUMED",
                "verified": True,
                "consumed": True,
                "expired": False,
                "phone_masked": masked_phone,
                "seconds_remaining": 0,
                "whatsapp_number": business_phone,
                "access_token": None,
                "token_type": None,
                "user": None,
                "message": "Verification session has already been claimed."
            }

        if challenge.status == "PENDING":
            return {
                "status": "PENDING",
                "verified": False,
                "consumed": False,
                "expired": False,
                "phone_masked": masked_phone,
                "seconds_remaining": time_remaining,
                "whatsapp_number": business_phone,
                "message": "Waiting for VERIFY message on WhatsApp."
            }

        # EXPIRED or FAILED
        return {
            "status": challenge.status,
            "verified": False,
            "consumed": False,
            "expired": challenge.status == "EXPIRED",
            "phone_masked": masked_phone,
            "seconds_remaining": 0,
            "whatsapp_number": business_phone,
            "message": "Verification code expired or exceeded attempts. Please request a new code."
        }
