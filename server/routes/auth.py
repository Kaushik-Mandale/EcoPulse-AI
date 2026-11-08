from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import Union
from server.database.db import get_db
from server.schemas.auth import (
    LoginRequest, SignupRequest, RegisterRequest, OtpLoginRequest,
    AuthResponse, UserResponse, UserProfileUpdate,
    ForgotPasswordRequest, ForgotPasswordResponse,
    SendOtpRequest, SendOtpResponse, VerifyOtpRequest,
    OtpChallengeStatusRequest, OtpChallengeStatusResponse
)
from server.services.auth_service import AuthService
from server.utils.security import get_current_user
from server.models.user import User

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
# 2. Compatibility & Session Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Password-based login for existing municipal administrative & driver accounts.
    Accepts mobile number, email, or employee ID.
    """
    return AuthService.login_user(db, payload)


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
        eco_coins=current_user.eco_coins or 100
    )


@router.put("/profile", response_model=UserResponse)
def update_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Updates profile details for the authenticated user."""
    return AuthService.update_user_profile(db, current_user, payload)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Dispatches password reset instructions."""
    result = AuthService.request_password_reset(db, payload.identifier, payload.role or "citizen")
    return ForgotPasswordResponse(**result)
