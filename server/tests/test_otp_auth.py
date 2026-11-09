"""
test_otp_auth.py — Comprehensive test suite for Meta WhatsApp OTP delivery,
FastAPI core authentication authority, security gates, and backward compatibility.
"""
import time
import re
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import httpx
import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.database.db import SessionLocal
from server.models.user import User
from server.models.mobile_otp import MobileOtpToken
from server.models.complaint import Complaint
from server.models.whatsapp_session import WhatsAppCitizen
from server.models.whatsapp_link_token import WhatsAppLinkToken
from server.utils.config import config
from server.services.otp_delivery.base import OtpDeliveryProvider, OtpDeliveryResult
from server.services.otp_delivery.factory import (
    get_otp_delivery_provider,
    set_otp_delivery_provider_for_testing
)
from server.services.otp_delivery.development import DevelopmentOtpProvider
from server.services.otp_delivery.meta_whatsapp import MetaWhatsAppOtpProvider
from server.services.auth_service import hash_otp

client = TestClient(app)

_REJECTED_MOCK_OTPS = {"000000", "111111", "999999"}


class MockMetaOtpProvider(OtpDeliveryProvider):
    """
    Controllable mock OTP delivery provider for testing.
    Records delivery calls and allows simulating upstream Meta API failures.
    """
    def __init__(self, should_fail: bool = False, error_code: str = "SIMULATED_FAILURE"):
        self.should_fail = should_fail
        self.error_code = error_code
        self.last_sent_phone = None
        self.last_sent_otp = None
        self.sent_count = 0

    @property
    def provider_name(self) -> str:
        return "mock_meta_whatsapp"

    def send_otp(self, e164_phone: str, otp: str) -> OtpDeliveryResult:
        if self.should_fail:
            return OtpDeliveryResult(
                success=False,
                provider=self.provider_name,
                message="Simulated Meta API failure.",
                error_code=self.error_code
            )
        if otp in _REJECTED_MOCK_OTPS:
            return OtpDeliveryResult(
                success=False,
                provider=self.provider_name,
                message=f"OTP {otp[:2]}**** is rejected by mock provider.",
                error_code="REJECTED_TEST_CODE"
            )
        self.last_sent_phone = e164_phone
        self.last_sent_otp = otp
        self.sent_count += 1
        return OtpDeliveryResult(
            success=True,
            provider=self.provider_name,
            message=f"Mock OTP dispatched to {e164_phone}.",
            provider_message_id=f"mock-wa-{self.sent_count}"
        )


@pytest.fixture(autouse=True)
def cleanup_test_state(monkeypatch):
    """Establish clean test environment with mock provider and wiped OTP tokens."""
    monkeypatch.setenv("ENV", "test")
    config.ENV = "test"

    mock_provider = MockMetaOtpProvider()
    set_otp_delivery_provider_for_testing(mock_provider)

    db = SessionLocal()
    try:
        db.query(MobileOtpToken).delete()
        db.commit()
    finally:
        db.close()

    yield mock_provider

    set_otp_delivery_provider_for_testing(None)

    db = SessionLocal()
    try:
        db.query(MobileOtpToken).delete()
        db.commit()
    finally:
        db.close()


# =============================================================================
# PART 1: Meta WhatsApp Cloud API Template Payload & HTTP Handling
# =============================================================================

def test_meta_template_components_building():
    """Verify Meta AUTHENTICATION template components strictly use sub_type='url' at runtime."""
    provider = MetaWhatsAppOtpProvider()
    components = provider._build_components("482910")

    # 1. Body component with OTP verification code
    body = next((c for c in components if c.get("type") == "body"), None)
    assert body is not None
    assert body["parameters"][0]["type"] == "text"
    assert body["parameters"][0]["text"] == "482910"

    # 2. Runtime button component: must strictly use sub_type='url' and index='0'
    button = next((c for c in components if c.get("type") == "button"), None)
    assert button is not None
    assert button["sub_type"] == "url"  # Meta Cloud API runtime strictly requires 'url'
    assert button["index"] == "0"
    assert button["parameters"][0]["type"] == "text"
    assert button["parameters"][0]["text"] == "482910"


def test_meta_runtime_payload_structure():
    """Verify exact JSON payload sent to Meta Cloud API /messages endpoint."""
    provider = MetaWhatsAppOtpProvider()
    payload = provider.build_payload("+919876543210", "654321")

    assert payload["messaging_product"] == "whatsapp"
    assert payload["recipient_type"] == "individual"
    assert payload["to"] == "919876543210"  # '+' sign stripped for Cloud API format
    assert payload["type"] == "template"

    template = payload["template"]
    assert template["name"] == config.META_OTP_TEMPLATE_NAME
    assert template["language"]["code"] == config.META_OTP_TEMPLATE_LANGUAGE
    assert len(template["components"]) == 2

    # Body component
    assert template["components"][0] == {
        "type": "body",
        "parameters": [{"type": "text", "text": "654321"}]
    }

    # Runtime button component
    assert template["components"][1] == {
        "type": "button",
        "sub_type": "url",
        "index": "0",
        "parameters": [{"type": "text", "text": "654321"}]
    }


def test_meta_recipient_formatting_strips_leading_plus():
    """Verify internal E.164 phone numbers have leading '+' stripped for Meta Cloud API serialization."""
    provider = MetaWhatsAppOtpProvider()

    # Standard Indian mobile with +91
    payload1 = provider.build_payload("+919876543210", "112233")
    assert payload1["to"] == "919876543210"

    # Number already without +
    payload2 = provider.build_payload("919876543210", "112233")
    assert payload2["to"] == "919876543210"

    # International number
    payload3 = provider.build_payload("+14155552671", "112233")
    assert payload3["to"] == "14155552671"


def test_meta_template_name_and_language_configurable(monkeypatch):
    """Verify template name and language code are dynamically configurable."""
    monkeypatch.setattr(config, "META_OTP_TEMPLATE_NAME", "custom_auth_template")
    monkeypatch.setattr(config, "META_OTP_TEMPLATE_LANGUAGE", "hi")

    provider = MetaWhatsAppOtpProvider()
    payload = provider.build_payload("+919876543210", "998877")

    assert payload["template"]["name"] == "custom_auth_template"
    assert payload["template"]["language"]["code"] == "hi"


def test_meta_template_button_can_be_disabled(monkeypatch):
    """Verify button component can be omitted if template does not have buttons."""
    monkeypatch.setattr(config, "META_OTP_TEMPLATE_HAS_BUTTON", False)
    monkeypatch.setattr(config, "META_OTP_TEMPLATE_HAS_URL_BUTTON", False)
    monkeypatch.setattr(config, "META_OTP_TEMPLATE_HAS_BUTTON_EXPLICIT", True)
    provider = MetaWhatsAppOtpProvider()
    components = provider._build_components("123456")
    assert len(components) == 1
    assert components[0]["type"] == "body"


def test_meta_provider_http_200_success(monkeypatch):
    """Meta API returns HTTP 200 with message ID -> delivery succeeds."""
    monkeypatch.setattr(config, "META_WHATSAPP_ACCESS_TOKEN", "mock_token")
    monkeypatch.setattr(config, "META_WHATSAPP_PHONE_NUMBER_ID", "123456789")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "messaging_product": "whatsapp",
        "contacts": [{"input": "+919876543210", "wa_id": "919876543210"}],
        "messages": [{"id": "wamid.HBgLM...test_id"}]
    }

    with patch.object(httpx.Client, "post", return_value=mock_resp):
        provider = MetaWhatsAppOtpProvider()
        result = provider.send_otp("+919876543210", "123456")
        assert result.success is True
        assert result.provider_message_id == "wamid.HBgLM...test_id"


def test_meta_provider_http_200_no_message_id(monkeypatch):
    """Meta API returns HTTP 200 but missing message ID -> treated as failure."""
    monkeypatch.setattr(config, "META_WHATSAPP_ACCESS_TOKEN", "mock_token")
    monkeypatch.setattr(config, "META_WHATSAPP_PHONE_NUMBER_ID", "123456789")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"messaging_product": "whatsapp", "messages": []}

    with patch.object(httpx.Client, "post", return_value=mock_resp):
        provider = MetaWhatsAppOtpProvider()
        result = provider.send_otp("+919876543210", "123456")
        assert result.success is False


def test_meta_provider_http_400_meta_rejection(monkeypatch):
    """Meta API returns HTTP 400 error response -> parsed gracefully, no crash."""
    monkeypatch.setattr(config, "META_WHATSAPP_ACCESS_TOKEN", "mock_token")
    monkeypatch.setattr(config, "META_WHATSAPP_PHONE_NUMBER_ID", "123456789")

    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "error": {
            "message": "(#132000) Number of parameters does not match template",
            "type": "OAuthException",
            "code": 132000
        }
    }

    with patch.object(httpx.Client, "post", return_value=mock_resp):
        provider = MetaWhatsAppOtpProvider()
        result = provider.send_otp("+919876543210", "123456")
        assert result.success is False
        assert result.error_code == "132000"


def test_meta_provider_http_401_invalid_token(monkeypatch):
    """Meta API returns HTTP 401 Unauthorized -> parsed as error, token not logged."""
    monkeypatch.setattr(config, "META_WHATSAPP_ACCESS_TOKEN", "invalid_token_secret")
    monkeypatch.setattr(config, "META_WHATSAPP_PHONE_NUMBER_ID", "123456789")

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {
        "error": {
            "message": "Invalid OAuth access token.",
            "type": "OAuthException",
            "code": 190
        }
    }

    with patch.object(httpx.Client, "post", return_value=mock_resp):
        provider = MetaWhatsAppOtpProvider()
        result = provider.send_otp("+919876543210", "123456")
        assert result.success is False
        assert result.error_code == "190"


def test_meta_provider_timeout_handling(monkeypatch):
    """Network timeout during Meta API call -> returns TIMEOUT result."""
    monkeypatch.setattr(config, "META_WHATSAPP_ACCESS_TOKEN", "mock_token")
    monkeypatch.setattr(config, "META_WHATSAPP_PHONE_NUMBER_ID", "123456789")

    with patch.object(httpx.Client, "post", side_effect=httpx.TimeoutException("Connection timed out")):
        provider = MetaWhatsAppOtpProvider()
        result = provider.send_otp("+919876543210", "123456")
        assert result.success is False
        assert result.error_code == "TIMEOUT"


def test_meta_provider_not_configured(monkeypatch):
    """Missing Meta credentials -> returns NOT_CONFIGURED without calling network."""
    monkeypatch.setattr(config, "META_WHATSAPP_ACCESS_TOKEN", "")
    monkeypatch.setattr(config, "META_WHATSAPP_PHONE_NUMBER_ID", "")

    provider = MetaWhatsAppOtpProvider()
    result = provider.send_otp("+919876543210", "123456")
    assert result.success is False
    assert result.error_code == "NOT_CONFIGURED"


# =============================================================================
# PART 2: Core FastAPI Authentication, Generation, Verification & Security
# =============================================================================

def test_01_successful_otp_request_login(cleanup_test_state):
    """1. OTP request generates 6-digit code, dispatches via provider, returns challenge_id."""
    mock = cleanup_test_state
    res = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "challenge_id" in data
    assert "otp" not in data  # Never expose OTP in response
    assert data["channel"] == "whatsapp"
    assert data["delivery_status"] == "ACCEPTED"
    assert mock.last_sent_phone == "+919876543210"
    assert len(mock.last_sent_otp) == 6


def test_02_invalid_mobile_number():
    """2. Invalid Indian mobile numbers are rejected with HTTP 400/422."""
    for bad_phone in ["12345", "987654321", "abcdefghij", "0000000000", "1234567890"]:
        res = client.post("/api/auth/otp/send", json={"phone": bad_phone, "purpose": "login"})
        assert res.status_code in (400, 422)


def test_03_existing_mobile_registration_rejection():
    """3. Registration for an existing mobile number is rejected with HTTP 409 Conflict."""
    res = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "register"})
    assert res.status_code in (400, 409)
    assert "already" in res.json()["detail"].lower()


def test_04_successful_otp_verification_login(cleanup_test_state):
    """4. Correct OTP code issues application JWT access_token and user info."""
    mock = cleanup_test_state
    res_send = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    assert res_send.status_code == 200
    challenge_id = res_send.json()["challenge_id"]

    res_verify = client.post("/api/auth/login/otp", json={
        "phone": "9876543210",
        "otp": mock.last_sent_otp,
        "challenge_id": challenge_id,
        "role": "citizen"
    })
    assert res_verify.status_code == 200
    data = res_verify.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["phone"] == "9876543210"


def test_05_incorrect_otp_returns_400(cleanup_test_state):
    """5. Incorrect OTP is rejected with HTTP 400 and tracks remaining attempts."""
    mock = cleanup_test_state
    res_send = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    challenge_id = res_send.json()["challenge_id"]

    res_verify = client.post("/api/auth/login/otp", json={
        "phone": "9876543210",
        "otp": "000001",
        "challenge_id": challenge_id,
        "role": "citizen"
    })
    assert res_verify.status_code == 400
    assert "invalid verification code" in res_verify.json()["detail"].lower()


def test_06_expired_otp_returns_400(cleanup_test_state):
    """6. Expired OTP challenge is rejected."""
    mock = cleanup_test_state
    res_send = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    challenge_id = res_send.json()["challenge_id"]

    # Manually expire the token in database
    db = SessionLocal()
    try:
        token = db.query(MobileOtpToken).filter(MobileOtpToken.phone == "9876543210").first()
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()
    finally:
        db.close()

    res_verify = client.post("/api/auth/login/otp", json={
        "phone": "9876543210",
        "otp": mock.last_sent_otp,
        "challenge_id": challenge_id,
        "role": "citizen"
    })
    assert res_verify.status_code == 400
    assert "expired" in res_verify.json()["detail"].lower()


def test_07_reused_otp_returns_400(cleanup_test_state):
    """7. Consumed OTP token cannot be re-used (single-use verification)."""
    mock = cleanup_test_state
    res_send = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    challenge_id = res_send.json()["challenge_id"]

    payload = {
        "phone": "9876543210",
        "otp": mock.last_sent_otp,
        "challenge_id": challenge_id,
        "role": "citizen"
    }

    # First attempt succeeds
    res1 = client.post("/api/auth/login/otp", json=payload)
    assert res1.status_code == 200

    # Second attempt with same token fails
    res2 = client.post("/api/auth/login/otp", json=payload)
    assert res2.status_code in (400, 410)


def test_08_otp_resend_cooldown(cleanup_test_state):
    """8. Requesting an OTP within the 60s cooldown is rejected with HTTP 429."""
    res1 = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    assert res1.status_code == 200

    res2 = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    assert res2.status_code == 429
    assert "seconds" in res2.json()["detail"].lower() or "wait" in res2.json()["detail"].lower()


def test_09_otp_max_attempts_lockout(cleanup_test_state):
    """9. Exceeding max 5 incorrect verification attempts locks out the challenge."""
    mock = cleanup_test_state
    res_send = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    challenge_id = res_send.json()["challenge_id"]

    for _ in range(5):
        client.post("/api/auth/login/otp", json={
            "phone": "9876543210",
            "otp": "000001",
            "challenge_id": challenge_id,
            "role": "citizen"
        })

    # 6th attempt is locked
    res_locked = client.post("/api/auth/login/otp", json={
        "phone": "9876543210",
        "otp": mock.last_sent_otp,
        "challenge_id": challenge_id,
        "role": "citizen"
    })
    assert res_locked.status_code == 400
    assert "maximum" in res_locked.json()["detail"].lower() or "locked" in res_locked.json()["detail"].lower()


def test_10_successful_citizen_registration_and_login(cleanup_test_state):
    """10. Full registration flow: request OTP -> register -> login with OTP."""
    mock = cleanup_test_state
    new_phone = "9822998877"

    # Clean up if existing
    db = SessionLocal()
    try:
        db.query(User).filter(User.phone == new_phone).delete()
        db.commit()
    finally:
        db.close()

    # Step 1: Request registration OTP
    res_send = client.post("/api/auth/otp/send", json={"phone": new_phone, "purpose": "register"})
    assert res_send.status_code == 200
    challenge_id = res_send.json()["challenge_id"]

    # Step 2: Register citizen
    res_reg = client.post("/api/auth/register", json={
        "full_name": "Gita Devi",
        "phone": new_phone,
        "email": "gita.devi@example.com",
        "otp": mock.last_sent_otp,
        "challenge_id": challenge_id,
        "role": "citizen"
    })
    assert res_reg.status_code == 200
    reg_data = res_reg.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["name"] == "Gita Devi"
    assert reg_data["user"]["role"] == "citizen"

    # Step 3: Login as existing citizen
    res_login_send = client.post("/api/auth/otp/send", json={"phone": new_phone, "purpose": "login"})
    assert res_login_send.status_code == 200
    login_challenge_id = res_login_send.json()["challenge_id"]

    res_login = client.post("/api/auth/login/otp", json={
        "phone": new_phone,
        "otp": mock.last_sent_otp,
        "challenge_id": login_challenge_id,
        "role": "citizen"
    })
    assert res_login.status_code == 200
    assert res_login.json()["user"]["name"] == "Gita Devi"


def test_11_optional_email_registration(cleanup_test_state):
    """11. Citizen registration succeeds without providing an email address."""
    mock = cleanup_test_state
    phone_no_email = "9822114455"

    db = SessionLocal()
    try:
        db.query(User).filter(User.phone == phone_no_email).delete()
        db.commit()
    finally:
        db.close()

    res_send = client.post("/api/auth/otp/send", json={"phone": phone_no_email, "purpose": "register"})
    assert res_send.status_code == 200
    challenge_id = res_send.json()["challenge_id"]

    res_reg = client.post("/api/auth/register", json={
        "full_name": "Suresh Patel",
        "phone": phone_no_email,
        "otp": mock.last_sent_otp,
        "challenge_id": challenge_id,
        "role": "citizen"
    })
    assert res_reg.status_code == 200
    assert res_reg.json()["user"]["name"] == "Suresh Patel"


def test_12_driver_public_registration_rejection(cleanup_test_state):
    """12. Public registration endpoint strictly forbids creating driver or admin accounts."""
    mock = cleanup_test_state
    phone_test = "9822334455"

    res_send = client.post("/api/auth/otp/send", json={"phone": phone_test, "purpose": "register"})
    challenge_id = res_send.json()["challenge_id"]

    for forbidden_role in ["driver", "admin", "collector", "supervisor"]:
        res = client.post("/api/auth/register", json={
            "full_name": "Unauthorized Driver",
            "phone": phone_test,
            "otp": mock.last_sent_otp,
            "challenge_id": challenge_id,
            "role": forbidden_role
        })
        assert res.status_code in (400, 403)


def test_13_jwt_validation_against_me_endpoint(cleanup_test_state):
    """13. JWT token returned by OTP authentication accesses /api/auth/me."""
    mock = cleanup_test_state
    res_send = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    challenge_id = res_send.json()["challenge_id"]

    res_verify = client.post("/api/auth/login/otp", json={
        "phone": "9876543210",
        "otp": mock.last_sent_otp,
        "challenge_id": challenge_id,
        "role": "citizen"
    })
    token = res_verify.json()["access_token"]

    res_me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    assert res_me.json()["phone"] == "9876543210"


def test_14_existing_password_login_backward_compatibility():
    """14. Existing password authentication for demo / admin users remains functional."""
    res = client.post("/api/auth/login", json={
        "email": "priya@cityswap.io",
        "password": "Password123!",
        "role": "citizen"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "citizen"


def test_15_citizen_cannot_access_driver_or_admin_routes(cleanup_test_state):
    """15. Citizen JWT tokens are blocked from accessing driver and admin routes."""
    mock = cleanup_test_state
    res_send = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    challenge_id = res_send.json()["challenge_id"]

    res_verify = client.post("/api/auth/login/otp", json={
        "phone": "9876543210",
        "otp": mock.last_sent_otp,
        "challenge_id": challenge_id,
        "role": "citizen"
    })
    token = res_verify.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Driver route
    res_driver = client.get("/api/driver/tasks", headers=headers)
    assert res_driver.status_code in (401, 403)

    # Admin route
    res_admin = client.get("/api/admin/metrics", headers=headers)
    assert res_admin.status_code in (401, 403)


def test_16_provider_failure_rolls_back_token_and_returns_503():
    """16. When OTP delivery fails, newly created DB token is deleted and HTTP 503 is returned."""
    fail_provider = MockMetaOtpProvider(should_fail=True)
    set_otp_delivery_provider_for_testing(fail_provider)

    res = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    assert res.status_code == 503

    # Token must NOT exist in DB so user is not penalized with cooldown
    db = SessionLocal()
    try:
        token = db.query(MobileOtpToken).filter(MobileOtpToken.phone == "9876543210").first()
        assert token is None
    finally:
        db.close()


def test_17_phone_normalization_handles_various_formats(cleanup_test_state):
    """17. Mobile number normalization handles spaces, hyphens, and +91 prefix."""
    formats = ["+91 9876543210", "+91-9876543210", "09876543210", "98765 43210"]
    for formatted_phone in formats:
        db = SessionLocal()
        try:
            db.query(MobileOtpToken).delete()
            db.commit()
        finally:
            db.close()

        res = client.post("/api/auth/otp/send", json={"phone": formatted_phone, "purpose": "login"})
        assert res.status_code == 200
        assert res.json()["success"] is True


def test_18_hmac_based_otp_hashing_verification(cleanup_test_state):
    """18. Database stores only HMAC-SHA256 hash; raw OTP is never stored in DB."""
    mock = cleanup_test_state
    client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})

    db = SessionLocal()
    try:
        token = db.query(MobileOtpToken).filter(MobileOtpToken.phone == "9876543210").first()
        assert token is not None
        assert token.otp_hash != mock.last_sent_otp
        assert len(token.otp_hash) == 64  # SHA-256 hex digest length
        assert hmac.compare_digest(hash_otp(mock.last_sent_otp), token.otp_hash)
    finally:
        db.close()


def test_19_development_provider_refuses_production(monkeypatch):
    """19. DevelopmentOtpProvider raises RuntimeError if instantiated in production."""
    monkeypatch.setenv("ENV", "production")
    config.ENV = "production"

    with pytest.raises(RuntimeError) as exc_info:
        DevelopmentOtpProvider()
    assert "production" in str(exc_info.value).lower()


def test_20_production_mode_disallows_mock_provider(monkeypatch):
    """20. get_otp_delivery_provider() raises in production if provider is not meta_whatsapp."""
    monkeypatch.setenv("ENV", "production")
    config.ENV = "production"
    monkeypatch.setattr(config, "OTP_DELIVERY_PROVIDER", "development")

    set_otp_delivery_provider_for_testing(None)

    with pytest.raises(RuntimeError) as exc_info:
        get_otp_delivery_provider()
    assert "meta_whatsapp" in str(exc_info.value).lower()


def test_21_challenge_status_authoritative_restoration(cleanup_test_state):
    """21. GET /api/auth/otp/challenge/{id} restores TTL, cooldown, and ownership."""
    res_send = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    assert res_send.status_code == 200
    challenge_id = res_send.json()["challenge_id"]

    res_status = client.get(f"/api/auth/otp/challenge/{challenge_id}")
    assert res_status.status_code == 200
    data = res_status.json()
    assert data["valid"] is True
    assert data["purpose"] == "login"
    assert data["seconds_remaining"] > 250
    assert data["attempts_remaining"] == 5


def test_22_expired_challenge_returns_valid_false(cleanup_test_state):
    """22. Challenge status for expired token returns valid=False and expired=True."""
    res_send = client.post("/api/auth/otp/send", json={"phone": "9876543210", "purpose": "login"})
    challenge_id = res_send.json()["challenge_id"]

    db = SessionLocal()
    try:
        token = db.query(MobileOtpToken).filter(MobileOtpToken.phone == "9876543210").first()
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db.commit()
    finally:
        db.close()

    res_status = client.get(f"/api/auth/otp/challenge/{challenge_id}")
    assert res_status.status_code == 200
    data = res_status.json()
    assert data["valid"] is False
    assert data["expired"] is True


def test_23_tampered_challenge_returns_404():
    """23. Tampered challenge HMAC signature returns HTTP 404."""
    tampered_id = "1:9876543210:login:1762607820:tampered_signature_123456"
    res = client.get(f"/api/auth/otp/challenge/{tampered_id}")
    assert res.status_code == 404


def test_24_purpose_binding_prevents_cross_use(cleanup_test_state):
    """24. Challenge created for registration cannot be used to login."""
    mock = cleanup_test_state
    new_phone = "9822887766"

    db = SessionLocal()
    try:
        db.query(User).filter(User.phone == new_phone).delete()
        db.commit()
    finally:
        db.close()

    res_send = client.post("/api/auth/otp/send", json={"phone": new_phone, "purpose": "register"})
    assert res_send.status_code == 200
    reg_challenge_id = res_send.json()["challenge_id"]

    # Attempt to use register challenge for login
    res_bad = client.post("/api/auth/login/otp", json={
        "phone": new_phone,
        "otp": mock.last_sent_otp,
        "challenge_id": reg_challenge_id,
        "role": "citizen"
    })
    assert res_bad.status_code == 400
    assert "purpose mismatch" in res_bad.json()["detail"].lower()


def test_25_whatsapp_account_linking_preserved():
    """25. Existing WhatsApp account linking tokens and identity mapping remain intact."""
    login_res = client.post("/api/auth/login", json={
        "email": "priya@cityswap.io",
        "password": "Password123!",
        "role": "citizen"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    code_res = client.post("/api/whatsapp/link/generate", headers=headers)
    assert code_res.status_code == 200
    code_data = code_res.json()
    assert "code" in code_data
    assert len(code_data["code"]) == 24


def test_26_complaint_ownership_foreign_key_intact():
    """26. Citizen complaints remain linked to the canonical user ID."""
    db = SessionLocal()
    user = db.query(User).filter(User.role == "citizen").first()
    assert user is not None

    complaint = Complaint(
        tracking_number="EP-2026-TEST-META-01",
        location_address="Near market ward 12",
        waste_type="Plastic Waste",
        description="Test waste description",
        ward="Ward 12",
        status="Pending",
        citizen_id=user.id
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)

    assert complaint.citizen_id == user.id
    db.delete(complaint)
    db.commit()
    db.close()


def test_27_existing_user_ids_remain_unchanged():
    """27. Canonical user IDs remain stable across logins."""
    db = SessionLocal()
    user_before = db.query(User).filter(User.email == "priya@cityswap.io").first()
    expected_id = user_before.id
    db.close()

    res = client.post("/api/auth/login", json={
        "email": "priya@cityswap.io",
        "password": "Password123!",
        "role": "citizen"
    })
    assert res.status_code == 200
    assert res.json()["user"]["id"] == expected_id


def test_28_existing_roles_remain_unchanged():
    """28. Existing roles (citizen, driver, admin) are strictly preserved."""
    db = SessionLocal()
    roles = {u.role for u in db.query(User).all()}
    db.close()

    assert "citizen" in roles
    assert "driver" in roles
    assert "admin" in roles
