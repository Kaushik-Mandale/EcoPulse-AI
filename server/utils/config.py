import os
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def normalize_environment(value: str | None) -> str:
    return (value or "").strip().lower()


def is_production_environment(value: str | None = None) -> bool:
    env_value = value if value is not None else os.getenv("ENV", os.getenv("ENVIRONMENT", "development"))
    return normalize_environment(env_value) == "production"


def is_local_or_test_environment(value: str | None = None) -> bool:
    env_value = value if value is not None else os.getenv("ENV", os.getenv("ENVIRONMENT", "development"))
    return normalize_environment(env_value) in {"development", "test", "testing", "local"}


def is_insecure_secret(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return True
    insecure_values = {
        "secret",
        "changeme",
        "password",
        "default",
        "development",
        "test",
        "replace_with_long_random_secret_key",
        "ecopulse-dev-secret-key-not-for-production",
    }
    return normalized in insecure_values or len((value or "").strip()) < 32


def is_valid_http_origin(value: str) -> bool:
    candidate = (value or "").strip()
    if not candidate:
        return False
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True


class Config:
    def __init__(self):
        self.reload()

    def reload(self):
        self.PROJECT_NAME: str = os.getenv("PROJECT_NAME", "EcoPulse AI")
        self.VERSION: str = os.getenv("VERSION", os.getenv("PROJECT_VERSION", "1.0.0"))
        self.ENV: str = normalize_environment(
            os.getenv("ENV", os.getenv("ENVIRONMENT", "development"))
        )
        self.SECRET_KEY: str = (os.getenv("SECRET_KEY", "") or "").strip()
        self.PORT: int = int(os.getenv("PORT", 8000))
        self.WHATSAPP_PROVIDER: str = os.getenv("WHATSAPP_PROVIDER", "meta").strip().lower()
        self.WHATSAPP_TOKEN: str = (os.getenv("WHATSAPP_TOKEN", "") or "").strip()
        self.WHATSAPP_PHONE_NUMBER_ID: str = (os.getenv("WHATSAPP_PHONE_NUMBER_ID", "") or "").strip()
        self.WHATSAPP_VERIFY_TOKEN: str = (os.getenv("WHATSAPP_VERIFY_TOKEN") or "").strip()
        if not self.WHATSAPP_VERIFY_TOKEN and not is_production_environment(self.ENV):
            self.WHATSAPP_VERIFY_TOKEN = "dev-whatsapp-verify-token"
        self.WHATSAPP_BUSINESS_PHONE: str = os.getenv("WHATSAPP_BUSINESS_PHONE", "+919876543210")
        self.WHATSAPP_GRAPH_API_VERSION: str = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v20.0")
        self.META_APP_SECRET: str = (os.getenv("META_APP_SECRET", "") or "").strip()
        self.UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
        self.MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))
        self.MEDIA_STORAGE_BACKEND: str = os.getenv("MEDIA_STORAGE_BACKEND", "local").strip().lower()
        self.R2_ACCOUNT_ID: str = (os.getenv("R2_ACCOUNT_ID", "") or "").strip()
        self.R2_ENDPOINT_URL: str = (os.getenv("R2_ENDPOINT_URL", "") or "").strip()
        self.R2_BUCKET_NAME: str = (os.getenv("R2_BUCKET_NAME", os.getenv("R2_BUCKET", "")) or "").strip()
        self.R2_ACCESS_KEY_ID: str = (os.getenv("R2_ACCESS_KEY_ID", "") or "").strip()
        self.R2_SECRET_ACCESS_KEY: str = (os.getenv("R2_SECRET_ACCESS_KEY", "") or "").strip()
        self.R2_PUBLIC_URL: str = (os.getenv("R2_PUBLIC_URL", os.getenv("R2_CUSTOM_DOMAIN", "")) or "").strip()
        # Supabase Storage settings
        self.SUPABASE_URL: str = (os.getenv("SUPABASE_URL", "") or "").strip()
        self.SUPABASE_SERVICE_ROLE_KEY: str = (os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
        self.SUPABASE_STORAGE_BUCKET: str = (os.getenv("SUPABASE_STORAGE_BUCKET", "complaint-images") or "").strip()
        self.SUPABASE_SIGNED_URL_TTL_SECONDS: int = int(os.getenv("SUPABASE_SIGNED_URL_TTL_SECONDS", "900"))
        # Twilio credentials kept for existing WhatsApp bot (whatsapp_service.py)
        self.TWILIO_ACCOUNT_SID: str = (os.getenv("TWILIO_ACCOUNT_SID", "") or "").strip()
        self.TWILIO_AUTH_TOKEN: str = (os.getenv("TWILIO_AUTH_TOKEN", "") or "").strip()
        self.TWILIO_WHATSAPP_NUMBER: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
        self.TWILIO_WEBHOOK_URL: str = (os.getenv("TWILIO_WEBHOOK_URL", "") or "").strip()

        # Meta WhatsApp Cloud API OTP delivery configuration
        # META_WHATSAPP_ACCESS_TOKEN and META_WHATSAPP_PHONE_NUMBER_ID alias the existing
        # WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID bot credentials if not separately set.
        self.META_WHATSAPP_ACCESS_TOKEN: str = (
            os.getenv("META_WHATSAPP_ACCESS_TOKEN", "") or
            os.getenv("WHATSAPP_TOKEN", "") or ""
        ).strip()
        self.META_WHATSAPP_PHONE_NUMBER_ID: str = (
            os.getenv("META_WHATSAPP_PHONE_NUMBER_ID", "") or
            os.getenv("WHATSAPP_PHONE_NUMBER_ID", "") or ""
        ).strip()
        self.META_OTP_TEMPLATE_NAME: str = os.getenv("META_OTP_TEMPLATE_NAME", "ecopulse_otp").strip()
        self.META_OTP_TEMPLATE_LANGUAGE: str = os.getenv("META_OTP_TEMPLATE_LANGUAGE", "en").strip()
        self.META_GRAPH_API_VERSION: str = (
            os.getenv("META_GRAPH_API_VERSION", "") or
            os.getenv("WHATSAPP_GRAPH_API_VERSION", "v22.0") or "v22.0"
        ).strip()
        self.META_OTP_TEMPLATE_CATEGORY: str = os.getenv("META_OTP_TEMPLATE_CATEGORY", "AUTHENTICATION").strip().upper()
        self.META_OTP_TEMPLATE_HAS_BUTTON: bool = (
            os.getenv("META_OTP_TEMPLATE_HAS_BUTTON", "true").strip().lower() == "true"
        )
        self.META_OTP_TEMPLATE_HAS_BUTTON_EXPLICIT: bool = "META_OTP_TEMPLATE_HAS_BUTTON" in os.environ
        self.META_OTP_TEMPLATE_HAS_URL_BUTTON: bool = (
            os.getenv("META_OTP_TEMPLATE_HAS_URL_BUTTON", "true").strip().lower() == "true"
        )
        self.OTP_DELIVERY_PROVIDER: str = os.getenv(
            "OTP_DELIVERY_PROVIDER",
            "meta_whatsapp" if self.ENV == "production" else "development"
        ).strip().lower()

        # SMS Gateway & Mobile OTP configuration (Indian DLT-compliant gateway)
        self.SMS_PROVIDER: str = os.getenv("SMS_PROVIDER", "mock" if self.ENV != "production" else "msg91").strip().lower()
        self.SMS_API_KEY: str = (os.getenv("SMS_API_KEY", "") or "").strip()
        self.SMS_SENDER_ID: str = (os.getenv("SMS_SENDER_ID", "ECPULS") or "ECPULS").strip()
        self.SMS_TEMPLATE_ID: str = (os.getenv("SMS_TEMPLATE_ID", "") or "").strip()
        self.SMS_OTP_EXPIRY_SECONDS: int = int(os.getenv("SMS_OTP_EXPIRY_SECONDS", "300"))
        self.SMS_RESEND_COOLDOWN_SECONDS: int = int(os.getenv("SMS_RESEND_COOLDOWN_SECONDS", "60"))

        # Municipality branding & configuration
        self.MUNICIPALITY_NAME: str = os.getenv("MUNICIPALITY_NAME", "Dhule Municipal Waste Management")
        self.MUNICIPALITY_NAME_MR: str = os.getenv("MUNICIPALITY_NAME_MR", "धुळे महानगरपालिका स्वच्छता व्यवस्थापन")
        self.FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://ecopulse-ai-frontend.onrender.com/").rstrip("/") + "/"
        self.TRACKING_PREFIX: str = os.getenv("TRACKING_PREFIX", "DHL-")

    @property
    def CORS_ORIGINS(self) -> list[str]:
        raw = os.getenv("CORS_ORIGINS", os.getenv("BACKEND_CORS_ORIGINS", "")).strip()
        parsed: list[str] = []
        if raw:
            parsed = [orig.strip().rstrip("/") for orig in raw.split(",") if orig.strip()]
        if not parsed:
            env = normalize_environment(os.getenv("ENV", os.getenv("ENVIRONMENT", self.ENV)))
            if env == "production":
                return []
            parsed = [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "https://ecopulse-ai-frontend.onrender.com",
            ]
        invalid = [origin for origin in parsed if not is_valid_http_origin(origin)]
        if invalid:
            raise ValueError(f"Invalid CORS origin configured: {invalid[0]}")
        return parsed

    def validate_production_settings(self) -> None:
        self.reload()
        env_name = normalize_environment(os.getenv("ENV", os.getenv("ENVIRONMENT", self.ENV)))
        if env_name != "production":
            return

        secret_key = (os.getenv("SECRET_KEY", self.SECRET_KEY) or "").strip()
        if is_insecure_secret(secret_key):
            raise RuntimeError("CRITICAL CONFIGURATION ERROR: SECRET_KEY must be set to a strong, non-empty value in production environment.")

        cors_origins = self.CORS_ORIGINS
        if not cors_origins:
            raise RuntimeError("CRITICAL CONFIGURATION ERROR: CORS_ORIGINS (or BACKEND_CORS_ORIGINS) must be set to a non-empty list of allowed origins in production environment.")

        if any("localhost" in origin.lower() or "127.0.0.1" in origin.lower() for origin in cors_origins):
            raise RuntimeError("CRITICAL CONFIGURATION ERROR: localhost development origins are not permitted in production CORS configuration.")

        provider = (os.getenv("WHATSAPP_PROVIDER") or "").strip().lower()
        if provider == "meta":
            missing = [
                name for name, value in {
                    "WHATSAPP_VERIFY_TOKEN": (os.getenv("WHATSAPP_VERIFY_TOKEN") or self.WHATSAPP_VERIFY_TOKEN or "").strip(),
                    "META_APP_SECRET": (os.getenv("META_APP_SECRET") or self.META_APP_SECRET or "").strip(),
                    "WHATSAPP_TOKEN": (os.getenv("WHATSAPP_TOKEN") or self.WHATSAPP_TOKEN or "").strip(),
                    "WHATSAPP_PHONE_NUMBER_ID": (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or self.WHATSAPP_PHONE_NUMBER_ID or "").strip(),
                }.items() if not value
            ]
            if missing:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Meta WhatsApp production settings are incomplete: "
                    + ", ".join(missing)
                )

        if provider == "twilio":
            twilio_account_sid = (os.getenv("TWILIO_ACCOUNT_SID") or self.TWILIO_ACCOUNT_SID or "").strip()
            twilio_auth_token = (os.getenv("TWILIO_AUTH_TOKEN") or self.TWILIO_AUTH_TOKEN or "").strip()
            twilio_webhook_url = (os.getenv("TWILIO_WEBHOOK_URL") or self.TWILIO_WEBHOOK_URL or "").strip()
            if not twilio_account_sid or not twilio_auth_token or not twilio_webhook_url:
                raise RuntimeError("CRITICAL CONFIGURATION ERROR: Twilio production settings require TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_WEBHOOK_URL.")

        # Validate Meta OTP delivery in production
        otp_provider = (os.getenv("OTP_DELIVERY_PROVIDER") or "").strip().lower()
        if otp_provider == "meta_whatsapp":
            missing_otp = []
            if not self.META_WHATSAPP_ACCESS_TOKEN:
                missing_otp.append("META_WHATSAPP_ACCESS_TOKEN (or WHATSAPP_TOKEN)")
            if not self.META_WHATSAPP_PHONE_NUMBER_ID:
                missing_otp.append("META_WHATSAPP_PHONE_NUMBER_ID (or WHATSAPP_PHONE_NUMBER_ID)")
            if missing_otp:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Meta WhatsApp OTP delivery settings are incomplete: "
                    + ", ".join(missing_otp)
                )

        storage_backend = (os.getenv("MEDIA_STORAGE_BACKEND") or self.MEDIA_STORAGE_BACKEND or "local").strip().lower()
        if storage_backend in ("r2", "s3", "cloudflare"):
            missing_r2 = []
            if not (os.getenv("R2_BUCKET_NAME") or os.getenv("R2_BUCKET") or self.R2_BUCKET_NAME):
                missing_r2.append("R2_BUCKET_NAME")
            if not (os.getenv("R2_ACCESS_KEY_ID") or self.R2_ACCESS_KEY_ID):
                missing_r2.append("R2_ACCESS_KEY_ID")
            if not (os.getenv("R2_SECRET_ACCESS_KEY") or self.R2_SECRET_ACCESS_KEY):
                missing_r2.append("R2_SECRET_ACCESS_KEY")
            if not (os.getenv("R2_ENDPOINT_URL") or self.R2_ENDPOINT_URL) and not (os.getenv("R2_ACCOUNT_ID") or self.R2_ACCOUNT_ID):
                missing_r2.append("R2_ACCOUNT_ID (or R2_ENDPOINT_URL)")
            if missing_r2:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Cloudflare R2 storage settings are incomplete: "
                    + ", ".join(missing_r2)
                )

        if storage_backend == "supabase":
            missing_sb = []
            if not (os.getenv("SUPABASE_URL") or self.SUPABASE_URL):
                missing_sb.append("SUPABASE_URL")
            if not (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or self.SUPABASE_SERVICE_ROLE_KEY):
                missing_sb.append("SUPABASE_SERVICE_ROLE_KEY")
            if not (os.getenv("SUPABASE_STORAGE_BUCKET") or self.SUPABASE_STORAGE_BUCKET):
                missing_sb.append("SUPABASE_STORAGE_BUCKET")
            if missing_sb:
                raise RuntimeError(
                    "CRITICAL CONFIGURATION ERROR: Supabase storage settings are incomplete: "
                    + ", ".join(missing_sb)
                )


config = Config()

