import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.services.whatsapp_service import _build_texts
from server.utils.config import config
from server.database.db import SessionLocal
from server.models.user import User
from server.models.mobile_otp import MobileOtpToken
from server.utils.security import hash_password, create_access_token
from server.services.otp_delivery.base import OtpDeliveryProvider, OtpDeliveryResult
from server.services.otp_delivery.factory import set_otp_delivery_provider_for_testing

client = TestClient(app)


class _MockOtpProvider(OtpDeliveryProvider):
    """Deterministic mock that always succeeds — no Meta API calls, no cooldown state."""

    @property
    def provider_name(self) -> str:
        return "mock_branding_test"

    def send_otp(self, e164_phone: str, otp: str) -> OtpDeliveryResult:
        return OtpDeliveryResult(
            success=True,
            provider=self.provider_name,
            message=f"Mock OTP dispatched to {e164_phone}.",
            provider_message_id="mock-branding-001",
        )


def test_whatsapp_messages_no_obsolete_branding():
    """Verify WhatsApp messages contain EcoPulse AI and no obsolete City Swap branding."""
    texts = _build_texts()
    pattern = re.compile(r"city[\s_-]*swap", re.IGNORECASE)

    for lang in ["mr", "en"]:
        for key, text_val in texts[lang].items():
            if isinstance(text_val, str):
                assert not pattern.search(text_val), (
                    f"Found obsolete branding in texts['{lang}']['{key}']: {text_val}"
                )


def test_backend_api_title_and_description():
    """Verify FastAPI metadata uses official EcoPulse AI product branding."""
    assert "EcoPulse AI" in app.description
    assert "City Swap" not in app.description
    assert "CITY_SWAP" not in app.description


def test_frontend_index_and_sitemap_branding():
    """Verify client/index.html, robots.txt, and sitemap.xml have updated titles and domain URLs."""
    client_dir = Path("client")

    # index.html
    index_html = (client_dir / "index.html").read_text(encoding="utf-8")
    assert "<title>EcoPulse AI - Smart Civic & Sustainability Ecosystem</title>" in index_html
    assert "City Swap" not in index_html

    # robots.txt
    robots_txt = (client_dir / "public" / "robots.txt").read_text(encoding="utf-8")
    assert "https://ecopulse-ai-frontend.onrender.com/sitemap.xml" in robots_txt
    assert "city-swap" not in robots_txt

    # sitemap.xml
    sitemap_xml = (client_dir / "public" / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://ecopulse-ai-frontend.onrender.com" in sitemap_xml
    assert "city-swap" not in sitemap_xml


def test_citizen_auth_otp_and_password_preserved():
    """Verify citizen login supports both WhatsApp OTP and password authentication.

    Design for determinism and isolation:
    - A unique test phone is used (avoids cross-test cooldown collisions).
    - Stale MobileOtpToken rows for that phone are purged before the OTP call.
    - A mock OTP delivery provider is installed so no real Meta API call is made.
    - The mock is removed in a finally block to leave global state unchanged.
    - Asserts exactly HTTP 200 and the presence of challenge_id in the response body,
      confirming the full send pathway (user lookup → rate-limit check → token
      creation → delivery → response) succeeds end-to-end.
    """
    db = SessionLocal()
    # Fixed 10-digit Indian mobile matching validate_indian_mobile() format.
    # Unique to this test to avoid collisions with other test files.
    phone = "9900110011"
    email = "citizen_otp_pathway_test@ecopulse.ai"
    password = "TestPassword123!"

    # Install deterministic mock — prevents any real Meta API call and ensures
    # the delivery step always succeeds regardless of env configuration.
    mock_provider = _MockOtpProvider()
    set_otp_delivery_provider_for_testing(mock_provider)

    try:
        # -- Setup: create the citizen account ------------------------------------
        db.query(User).filter(User.email == email).delete()
        db.commit()

        user = User(
            full_name="OTP Pathway Citizen",
            email=email,
            phone=phone,
            hashed_password=hash_password(password),
            role="citizen",
            is_active=True,
        )
        db.add(user)
        db.commit()

        # Purge any pre-existing OTP tokens for this phone so the 60-second
        # resend cooldown cannot interfere (test isolation).
        db.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
        db.commit()

        # -- Step 1: Password login (email + password) ----------------------------
        pw_res = client.post(
            "/api/auth/login",
            json={"email": email, "password": password, "role": "citizen"},
        )
        assert pw_res.status_code == 200, (
            f"Password login failed: {pw_res.status_code} {pw_res.text}"
        )
        pw_data = pw_res.json()
        assert "access_token" in pw_data, "Missing access_token in login response"
        assert pw_data["user"]["role"] == "citizen"

        # -- Step 2: WhatsApp OTP send (login purpose) ----------------------------
        # With the mock provider active and tokens cleared, this MUST return 200.
        # Any other status is a genuine failure of the OTP authentication pathway.
        otp_res = client.post(
            "/api/auth/otp/send",
            json={"phone": phone, "channel": "whatsapp", "purpose": "login"},
        )
        assert otp_res.status_code == 200, (
            f"OTP send failed — expected 200, got {otp_res.status_code}: {otp_res.text}"
        )
        otp_data = otp_res.json()
        assert "challenge_id" in otp_data, (
            f"Missing challenge_id in OTP send response: {otp_data}"
        )

    finally:
        # Restore factory resolution — no test-scoped override left behind.
        set_otp_delivery_provider_for_testing(None)
        db.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
        db.query(User).filter(User.email == email).delete()
        db.commit()
        db.close()


def test_driver_and_admin_role_separation():
    """Verify driver and admin roles authenticate cleanly and maintain role isolation."""
    db = SessionLocal()
    driver_email = "driver_auth_test@ecopulse.ai"
    admin_email = "admin_auth_test@ecopulse.ai"
    pwd = "RolePassword123!"

    try:
        driver = User(
            full_name="Driver Mohan",
            email=driver_email,
            employee_id="DRV-TEST-01",
            hashed_password=hash_password(pwd),
            role="driver",
            is_active=True
        )
        admin = User(
            full_name="Admin Deshmukh",
            email=admin_email,
            employee_id="ADM-TEST-01",
            hashed_password=hash_password(pwd),
            role="admin",
            is_active=True
        )
        db.add_all([driver, admin])
        db.commit()

        # Driver login
        drv_res = client.post(
            "/api/auth/login",
            json={"email": driver_email, "password": pwd, "role": "driver"}
        )
        assert drv_res.status_code == 200
        assert drv_res.json()["user"]["role"] == "driver"

        # Admin login
        adm_res = client.post(
            "/api/auth/login",
            json={"email": admin_email, "password": pwd, "role": "admin"}
        )
        assert adm_res.status_code == 200
        assert adm_res.json()["user"]["role"] == "admin"

    finally:
        db.query(User).filter(User.email.in_([driver_email, admin_email])).delete()
        db.commit()
        db.close()
