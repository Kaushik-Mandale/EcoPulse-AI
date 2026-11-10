"""
Automated regression tests for CORS configuration and OPTIONS preflight handling.
Verifies production origin (https://ecopulse-ai-frontend.onrender.com) support across
the authentication OTP pipeline and standard API endpoints.
"""

import pytest
from starlette.testclient import TestClient
from server.main import app
from server.utils.config import config, Config

CANONICAL_ORIGIN = "https://ecopulse-ai-frontend.onrender.com"
DISALLOWED_ORIGIN = "https://malicious-site.example.com"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_cors_options_preflight_otp_send_approved_origin(client):
    """
    OPTIONS preflight to /api/auth/otp/send from the production frontend origin
    must return HTTP 200 with Access-Control-Allow-Origin, allowed methods (POST, OPTIONS),
    and allowed headers (content-type, authorization).
    """
    response = client.options(
        "/api/auth/otp/send",
        headers={
            "Origin": CANONICAL_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, authorization",
        },
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    assert response.headers.get("access-control-allow-origin") == CANONICAL_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"

    # Verify allowed methods
    allowed_methods = response.headers.get("access-control-allow-methods", "")
    assert "POST" in allowed_methods, f"POST not in allowed methods: {allowed_methods}"
    assert "OPTIONS" in allowed_methods, f"OPTIONS not in allowed methods: {allowed_methods}"

    # Verify allowed headers
    allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "content-type" in allowed_headers, f"content-type not in allowed headers: {allowed_headers}"
    assert "authorization" in allowed_headers, f"authorization not in allowed headers: {allowed_headers}"


def test_cors_options_preflight_otp_verify_approved_origin(client):
    """OPTIONS preflight to /api/auth/otp/verify must return HTTP 200 with proper CORS headers."""
    response = client.options(
        "/api/auth/otp/verify",
        headers={
            "Origin": CANONICAL_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == CANONICAL_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_actual_post_otp_send_includes_allow_origin(client):
    """
    POST to /api/auth/otp/send with Origin header must include
    Access-Control-Allow-Origin in the response, even on validation errors.
    """
    response = client.post(
        "/api/auth/otp/send",
        headers={"Origin": CANONICAL_ORIGIN},
        json={"phone": "invalid_number", "purpose": "login"},
    )

    # Regardless of endpoint validation status (400 or 422), CORS headers must be present
    assert response.headers.get("access-control-allow-origin") == CANONICAL_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_disallowed_origin_rejected(client):
    """
    OPTIONS preflight from an unapproved origin must NOT return
    Access-Control-Allow-Origin header and should return HTTP 400.
    """
    response = client.options(
        "/api/auth/otp/send",
        headers={
            "Origin": DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_request_disallowed_origin_omits_allow_origin(client):
    """Standard requests from unapproved origins must not receive Access-Control-Allow-Origin."""
    response = client.get(
        "/api/health",
        headers={"Origin": DISALLOWED_ORIGIN},
    )

    assert "access-control-allow-origin" not in response.headers


def test_cors_health_endpoint_allowed_origin(client):
    """Health check endpoint must correctly return CORS headers for canonical frontend origin."""
    response = client.get(
        "/api/health",
        headers={"Origin": CANONICAL_ORIGIN},
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == CANONICAL_ORIGIN
    assert response.json().get("status") == "healthy"


def test_cors_config_trailing_slash_normalization(monkeypatch):
    """Config.CORS_ORIGINS must strip trailing slashes from configured origins."""
    monkeypatch.setenv("CORS_ORIGINS", "https://ecopulse-ai-frontend.onrender.com/, https://custom.org/")
    cfg = Config()
    assert cfg.CORS_ORIGINS == [
        "https://ecopulse-ai-frontend.onrender.com",
        "https://custom.org",
    ]


def test_cors_config_default_includes_canonical_frontend(monkeypatch):
    """In development mode without explicit CORS_ORIGINS, default origins include canonical frontend."""
    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("BACKEND_CORS_ORIGINS", raising=False)
    cfg = Config()
    assert CANONICAL_ORIGIN in cfg.CORS_ORIGINS
    assert "http://localhost:5173" in cfg.CORS_ORIGINS

