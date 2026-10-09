from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from server.database.db import get_db
from server.schemas.auth import (
    LoginRequest, SignupRequest, AuthResponse, UserResponse, UserProfileUpdate,
    ForgotPasswordRequest, ForgotPasswordResponse, SendOtpRequest, VerifyOtpRequest
)
from server.services.auth_service import AuthService
from server.utils.security import get_current_user
from server.models.user import User

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        return AuthService.login_user(db, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/signup", response_model=AuthResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    try:
        return AuthService.register_user(db, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
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
    try:
        return AuthService.update_user_profile(db, current_user, payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    try:
        result = AuthService.request_password_reset(db, payload.identifier, payload.role or "citizen")
        return ForgotPasswordResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/send-otp")
def send_otp(payload: SendOtpRequest, db: Session = Depends(get_db)):
    try:
        return AuthService.send_otp(db, payload.phone)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/verify-otp", response_model=AuthResponse)
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)):
    try:
        return AuthService.verify_otp(db, payload.phone, payload.otp, payload.role or "citizen")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
