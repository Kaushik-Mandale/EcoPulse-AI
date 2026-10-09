import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    def __init__(self):
        self.reload()

    def reload(self):
        self.PROJECT_NAME: str = os.getenv("PROJECT_NAME", "CITY_SWAP API")
        self.VERSION: str = os.getenv("VERSION", os.getenv("PROJECT_VERSION", "1.0.0"))
        self.ENV: str = os.getenv("ENV", os.getenv("ENVIRONMENT", "development"))
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "")
        self.PORT: int = int(os.getenv("PORT", 8000))
        self.WHATSAPP_PROVIDER: str = os.getenv("WHATSAPP_PROVIDER", "meta")
        self.WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
        self.WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self.WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "ecopulse_whatsapp_token_2026")
        self.WHATSAPP_BUSINESS_PHONE: str = os.getenv("WHATSAPP_BUSINESS_PHONE", "+919876543210")
        self.WHATSAPP_GRAPH_API_VERSION: str = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v20.0")
        self.META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
        self.UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
        self.MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", 10 * 1024 * 1024))
        self.TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.TWILIO_WHATSAPP_NUMBER: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

    @property
    def CORS_ORIGINS(self) -> list[str]:
        raw = os.getenv("CORS_ORIGINS", os.getenv("BACKEND_CORS_ORIGINS", "")).strip()
        if raw:
            return [orig.strip() for orig in raw.split(",") if orig.strip()]
        env = os.getenv("ENV", os.getenv("ENVIRONMENT", self.ENV)).strip().lower()
        if env == "production":
            return []
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000"
        ]

config = Config()
