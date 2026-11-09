"""Factory for resolving the active OTP delivery provider."""
import logging
from typing import Optional
from server.utils.config import config

logger = logging.getLogger(__name__)

_provider_override: Optional[object] = None


def set_otp_delivery_provider_for_testing(provider) -> None:
    """
    Testing injection hook — sets a fixed provider for the duration of a test.
    Pass None to restore factory resolution.
    """
    global _provider_override
    _provider_override = provider


def get_otp_delivery_provider():
    """
    Returns the active OTP delivery provider.

    Resolution order:
      1. Test override (if set via set_otp_delivery_provider_for_testing).
      2. OTP_DELIVERY_PROVIDER env var / config.
      3. DevelopmentOtpProvider in non-production environments.
      4. RuntimeError if production requests development provider.
    """
    global _provider_override
    if _provider_override is not None:
        return _provider_override

    provider_name = getattr(config, "OTP_DELIVERY_PROVIDER", "development").strip().lower()
    env = config.ENV  # already normalized by Config.reload()

    if provider_name == "meta_whatsapp":
        from server.services.otp_delivery.meta_whatsapp import MetaWhatsAppOtpProvider
        return MetaWhatsAppOtpProvider()

    if env == "production":
        raise RuntimeError(
            "OTP_DELIVERY_PROVIDER must be set to 'meta_whatsapp' in production. "
            "Development provider is not permitted in production mode."
        )

    # development / test
    from server.services.otp_delivery.development import DevelopmentOtpProvider
    return DevelopmentOtpProvider()
