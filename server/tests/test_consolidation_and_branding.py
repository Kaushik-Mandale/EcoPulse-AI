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
from server.tests.iam_test_helpers import login_admin
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


def test_activation_routes_role_contracts_and_dashboard_freshness_copy():
    client_dir = Path("client")
    app_js = (client_dir / "src" / "App.jsx").read_text(encoding="utf-8")
    activation_js = (
        client_dir / "src" / "pages" / "InvitationActivationPage.jsx"
    ).read_text(encoding="utf-8")
    auth_service_js = (
        client_dir / "src" / "services" / "authService.js"
    ).read_text(encoding="utf-8")
    collector_login_js = (
        client_dir / "src" / "components" / "auth" / "CollectorPortalLogin.jsx"
    ).read_text(encoding="utf-8")
    admin_dashboard_js = (
        client_dir / "src" / "pages" / "AdminDashboardPage.jsx"
    ).read_text(encoding="utf-8")
    citizen_dashboard_js = (
        client_dir / "src" / "pages" / "DashboardPage.jsx"
    ).read_text(encoding="utf-8")
    complaint_tracking_js = (
        client_dir / "src" / "pages" / "TrackComplaintPage.jsx"
    ).read_text(encoding="utf-8")

    driver_route = re.search(
        r'<Route\s+path={APP_ROUTE_PATHS\.driver}[\s\S]*?/>',
        app_js,
    )
    assert driver_route
    assert "allowedRoles={['driver']}" in driver_route.group(0)
    assert "admin" not in driver_route.group(0)
    assert '<Route path={APP_ROUTE_PATHS.activate} element={<InvitationActivationPage />} />' in app_js
    assert "activateDriverAccount" in activation_js
    assert "activateAdministratorAccount" in activation_js
    assert "confirmMfaEnrollment" in activation_js
    assert "window.history.replaceState" in activation_js
    assert "window.location.hash.slice(1)" in activation_js
    assert "new URLSearchParams" in activation_js
    assert "addEventListener('hashchange', handleInvitationLocation)" in activation_js
    assert "/activate#token=" not in admin_dashboard_js
    assert "activation_token" not in admin_dashboard_js
    assert "encodeURIComponent(token)" not in admin_dashboard_js
    assert "role: requestedRole" in collector_login_js
    assert '<option value="collector">Collector</option>' in collector_login_js
    assert "API data snapshot" in admin_dashboard_js
    assert "No live feed" in admin_dashboard_js
    assert "real-time" not in admin_dashboard_js.lower()
    assert "Live Telemetry" not in admin_dashboard_js
    assert "Live Dynamic Diagnostics" not in admin_dashboard_js
    assert "PostgreSQL Active" not in admin_dashboard_js
    assert "real-time" not in citizen_dashboard_js.lower()
    assert "real-time" not in complaint_tracking_js.lower()
    assert "export const validateInvitation" in auth_service_js


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
            is_verified=True,
        )
        db.add(user)
        db.commit()

        # Purge any pre-existing OTP tokens for this phone so the 60-second
        # resend cooldown cannot interfere (test isolation).
        db.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
        db.commit()

        # Preserve citizen password login alongside the WhatsApp OTP flow.
        pw_res = client.post(
            "/api/auth/login",
            json={"email": email, "password": password, "role": "citizen"},
        )
        assert pw_res.status_code == 200
        assert pw_res.json()["user"]["role"] == "citizen"

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
            is_active=True,
            is_verified=True,
        )
        admin = User(
            full_name="Admin Deshmukh",
            email=admin_email,
            employee_id="ADM-TEST-01",
            hashed_password=hash_password(pwd),
            role="admin",
            is_active=True,
            is_verified=True,
        )
        db.add_all([driver, admin])
        db.commit()

        # Driver login
        drv_res = client.post(
            "/api/auth/login",
            json={"email": "DRV-TEST-01", "password": pwd, "role": "driver"}
        )
        assert drv_res.status_code == 200
        assert drv_res.json()["user"]["role"] == "driver"

        # Admin login requires Employee ID, password, and a valid authenticator code.
        adm_res = login_admin(client, admin, pwd)
        assert adm_res.status_code == 200
        assert adm_res.json()["user"]["role"] == "admin"

    finally:
        db.query(User).filter(User.email.in_([driver_email, admin_email])).delete()
        db.commit()
        db.close()
