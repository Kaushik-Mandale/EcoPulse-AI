"""Development / test OTP delivery provider for EcoPulse AI.

Strictly forbidden in production. Used during local development and automated tests.
"""
import os
import logging
from typing import Optional
from server.services.otp_delivery.base import OtpDeliveryProvider, OtpDeliveryResult
from server.utils.config import config, normalize_environment

logger = logging.getLogger(__name__)

# OTPs that are always rejected (trivially guessable codes)
_REJECTED_OTPS = {"000000", "111111", "999999"}


class DevelopmentOtpProvider(OtpDeliveryProvider):
    """
    Safe development / test provider.

    Behaviour:
      - Accepts any 6-digit numeric OTP as valid (simulates delivery).
      - Rejects 000000, 111111, 999999.
      - Raises RuntimeError if instantiated in production mode.
      - Records the last phone and OTP for assertion convenience (OTP not logged).
    """

    def __init__(self):
        env = normalize_environment(os.getenv("ENV", os.getenv("ENVIRONMENT", config.ENV)))
        if env == "production":
            raise RuntimeError(
                "CRITICAL: DevelopmentOtpProvider cannot be initialised in production mode. "
                "Set OTP_DELIVERY_PROVIDER=meta_whatsapp in production."
            )
        self.last_sent_phone: Optional[str] = None
        # NOTE: last_sent_otp is intentionally stored for test assertions only;
        #       it is never written to logs.
        self.last_sent_otp: Optional[str] = None
        self.sent_count: int = 0

    @property
    def provider_name(self) -> str:
        return "development"

    def send_otp(self, e164_phone: str, otp: str) -> OtpDeliveryResult:
        """Simulate OTP delivery. Never logs the OTP value."""
        if otp in _REJECTED_OTPS:
            return OtpDeliveryResult(
                success=False,
                provider=self.provider_name,
                message=f"OTP {otp[:2]}**** is not accepted by the development provider.",
                error_code="REJECTED_TEST_CODE"
            )
        self.last_sent_phone = e164_phone
        self.last_sent_otp = otp  # stored for test assertions; never logged
        self.sent_count += 1
        masked = f"+91 ******{e164_phone[-4:]}" if len(e164_phone) >= 4 else e164_phone
        logger.info("[OTP-DEV] OTP dispatched to %s (length=%d)", masked, len(otp))
        return OtpDeliveryResult(
            success=True,
            provider=self.provider_name,
            message=f"Development OTP accepted for {masked}.",
            provider_message_id=f"dev-{self.sent_count}"
        )


def set_provider_for_testing(provider: Optional["OtpDeliveryProvider"]) -> None:
    """
    Injection hook for tests — delegates to the factory-level setter.
    Import from factory instead when possible.
    """
    from server.services.otp_delivery.factory import set_otp_delivery_provider_for_testing
    set_otp_delivery_provider_for_testing(provider)
