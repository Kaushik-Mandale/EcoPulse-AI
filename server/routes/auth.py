from server.schemas.whatsapp_verification import (
    WhatsAppVerificationGenerateRequest,
    WhatsAppVerificationGenerateResponse,
    WhatsAppVerificationStatusResponse
)
from server.services.whatsapp_verification_service import WhatsAppVerificationService
from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from sqlalchemy.orm import Session
from typing import Union, Optional
from server.database.db import get_db
from server.schemas.auth import (
    LoginRequest, SignupRequest, RegisterRequest, OtpLoginRequest, PasswordChangeRequest,
    InitialPasswordChangeRequest,
    StaffPhoneVerificationStartRequest, StaffPhoneVerificationConfirmRequest,
    AuthResponse, UserResponse, UserProfileUpdate,
    ForgotPasswordRequest, ForgotPasswordResponse,
    SendOtpRequest, SendOtpResponse, VerifyOtpRequest,
    OtpChallengeStatusRequest, OtpChallengeStatusResponse,
    InvitationValidationRequest, InvitationValidationResponse,
)
from server.services.auth_service import AuthService, temporary_password_expired
from server.utils.security import get_current_user
from server.utils.security import hash_password, is_strong_password
from server.models.user import User
from server.schemas.auth import MfaEnrollmentConfirmRequest, MfaEnrollmentStartRequest, InvitationActivationRequest
from server.models.account_invitation import AccountInvitation
from server.models.mobile_otp import MobileOtpToken
from server.services.iam_service import (
    audit, authenticate_password, change_password, consume_invitation, decrypt_mfa_secret,
    encrypt_mfa_secret, get_valid_invitation, make_access_token, verify_totp,
)
from server.services.auth_service import normalize_phone_number
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import secrets
import time
from urllib.parse import quote

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ─────────────────────────────────────────────────────────────
# 1. Mobile OTP Authentication Endpoints (Primary Flow)
# ─────────────────────────────────────────────────────────────

@router.post("/otp/send", response_model=SendOtpResponse)
@router.post("/send-otp", response_model=SendOtpResponse)
def send_otp(request: Request, payload: SendOtpRequest, db: Session = Depends(get_db)):
    """
    Dispatches a 6-digit verification code to the given Indian mobile number (+91).
    Enforces resend cooldown (60s) and rate-limiting by phone and IP.
    Never returns the OTP in response.
    """
    client_ip = request.client.host if request.client else None
    return AuthService.send_otp(db, phone=payload.phone, purpose=payload.purpose or "login", ip_address=client_ip)


@router.post("/otp/verify", response_model=AuthResponse)
@router.post("/verify-otp", response_model=AuthResponse)
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    """
    Verifies 6-digit OTP against stored SHA-256 hash.
    On purpose='login', authenticates user and generates JWT session.
    """
    return AuthService.verify_otp(
        db,
        phone=payload.phone,
        otp=payload.otp,
        purpose=payload.purpose or "login",
        role=payload.role or "citizen",
        challenge_id=payload.challenge_id
    )


@router.get("/otp/challenge/{challenge_id}", response_model=OtpChallengeStatusResponse)
def get_challenge_status(challenge_id: str, db: Session = Depends(get_db)):
    """
    Authoritative challenge status retrieval for refresh-safe session restoration.
    Returns remaining TTL, resend cooldown, and validity without exposing OTP values.
    """
    return AuthService.get_challenge_status(db, challenge_id)


@router.post("/otp/status", response_model=OtpChallengeStatusResponse)
def post_challenge_status(payload: OtpChallengeStatusRequest, db: Session = Depends(get_db)):
    """
    POST variant for challenge status retrieval.
    """
    return AuthService.get_challenge_status(db, payload.challenge_id)


@router.post("/login/otp", response_model=AuthResponse)
def login_with_otp(payload: OtpLoginRequest, db: Session = Depends(get_db)):
    """
    Mobile-first login endpoint: Authenticates existing user via mobile number + OTP.
    Redirects to the user's role-specific dashboard.
    """
    return AuthService.login_with_otp(
        db,
        phone=payload.phone,
        otp=payload.otp,
        role=payload.role or "citizen",
        challenge_id=payload.challenge_id
    )


@router.post("/register", response_model=AuthResponse)
@router.post("/signup", response_model=AuthResponse)
def register(request: Request, payload: Union[RegisterRequest, SignupRequest], db: Session = Depends(get_db)):
    """
    Mobile-first citizen registration:
    Full name and mobile number are required. Email is optional.
    Strictly verifies OTP before creating the user in database.
    """
    client_ip = request.client.host if request.client else None
    return AuthService.register_user(db, payload, ip_address=client_ip)


# ─────────────────────────────────────────────────────────────
# 1b. Website-Generated WhatsApp Registration Verification Flow
# ─────────────────────────────────────────────────────────────

@router.post("/whatsapp-verification/generate", response_model=WhatsAppVerificationGenerateResponse)
def generate_whatsapp_verification(
    request: Request,
    payload: WhatsAppVerificationGenerateRequest,
    db: Session = Depends(get_db)
):
    """
    Generates a 6-digit verification code for citizen registration.
    No outbound message is dispatched.
    Instructions display: 'Send VERIFY <code> to official EcoPulse AI WhatsApp Business number.'
    Returns the plaintext code once in the response.
    """
    client_ip = request.client.host if request.client else None
    full_name = payload.resolve_full_name()
    return WhatsAppVerificationService.generate_verification_challenge(
        db,
        phone=payload.phone,
        full_name=full_name,
        email=payload.email,
        password=payload.password,
        ward=payload.ward,
        ip_address=client_ip
    )


@router.get("/whatsapp-verification/status/{challenge_id}", response_model=WhatsAppVerificationStatusResponse)
def get_whatsapp_verification_status(
    challenge_id: str,
    db: Session = Depends(get_db),
    x_challenge_secret: Optional[str] = Header(None, alias="X-Challenge-Secret"),
    secret: Optional[str] = None
):
    """
    Polls the verification status of a website-generated challenge.
    Possession of challenge_id alone permits checking status without exposing session.
    A valid challenge_secret (via X-Challenge-Secret header) is required to claim the JWT.
    Does not disclose sensitive challenge secrets or database keys.
    """
    effective_secret = x_challenge_secret or secret
    return WhatsAppVerificationService.get_challenge_status(db, challenge_id, challenge_secret=effective_secret)


# ─────────────────────────────────────────────────────────────
# 2. Compatibility & Session Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Password-based login for existing municipal administrative & driver accounts.
    Accepts mobile number, email, or employee ID.
    """
    return AuthService.login_user(db, payload)


@router.post("/initial-password/change")
def change_initial_super_admin_password(
    payload: InitialPasswordChangeRequest, db: Session = Depends(get_db),
):
    """Rotate a provisioned staff temporary password without issuing a session."""
    user = db.query(User).filter(
        User.login_id == payload.login_id.strip(),
        User.role.in_(["admin", "driver", "collector"]),
    ).first()
    if (
        not user or not user.must_change_password
        or user.is_locked or not user.is_active
        or getattr(user, "account_status", "active") != "active"
        or (not user.is_verified and user.role != "driver")
    ):
        raise HTTPException(status_code=401, detail="Initial password change is unavailable.")
    if temporary_password_expired(user):
        raise HTTPException(
            status_code=403,
            detail={"code": "TEMPORARY_CREDENTIAL_EXPIRED", "message": "This temporary password has expired. Contact an authorized administrator for a reset."},
        )
    if not authenticate_password(user, payload.current_password):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= 5:
            user.is_locked = True
        audit(db, "initial_password_change_failed", target=user)
        db.commit()
        raise HTTPException(status_code=401, detail="Initial password change is unavailable.")
    password = payload.new_password
    if not is_strong_password(password) or authenticate_password(user, password):
        raise HTTPException(
            status_code=400,
            detail="Choose a different password with 12-72 UTF-8 bytes, uppercase and lowercase letters, a number, and a symbol.",
        )
    user.hashed_password = hash_password(payload.new_password)
    user.must_change_password = False
    user.temporary_password_expires_at = None
    user.session_version = (user.session_version or 0) + 1
    user.failed_attempts = 0
    audit(
        db,
        "super_admin_initial_password_changed" if user.is_super_admin else "staff_initial_password_changed",
        actor=user,
        target=user,
    )
    db.commit()
    next_step = "Enroll authenticator-app MFA before signing in." if user.role in {"admin", "collector"} else "Sign in after mobile verification."
    return {"success": True, "message": f"Initial password changed. {next_step}"}


def _find_mfa_enrollment_user(db: Session, identifier: str):
    identifier = identifier.strip()
    user = db.query(User).filter(User.employee_id == identifier).first()
    if user is None:
        user = db.query(User).filter(
            User.login_id == identifier,
            User.role.in_(["admin", "collector"]),
        ).first()
    return user


@router.post("/drivers/phone-verification/send")
def send_provisioned_driver_phone_verification(
    payload: StaffPhoneVerificationStartRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Send activation-purpose OTP only to a provisioned, unverified Driver."""
    user = db.query(User).filter(
        User.login_id == payload.login_id.strip(), User.role == "driver",
    ).first()
    if (
        not user or user.is_verified or user.must_change_password
        or not user.login_id or not user.created_by_id
        or not user.is_active or user.is_locked or user.account_status != "active"
        or not authenticate_password(user, payload.password)
    ):
        raise HTTPException(status_code=401, detail="Driver verification is unavailable.")
    return AuthService.send_otp(
        db,
        phone=user.phone or "",
        purpose="activation",
        ip_address=request.client.host if request.client else None,
    )


@router.post("/drivers/phone-verification/confirm")
def confirm_provisioned_driver_phone_verification(
    payload: StaffPhoneVerificationConfirmRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(
        User.login_id == payload.login_id.strip(), User.role == "driver",
    ).first()
    if (
        not user or user.is_verified or user.must_change_password
        or not user.login_id or not user.created_by_id
        or not user.is_active or user.is_locked or user.account_status != "active"
        or not authenticate_password(user, payload.password)
    ):
        raise HTTPException(status_code=401, detail="Driver verification is unavailable.")

    challenge = AuthService.verify_and_get_challenge_token(db, payload.challenge_id)
    now = datetime.now(timezone.utc)
    expires_at = challenge.expires_at if challenge else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    valid = bool(
        challenge
        and challenge.purpose == "activation"
        and normalize_phone_number(challenge.phone) == normalize_phone_number(user.phone or "")
        and challenge.consumed_at is None
        and expires_at and expires_at > now
        and challenge.attempts < challenge.max_attempts
        and AuthService._verify_otp_hash(payload.otp, challenge.otp_hash)
    )
    if not valid:
        if challenge and challenge.purpose == "activation" and challenge.consumed_at is None:
            db.query(MobileOtpToken).filter(
                MobileOtpToken.id == challenge.id,
                MobileOtpToken.consumed_at.is_(None),
                MobileOtpToken.attempts < MobileOtpToken.max_attempts,
            ).update({"attempts": MobileOtpToken.attempts + 1}, synchronize_session=False)
            db.commit()
        raise HTTPException(status_code=400, detail="Driver mobile verification failed or expired.")

    consumed = db.query(MobileOtpToken).filter(
        MobileOtpToken.id == challenge.id,
        MobileOtpToken.purpose == "activation",
        MobileOtpToken.consumed_at.is_(None),
        MobileOtpToken.attempts < MobileOtpToken.max_attempts,
        MobileOtpToken.expires_at > now,
    ).update({"consumed_at": now}, synchronize_session=False)
    if consumed != 1:
        raise HTTPException(status_code=400, detail="Driver mobile verification was already used or expired.")

    user.is_verified = True
    user.verified_at = now
    user.session_version = (user.session_version or 0) + 1
    audit(db, "driver_phone_verified", target=user)
    db.commit()
    return {"success": True, "message": "Mobile verified. Sign in with your rotated password to continue."}


@router.post("/mfa/enrollment/start")
def start_mfa_enrollment(payload: MfaEnrollmentStartRequest, db: Session = Depends(get_db)):
    """Starts password-authorized TOTP enrollment for an administrator."""
    user = _find_mfa_enrollment_user(db, payload.employee_id)
    if (
        not user or user.role not in {"admin", "collector"} or not user.is_active
        or user.is_locked or getattr(user, "account_status", "active") != "active"
        or not authenticate_password(user, payload.password)
    ):
        if user and user.role in {"admin", "collector"}:
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= 5:
                user.is_locked = True
            audit(db, "mfa_enrollment_failed", target=user)
            db.commit()
        raise HTTPException(status_code=401, detail="Invalid employee credentials.")
    # Return onboarding state only after the password has been verified. This
    # lets the login UI guide the legitimate account holder to rotation without
    # exposing account state to unauthenticated callers.
    if user.must_change_password:
        if temporary_password_expired(user):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "TEMPORARY_CREDENTIAL_EXPIRED",
                    "message": "This temporary password has expired. Contact an authorized administrator for a reset.",
                },
            )
        raise HTTPException(
            status_code=428,
            detail={
                "code": "PASSWORD_CHANGE_REQUIRED",
                "message": "Change the initial password before setting up an authenticator.",
            },
        )
    if user.mfa_enabled:
        raise HTTPException(
            status_code=409,
            detail="MFA is already enrolled. Contact the municipal recovery process to replace an authenticator.",
        )
    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    try:
        user.mfa_secret_enc = encrypt_mfa_secret(secret)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Administrator MFA is not configured.") from exc
    user.mfa_enabled = False
    user.mfa_last_verified_step = None
    user.mfa_enrollment_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    user.failed_attempts = 0
    audit(db, "mfa_enrollment_started", target=user)
    db.commit()
    issuer = quote("EcoPulse AI", safe="")
    account = quote(user.login_id or user.employee_id or "", safe="")
    return {
        "secret": secret,
        "otpauth_uri": f"otpauth://totp/{issuer}:{account}?secret={secret}&issuer={issuer}&digits=6&period=30",
    }


@router.post("/mfa/enrollment/confirm")
def confirm_mfa_enrollment(payload: MfaEnrollmentConfirmRequest, db: Session = Depends(get_db)):
    user = _find_mfa_enrollment_user(db, payload.employee_id)
    if (
        not user or user.role not in {"admin", "collector"} or not user.is_active
        or user.is_locked or getattr(user, "account_status", "active") != "active"
        or user.mfa_enabled or user.must_change_password
        or not authenticate_password(user, payload.password)
        or not user.mfa_secret_enc
        or not user.mfa_enrollment_expires_at
    ):
        raise HTTPException(status_code=401, detail="MFA enrollment credentials are invalid.")
    enrollment_expires_at = user.mfa_enrollment_expires_at
    if enrollment_expires_at.tzinfo is None:
        enrollment_expires_at = enrollment_expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if enrollment_expires_at <= now:
        user.mfa_secret_enc = None
        user.mfa_enrollment_expires_at = None
        audit(db, "mfa_enrollment_expired", target=user)
        db.commit()
        raise HTTPException(status_code=410, detail="MFA enrollment expired. Start a new enrollment.")
    try:
        secret = decrypt_mfa_secret(user.mfa_secret_enc)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Administrator MFA is not configured.") from exc
    step = verify_totp(secret, payload.code)
    if step is None:
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= 5:
            user.is_locked = True
        audit(db, "mfa_enrollment_failed", target=user)
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid authenticator code.")
    user.mfa_enabled = True
    user.mfa_last_verified_step = step
    user.failed_attempts = 0
    user.mfa_enrolled_at = now
    user.mfa_enrollment_expires_at = None
    user.session_version = (user.session_version or 0) + 1
    audit(db, "mfa_enrollment_completed", target=user)
    db.commit()
    return {"success": True, "message": "MFA enrollment completed. Sign in with a new authenticator code."}


@router.post("/invitations/validate", response_model=InvitationValidationResponse)
def validate_invitation(
    payload: InvitationValidationRequest,
    db: Session = Depends(get_db),
):
    """Checks an invitation without returning its token or account contact details."""
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    invitation = db.query(AccountInvitation).filter(
        AccountInvitation.token_hash == token_hash
    ).first()
    if not invitation:
        return InvitationValidationResponse(status="invalid")
    if invitation.revoked_at is not None:
        return InvitationValidationResponse(status="revoked")
    if invitation.consumed_at is not None:
        return InvitationValidationResponse(status="used")

    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return InvitationValidationResponse(status="expired")

    user = db.query(User).filter(User.id == invitation.user_id).first()
    if (not user or invitation.role not in {"driver", "admin", "collector"} or user.role != invitation.role
            or user.account_status in {"suspended", "retired", "deactivated"}):
        return InvitationValidationResponse(status="invalid")
    return InvitationValidationResponse(
        status="valid",
        role=invitation.role,
        employee_id=user.employee_id if invitation.role in {"admin", "collector"} else None,
    )


@router.post("/drivers/activate")
def activate_driver(payload: InvitationActivationRequest, db: Session = Depends(get_db)):
    """Consumes a single-use invitation and mobile verification to activate a driver."""
    if not payload.otp or not payload.phone or not payload.challenge_id:
        raise HTTPException(status_code=400, detail="Invitation, phone, OTP, and challenge ID are required.")
    if len(payload.password) < 12 or len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be 12-72 UTF-8 bytes.")
    invitation, user = get_valid_invitation(db, payload.token, role="driver")
    if normalize_phone_number(payload.phone) != normalize_phone_number(user.phone or ""):
        raise HTTPException(status_code=403, detail="The mobile number does not match the invited driver.")
    challenge = AuthService.verify_and_get_challenge_token(db, payload.challenge_id)
    if not challenge:
        raise HTTPException(status_code=400, detail="Invalid activation challenge.")
    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if (
        not challenge or challenge.purpose != "activation"
        or challenge.consumed_at is not None
        or normalize_phone_number(challenge.phone) != normalize_phone_number(payload.phone)
        or challenge.expires_at is None
        or expires_at < datetime.now(timezone.utc)
        or challenge.attempts >= challenge.max_attempts
        or not AuthService._verify_otp_hash(payload.otp, challenge.otp_hash)
    ):
        if challenge and challenge.purpose == "activation" and challenge.consumed_at is None:
            db.query(MobileOtpToken).filter(
                MobileOtpToken.id == challenge.id,
                MobileOtpToken.consumed_at.is_(None),
                MobileOtpToken.attempts < MobileOtpToken.max_attempts,
            ).update(
                {"attempts": MobileOtpToken.attempts + 1},
                synchronize_session=False,
            )
            db.commit()
        raise HTTPException(status_code=400, detail="Driver mobile verification failed or expired.")
    now = datetime.now(timezone.utc)
    consumed_challenge = db.query(MobileOtpToken).filter(
        MobileOtpToken.id == challenge.id,
        MobileOtpToken.purpose == "activation",
        MobileOtpToken.phone == normalize_phone_number(payload.phone),
        MobileOtpToken.consumed_at.is_(None),
        MobileOtpToken.attempts < MobileOtpToken.max_attempts,
        MobileOtpToken.expires_at > now,
    ).update({"consumed_at": now}, synchronize_session=False)
    if consumed_challenge != 1:
        raise HTTPException(status_code=400, detail="Driver mobile verification was already used or expired.")
    consume_invitation(db, invitation, "driver")
    from server.utils.security import hash_password
    user.hashed_password = hash_password(payload.password)
    user.is_verified = True
    user.verified_at = datetime.now(timezone.utc)
    user.is_active = True
    user.account_status = "active"
    user.activated_at = datetime.now(timezone.utc)
    audit(db, "driver_activated", target=user)
    db.commit()
    return {"success": True, "message": "Driver account activated. Sign in with Employee ID and password."}


@router.post("/admins/activate")
def activate_administrator(payload: InvitationActivationRequest, db: Session = Depends(get_db)):
    if len(payload.password) < 12 or len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be 12-72 UTF-8 bytes.")
    invitation, user = get_valid_invitation(db, payload.token, role="admin")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Invitation is not for an administrator.")
    from server.utils.security import hash_password
    user.hashed_password = hash_password(payload.password)
    user.is_active = True
    user.is_verified = True
    user.verified_at = datetime.now(timezone.utc)
    user.account_status = "active"
    user.activated_at = datetime.now(timezone.utc)
    consume_invitation(db, invitation, "admin")
    user.session_version = (user.session_version or 0) + 1
    audit(db, "admin_activated", target=user)
    db.commit()
    return {"success": True, "message": "Administrator account activated. Enroll MFA before signing in."}


@router.post("/collectors/activate")
def activate_collector(payload: InvitationActivationRequest, db: Session = Depends(get_db)):
    """Activates an invited collector; MFA enrollment remains mandatory before sign-in."""
    if len(payload.password) < 12 or len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be 12-72 UTF-8 bytes.")
    invitation, user = get_valid_invitation(db, payload.token, role="collector")
    if user.role != "collector":
        raise HTTPException(status_code=403, detail="Invitation is not for a collector.")
    from server.utils.security import hash_password
    user.hashed_password = hash_password(payload.password)
    user.is_active = True
    user.is_verified = True
    user.verified_at = datetime.now(timezone.utc)
    user.account_status = "active"
    user.activated_at = datetime.now(timezone.utc)
    user.mfa_enabled = False
    user.mfa_secret_enc = None
    user.mfa_last_verified_step = None
    consume_invitation(db, invitation, "collector")
    user.session_version = (user.session_version or 0) + 1
    audit(db, "collector_activated", target=user)
    db.commit()
    return {"success": True, "message": "Collector account activated. Enroll MFA before signing in."}


@router.get("/me", response_model=UserResponse)
@router.get("/my", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Returns the authenticated user's profile."""
    return UserResponse(
        id=current_user.id,
        name=current_user.full_name,
        email=current_user.email,
        role=current_user.role,
        ward=current_user.ward,
        phone=current_user.phone,
        employee_id=current_user.employee_id,
        login_id=current_user.login_id,
        eco_coins=current_user.eco_coins if current_user.eco_coins is not None else 0,
        is_super_admin=bool(current_user.is_super_admin),
        account_status=current_user.account_status,
        mfa_enabled=bool(current_user.mfa_enabled),
    )


@router.put("/profile", response_model=UserResponse)
def update_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Updates profile details for the authenticated user."""
    return AuthService.update_user_profile(db, current_user, payload)


@router.post("/logout")
def logout(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.session_version = (current_user.session_version or 0) + 1
    audit(db, "logout", actor=current_user, target=current_user)
    db.commit()
    return {"success": True}


@router.post("/password/change")
def change_authenticated_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if len(payload.new_password) < 12 or len(payload.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="New password must be 12-72 UTF-8 bytes.")
    if not authenticate_password(current_user, payload.current_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    change_password(db, current_user, payload.new_password, actor=current_user)
    db.commit()
    return {"success": True, "message": "Password changed. Sign in again on your devices."}


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Dispatches password reset instructions."""
    result = AuthService.request_password_reset(db, payload.identifier, payload.role or "citizen")
    return ForgotPasswordResponse(**result)
