"""
Tests for production-readiness requirements:
  - Health check endpoint (with DB probe)
  - Database configuration (production guards)
  - WhatsApp webhook verification handshake (GET)
"""
import os
import hmac
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_check_returns_200(self):
        response = client.get("/api/health")
        assert response.status_code == 200, response.text

    def test_health_check_has_db_ok(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["db"] == "ok", f"Expected db='ok', got: {data}"

    def test_health_check_has_timestamp(self):
        response = client.get("/api/health")
        data = response.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], float)


# ---------------------------------------------------------------------------
# Database Configuration Guards
# ---------------------------------------------------------------------------

class TestDatabaseConfig:
    def test_production_requires_database_url(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from server.database import db as db_module
        with pytest.raises(RuntimeError, match="DATABASE_URL is required in production"):
            db_module.get_database_url()

    def test_production_rejects_sqlite(self, monkeypatch):
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
        from server.database import db as db_module
        with pytest.raises(RuntimeError, match="SQLite is not allowed in production"):
            db_module.get_database_url()

    def test_development_allows_sqlite_fallback(self, monkeypatch):
        monkeypatch.setenv("ENV", "development")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from server.database import db as db_module
        url = db_module.get_database_url()
        assert url.startswith("sqlite"), f"Expected SQLite fallback, got: {url}"

    def test_postgres_url_rewrite(self, monkeypatch):
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host/db")
        from server.database import db as db_module
        url = db_module.get_database_url()
        assert url.startswith("postgresql://"), f"Expected postgresql://, got: {url}"

    def test_safe_url_logging_hides_password(self):
        from server.database.db import safe_database_url_for_logging
        safe = safe_database_url_for_logging("postgresql://user:supersecret@host:5432/mydb")
        assert "supersecret" not in safe
        assert "user" not in safe
        assert safe == "postgresql://***"


# ---------------------------------------------------------------------------
# WhatsApp Webhook GET Handshake
# ---------------------------------------------------------------------------

class TestWebhookVerification:
    def test_verify_webhook_correct_token(self, monkeypatch):
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test-verify-token-dev")
        from server.utils.config import config
        config.reload()
        response = client.get(
            "/api/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test-verify-token-dev",
                "hub.challenge": "challenge_abc123",
            },
        )
        assert response.status_code == 200, response.text
        assert response.text == "challenge_abc123"

    def test_verify_webhook_wrong_token_returns_403(self, monkeypatch):
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "correct-token")
        from server.utils.config import config
        config.reload()
        response = client.get(
            "/api/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "xyz",
            },
        )
        assert response.status_code == 403

    def test_verify_webhook_missing_mode_returns_403(self):
        response = client.get(
            "/api/whatsapp/webhook",
            params={"hub.verify_token": "any-token", "hub.challenge": "xyz"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Webhook POST Signature Validation
# ---------------------------------------------------------------------------

class TestWebhookSignature:
    def _make_signed_payload(self, body: bytes, secret: str) -> dict:
        sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return {"X-Hub-Signature-256": f"sha256={sig}"}

    def test_missing_signature_returns_403(self, monkeypatch):
        monkeypatch.setenv("META_APP_SECRET", "test-app-secret-1234567890ab")
        from server.utils.config import config
        config.reload()
        body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()
        response = client.post(
            "/api/whatsapp/webhook",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 403

    def test_invalid_signature_returns_403(self, monkeypatch):
        monkeypatch.setenv("META_APP_SECRET", "test-app-secret-1234567890ab")
        from server.utils.config import config
        config.reload()
        body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()
        response = client.post(
            "/api/whatsapp/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalidsignature",
            },
        )
        assert response.status_code == 403

    def test_no_app_secret_configured_returns_500(self, monkeypatch):
        monkeypatch.setenv("META_APP_SECRET", "")
        from server.utils.config import config
        config.reload()
        body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode()
        response = client.post(
            "/api/whatsapp/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=anything",
            },
        )
        assert response.status_code == 500
