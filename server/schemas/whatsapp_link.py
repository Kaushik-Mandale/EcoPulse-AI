"""Pydantic schemas for WhatsApp account-linking API."""
from typing import Optional
from pydantic import BaseModel


class GenerateLinkCodeResponse(BaseModel):
    success: bool
    link_code: str
    code: Optional[str] = None
    expires_in: int          # seconds until expiry
    bot_phone: Optional[str] = None
    message: str


class LinkStatusResponse(BaseModel):
    is_linked: bool
    whatsapp_phone: Optional[str] = None   # masked phone shown to user
    whatsapp_phone_masked: Optional[str] = None
    registered_phone: Optional[str] = None  # website registration phone
    linked_at: Optional[str] = None


class UnlinkResponse(BaseModel):
    success: bool
    message: str
