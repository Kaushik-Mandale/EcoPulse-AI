"""Pydantic schemas for Website-Generated WhatsApp Registration Verification."""

from typing import Optional
import re
from pydantic import BaseModel, field_validator
from server.schemas.auth import UserResponse


class WhatsAppVerificationGenerateRequest(BaseModel):
    phone: str
    full_name: Optional[str] = None
    fullName: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    ward: Optional[str] = "Ward 12"

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean = re.sub(r"\D", "", v.strip())
        if clean.startswith("91") and len(clean) == 12:
            clean = clean[2:]
        elif clean.startswith("0") and len(clean) == 11:
            clean = clean[1:]
        if len(clean) != 10:
            raise ValueError("Phone number must be a valid 10-digit mobile number.")
        if not re.match(r"^[6-9]\d{9}$", clean):
            raise ValueError("Indian mobile numbers must begin with 6, 7, 8, or 9.")
        return clean

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            return None
        v = v.strip().lower()
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", v):
            raise ValueError("Please provide a valid email address or leave blank.")
        return v

    def resolve_full_name(self) -> str:
        name = (self.full_name or self.fullName or "").strip()
        if not name or len(name) < 2:
            raise ValueError("Full name must be at least 2 characters long.")
        return name


class WhatsAppVerificationGenerateResponse(BaseModel):
    success: bool = True
    challenge_id: str
    challenge_secret: str  # High-entropy secret returned once to browser to authorize session retrieval
    code: str
    whatsapp_number: str
    verification_command: str
    instructions: str
    expires_in: int
    expires_at: str
    cooldown_seconds: int = 60
    phone_masked: str


class WhatsAppVerificationStatusResponse(BaseModel):
    status: str  # PENDING, VERIFIED, CONSUMED, EXPIRED, FAILED
    verified: bool
    consumed: bool
    expired: bool
    phone_masked: str
    seconds_remaining: int
    whatsapp_number: Optional[str] = None
    access_token: Optional[str] = None
    token_type: Optional[str] = "bearer"
    user: Optional[UserResponse] = None
    message: Optional[str] = None
