"""
SMS service abstraction for EcoPulse AI.
Supports Indian DLT-compliant SMS gateways (MSG91, 2Factor) and a safe development provider.
"""
import os
import abc
import logging
from typing import Optional
import httpx
from server.utils.config import config, normalize_environment

logger = logging.getLogger(__name__)


class SMSProvider(abc.ABC):
    """Abstract Base Class for SMS delivery providers."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name of the SMS provider."""
        pass

    @abc.abstractmethod
    def send_otp(self, phone: str, otp: str) -> bool:
        """
        Deliver a 6-digit OTP to the specified 10-digit Indian phone number.
        Returns True if delivery succeeded, False if failed.
        """
        pass


class DevelopmentSMSProvider(SMSProvider):
    """
    Safe local development provider.
    - Strictly active ONLY when ENV is 'development' or 'test'.
    - Refuses to run in production.
    - Masks phone numbers.
    - Never exposes OTPs in production.
    """
    def __init__(self):
        env = normalize_environment(os.getenv("ENV", os.getenv("ENVIRONMENT", config.ENV)))
        if env == "production":
            raise RuntimeError("CRITICAL: DevelopmentSMSProvider cannot be initialized in production mode.")
        self.last_sent_phone: Optional[str] = None
        self.last_sent_otp: Optional[str] = None

    @property
    def provider_name(self) -> str:
        return "development"

    def send_otp(self, phone: str, otp: str) -> bool:
        clean_phone = phone.strip()
        self.last_sent_phone = clean_phone
        self.last_sent_otp = otp

        masked_phone = f"+91 ******{clean_phone[-4:]}" if len(clean_phone) >= 4 else clean_phone
        env = normalize_environment(os.getenv("ENV", os.getenv("ENVIRONMENT", config.ENV)))

        if env in ("development", "test"):
            logger.info("[SMS-DEV] [DEVELOPMENT MODE] OTP dispatched to %s (dev_otp=%s)", masked_phone, otp)
        else:
            logger.info("[SMS-DEV] OTP dispatched to %s (length=%d)", masked_phone, len(otp))

        return True


# Backward-compatible alias for existing tests
MockSMSProvider = DevelopmentSMSProvider


class MSG91SMSProvider(SMSProvider):
    """
    MSG91 Indian SMS Gateway provider adhering to TRAI DLT regulations.
    Uses MSG91 v5 OTP transactional API.
    """
    def __init__(self, auth_key: str, sender_id: str, template_id: str):
        self.auth_key = auth_key.strip() if auth_key else ""
        self.sender_id = sender_id.strip() if sender_id else "ECPULS"
        self.template_id = template_id.strip() if template_id else ""

    @property
    def provider_name(self) -> str:
        return "msg91"

    def send_otp(self, phone: str, otp: str) -> bool:
        if not self.auth_key or not self.template_id:
            logger.error("[SMS-MSG91] Missing MSG91 credentials: SMS_API_KEY and SMS_TEMPLATE_ID are required.")
            return False

        clean_phone = phone.strip()
        formatted_mobile = f"91{clean_phone}" if len(clean_phone) == 10 else clean_phone
        masked_mobile = f"91******{clean_phone[-4:]}"

        url = "https://control.msg91.com/api/v5/otp"
        headers = {
            "authkey": self.auth_key,
            "Content-Type": "application/json"
        }
        payload = {
            "template_id": self.template_id,
            "mobile": formatted_mobile,
            "otp": otp,
            "sender": self.sender_id,
            "otp_expiry": max(1, config.SMS_OTP_EXPIRY_SECONDS // 60)
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("type") == "success":
                        logger.info("[SMS-MSG91] OTP dispatched successfully to %s", masked_mobile)
                        return True
                    logger.warning("[SMS-MSG91] Gateway returned error: %s", data.get("message"))
                    return False
                logger.error("[SMS-MSG91] Gateway returned HTTP %d: %s", res.status_code, res.text[:200])
                return False
        except Exception as exc:
            logger.error("[SMS-MSG91] Exception dispatching OTP to %s: %s", masked_mobile, type(exc).__name__)
            return False


class TwoFactorSMSProvider(SMSProvider):
    """
    2Factor.in Indian SMS Gateway provider adhering to TRAI DLT regulations.
    Official Endpoint: https://2factor.in/API/V1/{api_key}/SMS/{phone}/{otp}/{template_name}
    """
    def __init__(self, api_key: str, template_name: str = ""):
        self.api_key = api_key.strip() if api_key else ""
        self.template_name = template_name.strip() if template_name else ""

    @property
    def provider_name(self) -> str:
        return "2factor"

    def send_otp(self, phone: str, otp: str) -> bool:
        if not self.api_key:
            logger.error("[SMS-2FACTOR] Missing 2Factor API Key: SMS_API_KEY is required.")
            return False

        clean_phone = phone.strip()
        formatted_mobile = f"91{clean_phone}" if len(clean_phone) == 10 else clean_phone
        masked_mobile = f"91******{clean_phone[-4:]}"

        if self.template_name:
            url = f"https://2factor.in/API/V1/{self.api_key}/SMS/{formatted_mobile}/{otp}/{self.template_name}"
        else:
            url = f"https://2factor.in/API/V1/{self.api_key}/SMS/{formatted_mobile}/{otp}"

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("Status") == "Success":
                        logger.info("[SMS-2FACTOR] OTP dispatched successfully to %s", masked_mobile)
                        return True
                    logger.warning("[SMS-2FACTOR] Gateway returned error: %s", data.get("Details"))
                    return False
                logger.error("[SMS-2FACTOR] Gateway returned HTTP %d: %s", res.status_code, res.text[:200])
                return False
        except Exception as exc:
            logger.error("[SMS-2FACTOR] Exception dispatching OTP to %s: %s", masked_mobile, type(exc).__name__)
            return False


_active_provider: Optional[SMSProvider] = None


def get_sms_provider() -> SMSProvider:
    """
    Factory function returning the active SMSProvider according to configuration.
    Enforces strict production safeguards:
    - Never allows development/mock provider in production mode.
    - If credentials are missing in production mode, raises HTTPException(503).
    """
    global _active_provider
    if _active_provider is not None:
        return _active_provider

    env = normalize_environment(os.getenv("ENV", os.getenv("ENVIRONMENT", config.ENV)))
    provider_name = (config.SMS_PROVIDER or "development").strip().lower()

    if env == "production":
        # Disallow development/mock provider in production
        if provider_name in ("mock", "dev", "development"):
            logger.error("[SMS] CRITICAL: Development SMS provider cannot be enabled in production environment.")
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SMS gateway service is not configured for production. Please configure an approved SMS provider."
            )

        if provider_name == "msg91":
            if not config.SMS_API_KEY or not config.SMS_TEMPLATE_ID:
                logger.error("[SMS] Incomplete MSG91 configuration in production mode.")
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="SMS gateway service is not configured. Missing MSG91 AuthKey or DLT template ID."
                )
            return MSG91SMSProvider(config.SMS_API_KEY, config.SMS_SENDER_ID, config.SMS_TEMPLATE_ID)

        if provider_name in ("2factor", "twofactor"):
            if not config.SMS_API_KEY:
                logger.error("[SMS] Incomplete 2Factor configuration in production mode.")
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="SMS gateway service is not configured. Missing 2Factor API Key."
                )
            return TwoFactorSMSProvider(config.SMS_API_KEY, config.SMS_TEMPLATE_ID)

        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unsupported SMS provider '{provider_name}' in production mode."
        )

    # In non-production (development, test)
    if provider_name == "msg91" and config.SMS_API_KEY:
        return MSG91SMSProvider(config.SMS_API_KEY, config.SMS_SENDER_ID, config.SMS_TEMPLATE_ID)

    if provider_name in ("2factor", "twofactor") and config.SMS_API_KEY:
        return TwoFactorSMSProvider(config.SMS_API_KEY, config.SMS_TEMPLATE_ID)

    return DevelopmentSMSProvider()


def set_sms_provider_for_testing(provider: Optional[SMSProvider]):
    """Testing hook to inject mock or failing provider instances."""
    global _active_provider
    _active_provider = provider
