from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
from typing import Optional
import re

class LoginRequest(BaseModel):
    email: str
    password: str
    role: Optional[str] = "citizen"
    rememberMe: Optional[bool] = True

    @field_validator("email")
    @classmethod
    def sanitize_identifier(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Email or Employee ID cannot be empty.")
        if "@" in v:
            return v.lower()
        return v

    @field_validator("password")
    @classmethod
    def validate_password_nonempty(cls, v: str) -> str:
        if not v or len(v) < 6:
            raise ValueError("Password must be at least 6 characters long.")
        return v

class SignupRequest(BaseModel):
    fullName: str
    email: str
    password: str
    role: Optional[str] = "citizen"
    ward: Optional[str] = "Ward 12"
    phone: Optional[str] = ""
    employeeId: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", v):
            raise ValueError("Please provide a valid email address.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone_format(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return ""
        clean = v.strip().replace(" ", "").replace("-", "")
        if len(clean) < 10:
            raise ValueError("Phone number must be at least 10 digits.")
        return clean

    @field_validator("password")
    @classmethod
    def validate_strong_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit.")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> str:
        valid_roles = {"citizen", "driver", "collector", "admin"}
        if v and v.lower() not in valid_roles:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
        return v.lower() if v else "citizen"

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    ward: Optional[str] = None
    phone: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    ward: Optional[str] = None
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    eco_coins: int = 100

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class ForgotPasswordRequest(BaseModel):
    identifier: str
    role: Optional[str] = "citizen"

class ForgotPasswordResponse(BaseModel):
    success: bool
    message: str

class SendOtpRequest(BaseModel):
    phone: str

class VerifyOtpRequest(BaseModel):
    phone: str
    otp: str
    role: Optional[str] = "citizen"
