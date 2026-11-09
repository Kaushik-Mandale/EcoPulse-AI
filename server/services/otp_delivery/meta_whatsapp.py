"""Meta WhatsApp Cloud API OTP delivery provider for EcoPulse AI."""
import logging
from typing import Optional
import httpx
from server.services.otp_delivery.base import OtpDeliveryProvider, OtpDeliveryResult
from server.utils.config import config

logger = logging.getLogger(__name__)


class MetaWhatsAppOtpProvider(OtpDeliveryProvider):
    """
    Sends OTP via Meta WhatsApp Cloud API using an approved authentication template.

    Template creation vs runtime delivery:
      - Template creation: Category AUTHENTICATION, button type OTP, otp_type COPY_CODE.
      - Runtime delivery: Includes body parameter with OTP and runtime button parameter
        with sub_type="url" and index="0". Meta's Cloud API does not accept "copy_code"
        as a runtime sub_type.

    Required environment variables:
        META_WHATSAPP_ACCESS_TOKEN    — Meta permanent / system-user access token.
        META_WHATSAPP_PHONE_NUMBER_ID — Phone number ID from WhatsApp Business Manager.
        META_OTP_TEMPLATE_NAME        — Name of the approved WhatsApp template (default: ecopulse_otp).
        META_OTP_TEMPLATE_LANGUAGE    — Template language code (default: en).
        META_GRAPH_API_VERSION        — Graph API version (default: v22.0).
    """

    _GRAPH_BASE = "https://graph.facebook.com"

    @property
    def provider_name(self) -> str:
        return "meta_whatsapp"

    def _build_components(self, otp: str) -> list:
        """
        Builds the template components array for Meta WhatsApp Cloud API runtime delivery.

        For Meta AUTHENTICATION templates:
          1. Body component: Passes the OTP verification code as a text parameter:
             {"type": "body", "parameters": [{"type": "text", "text": otp}]}
          2. Button component: Meta Cloud API requires that runtime messages reference
             the button component with sub_type="url" and index="0", passing the OTP
             as the parameter:
             {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": otp}]}

        Note: Meta's Cloud API runtime engine converts template COPY_CODE buttons into
        URL-type action buttons for runtime delivery. sub_type="copy_code" is NOT a valid
        runtime delivery option and must not be sent.
        """
        components = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": otp}]
            }
        ]

        has_button = getattr(config, "META_OTP_TEMPLATE_HAS_BUTTON", True)
        if (
            hasattr(config, "META_OTP_TEMPLATE_HAS_URL_BUTTON")
            and not config.META_OTP_TEMPLATE_HAS_URL_BUTTON
            and not getattr(config, "META_OTP_TEMPLATE_HAS_BUTTON_EXPLICIT", False)
        ):
            has_button = False

        if has_button:
            # Runtime button component for approved Meta AUTHENTICATION template strictly uses sub_type="url"
            components.append({
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [{"type": "text", "text": otp}]
            })
        return components

    def build_payload(self, e164_phone: str, otp: str) -> dict:
        """
        Builds the complete JSON payload for Meta WhatsApp Cloud API /messages endpoint.

        Preserves internal E.164 phone while serializing recipient to the Cloud API format
        (international format without the leading '+' sign, e.g. '919876543210').
        """
        recipient = e164_phone.lstrip("+").strip()
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "template",
            "template": {
                "name": config.META_OTP_TEMPLATE_NAME,
                "language": {"code": config.META_OTP_TEMPLATE_LANGUAGE},
                "components": self._build_components(otp)
            }
        }

    def send_otp(self, e164_phone: str, otp: str) -> OtpDeliveryResult:
        """Send OTP via Meta WhatsApp Cloud API template message."""
        access_token = config.META_WHATSAPP_ACCESS_TOKEN
        phone_number_id = config.META_WHATSAPP_PHONE_NUMBER_ID

        if not access_token or not phone_number_id:
            logger.error(
                "[META-WA-OTP] Missing configuration: META_WHATSAPP_ACCESS_TOKEN and "
                "META_WHATSAPP_PHONE_NUMBER_ID are required."
            )
            return OtpDeliveryResult(
                success=False,
                provider=self.provider_name,
                message="Meta WhatsApp OTP service is not configured. Missing access token or phone number ID.",
                error_code="NOT_CONFIGURED"
            )

        masked_phone = f"+91 ******{e164_phone[-4:]}" if len(e164_phone) >= 4 else e164_phone
        api_version = config.META_GRAPH_API_VERSION or "v22.0"
        url = f"{self._GRAPH_BASE}/{api_version}/{phone_number_id}/messages"

        payload = self.build_payload(e164_phone, otp)

        headers = {
            # Never log the Authorization header
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        try:
            with httpx.Client(timeout=10.0) as http:
                response = http.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                messages = data.get("messages", [])
                if messages and messages[0].get("id"):
                    logger.info(
                        "[META-WA-OTP] OTP dispatched successfully via WhatsApp to %s", masked_phone
                    )
                    return OtpDeliveryResult(
                        success=True,
                        provider=self.provider_name,
                        message=f"WhatsApp OTP sent to {masked_phone}.",
                        provider_message_id=messages[0]["id"]
                    )
                # HTTP 200 but no message ID — treat as failure
                error_obj = data.get("error", {})
                err_code = str(error_obj.get("code", "UNKNOWN"))
                err_msg = error_obj.get("message", "Meta returned HTTP 200 but no message ID.")
                logger.error("[META-WA-OTP] HTTP 200 but no message ID for %s: %s", masked_phone, err_msg)
                return OtpDeliveryResult(
                    success=False,
                    provider=self.provider_name,
                    message=f"Meta WhatsApp API error: {err_msg}",
                    error_code=err_code
                )

            # Non-200 response
            try:
                error_body = response.json()
                error_obj = error_body.get("error", {})
                err_code = str(error_obj.get("code", response.status_code))
                err_msg = error_obj.get("message", f"HTTP {response.status_code}")
            except Exception:
                err_code = str(response.status_code)
                err_msg = f"HTTP {response.status_code}"

            logger.error(
                "[META-WA-OTP] API returned HTTP %d for %s: %s",
                response.status_code, masked_phone, err_msg
            )
            return OtpDeliveryResult(
                success=False,
                provider=self.provider_name,
                message=f"Meta WhatsApp API error ({err_code}): {err_msg}",
                error_code=err_code
            )

        except httpx.TimeoutException:
            logger.error("[META-WA-OTP] Request timed out for %s", masked_phone)
            return OtpDeliveryResult(
                success=False,
                provider=self.provider_name,
                message="Meta WhatsApp API request timed out. Please try again.",
                error_code="TIMEOUT"
            )
        except Exception as exc:
            logger.error("[META-WA-OTP] Unexpected error for %s: %s", masked_phone, type(exc).__name__)
            return OtpDeliveryResult(
                success=False,
                provider=self.provider_name,
                message=f"Meta WhatsApp API connection error: {type(exc).__name__}.",
                error_code="CONNECTION_ERROR"
            )
