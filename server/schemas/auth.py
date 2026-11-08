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
            raise ValueError("Mobile number, Email or Employee ID cannot be empty.")
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
    fullName: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = "citizen"
    ward: Optional[str] = "Ward 12"
    phone: str
    otp: Optional[str] = None
    employeeId: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        v = v.strip().lower()
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", v):
            raise ValueError("Please provide a valid email address.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone_format(cls, v: str) -> str:
        clean = re.sub(r"\D", "", v.strip())
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        elif clean.startswith("0") and len(clean) == 11:
            clean = clean[1:]
        if len(clean) != 10:
            raise ValueError("Phone number must be a valid 10-digit mobile number.")
        return clean

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> str:
        valid_roles = {"citizen", "driver", "collector", "admin"}
        if v and v.lower() not in valid_roles:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(valid_roles)}")
        return v.lower() if v else "citizen"

class RegisterRequest(BaseModel):
    full_name: str
    phone: str
    otp: str
    email: Optional[str] = None
    role: Optional[str] = "citizen"
    ward: Optional[str] = "Ward 12"
    password: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Full name must be at least 2 characters long.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone_format(cls, v: str) -> str:
        clean = re.sub(r"\D", "", v.strip())
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        elif clean.startswith("0") and len(clean) == 11:
            clean = clean[1:]
        if len(clean) != 10:
            raise ValueError("Phone number must be a valid 10-digit mobile number.")
        return clean

    @field_validator("email")
    @classmethod
    def validate_email_if_present(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        v = v.strip().lower()
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", v):
            raise ValueError("Please provide a valid email address.")
        return v

class OtpLoginRequest(BaseModel):
    phone: str
    otp: str
    role: Optional[str] = "citizen"

    @field_validator("phone")
    @classmethod
    def validate_phone_format(cls, v: str) -> str:
        clean = re.sub(r"\D", "", v.strip())
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        elif clean.startswith("0") and len(clean) == 11:
            clean = clean[1:]
        if len(clean) != 10:
            raise ValueError("Phone number must be a valid 10-digit mobile number.")
        return clean

class SendOtpRequest(BaseModel):
    phone: str
    purpose: Optional[str] = "login" # "login" | "register"

    @field_validator("phone")
    @classmethod
    def validate_phone_format(cls, v: str) -> str:
        clean = re.sub(r"\D", "", v.strip())
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        elif clean.startswith("0") and len(clean) == 11:
            clean = clean[1:]
        if len(clean) != 10:
            raise ValueError("Phone number must be a valid 10-digit mobile number.")
        return clean

class SendOtpResponse(BaseModel):
    success: bool
    message: str
    phone: str
    cooldown_seconds: int = 60
    expires_in: int = 300
    account_exists: Optional[bool] = None

class VerifyOtpRequest(BaseModel):
    phone: str
    otp: str
    purpose: Optional[str] = "login"
    role: Optional[str] = "citizen"

    @field_validator("phone")
    @classmethod
    def validate_phone_format(cls, v: str) -> str:
        clean = re.sub(r"\D", "", v.strip())
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        elif clean.startswith("0") and len(clean) == 11:
            clean = clean[1:]
        if len(clean) != 10:
            raise ValueError("Phone number must be a valid 10-digit mobile number.")
        return clean

    @field_validator("otp")
    @classmethod
    def validate_otp_format(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^\d{6}$", v):
            raise ValueError("OTP must be exactly 6 digits.")
        return v

class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    ward: Optional[str] = None
    phone: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

class UserResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
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
