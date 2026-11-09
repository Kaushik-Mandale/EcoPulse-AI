"""Abstract base class for OTP delivery providers."""
from dataclasses import dataclass
from typing import Optional
from abc import ABC, abstractmethod


@dataclass
class OtpDeliveryResult:
    """Rich result object returned by every OTP delivery provider."""
    success: bool
    provider: str
    message: str
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None

    def __bool__(self) -> bool:
        return self.success

    def __repr__(self) -> str:
        return (
            f"<OtpDeliveryResult success={self.success} provider={self.provider!r} "
            f"message={self.message!r}>"
        )


class OtpDeliveryProvider(ABC):
    """Abstract base class every OTP delivery channel must implement."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier (e.g. 'meta_whatsapp')."""
        ...

    @abstractmethod
    def send_otp(self, e164_phone: str, otp: str) -> OtpDeliveryResult:
        """
        Deliver a 6-digit OTP to the given E.164 phone number.

        Args:
            e164_phone: Phone number in E.164 format (e.g. '+919876543210').
            otp: Plaintext 6-digit OTP to deliver.  NEVER log this value.

        Returns:
            OtpDeliveryResult — evaluates truthy on success.
        """
        ...
