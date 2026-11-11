"""
Automated tests for Phase 2: Meta WhatsApp OTP Delivery Observability.
Covers wamid persistence, delivery status lifecycle (sent, delivered, read, failed),
duplicate & out-of-order callback protection, webhook integration, and non-interference.
"""

import hmac
import hashlib
import json
import pytest
from datetime import datetime, timezone
from starlette.testclient import TestClient

from server.main import app
from server.database.db import SessionLocal
from server.models.mobile_otp import MobileOtpToken
from server.models.complaint import Complaint
from server.models.user import User
from server.services.auth_service import AuthService
from server.services.otp_delivery.base import OtpDeliveryProvider, OtpDeliveryResult
from server.services.otp_delivery.factory import set_otp_delivery_provider_for_testing
from server.utils.config import config

client = TestClient(app)


class MockWamidOtpProvider(OtpDeliveryProvider):
    """Test provider returning predictable wamid message IDs."""

    def __init__(self, wamid: str = "wamid.HBgLMTestWamid12345"):
        self.wamid = wamid
        self.dispatched = []

    @property
    def provider_name(self) -> str:
        return "mock_wamid_provider"

    def send_otp(self, e164_phone: str, otp: str) -> OtpDeliveryResult:
        self.dispatched.append((e164_phone, otp))
        return OtpDeliveryResult(
            success=True,
            provider=self.provider_name,
            message="OTP dispatched successfully.",
            provider_message_id=self.wamid,
        )


def generate_meta_signature(raw_body: bytes, secret: str = None) -> str:
    """Generates a valid X-Hub-Signature-256 header for test webhook requests."""
    secret = secret or config.META_APP_SECRET or "dev-meta-app-secret-1234567890123456"
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_provider():
    yield
    set_otp_delivery_provider_for_testing(None)


def test_wamid_persistence_on_successful_dispatch(db_session):
    """When an OTP is dispatched, the provider wamid and ACCEPTED status must be persisted in MobileOtpToken."""
    test_wamid = "wamid.HBgLMPersistTest999"
    set_otp_delivery_provider_for_testing(MockWamidOtpProvider(wamid=test_wamid))

    phone = "9876500001"
    # Clean up previous tokens and ensure unregistered
    db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
    db_session.query(User).filter(User.phone == phone).delete()
    db_session.commit()

    res = AuthService.send_otp(db_session, phone=phone, purpose="register")
    assert res["success"] is True
    assert res["delivery_status"] == "ACCEPTED"

    # Verify database persistence
    token = db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).first()
    assert token is not None
    assert token.provider_message_id == test_wamid
    assert token.delivery_status == "ACCEPTED"
    assert token.delivery_error_code is None
    assert token.delivery_error_message is None

    # Verify challenge status endpoint exposes delivery_status but keeps provider_message_id internal
    challenge_id = res["challenge_id"]
    status_res = AuthService.get_challenge_status(db_session, challenge_id)
    assert status_res["delivery_status"] == "ACCEPTED"
    assert "provider_message_id" not in status_res


def test_status_callback_sent_transition(db_session):
    """Callback with status 'sent' transitions delivery_status to SENT."""
    test_wamid = "wamid.HBgLMSentTest111"
    set_otp_delivery_provider_for_testing(MockWamidOtpProvider(wamid=test_wamid))
    phone = "9876500002"

    db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
    db_session.query(User).filter(User.phone == phone).delete()
    db_session.commit()

    AuthService.send_otp(db_session, phone=phone, purpose="register")

    # Simulate Meta 'sent' status callback
    status_obj = {
        "id": test_wamid,
        "status": "sent",
        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "recipient_id": f"91{phone}",
    }

    updated = AuthService.process_meta_delivery_status(db_session, status_obj)
    assert updated is not None
    assert updated.delivery_status == "SENT"
    assert updated.delivery_error_code is None


def test_status_callback_delivered_transition(db_session):
    """Callback with status 'delivered' transitions delivery_status to DELIVERED and sets delivered_at."""
    test_wamid = "wamid.HBgLMDeliveredTest222"
    set_otp_delivery_provider_for_testing(MockWamidOtpProvider(wamid=test_wamid))
    phone = "9876500003"

    db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
    db_session.query(User).filter(User.phone == phone).delete()
    db_session.commit()

    AuthService.send_otp(db_session, phone=phone, purpose="register")

    ts = 1731234567
    status_obj = {
        "id": test_wamid,
        "status": "delivered",
        "timestamp": str(ts),
        "recipient_id": f"91{phone}",
    }

    updated = AuthService.process_meta_delivery_status(db_session, status_obj)
    assert updated is not None
    assert updated.delivery_status == "DELIVERED"
    assert updated.delivered_at is not None
    delivered_at = updated.delivered_at.replace(tzinfo=timezone.utc) if updated.delivered_at.tzinfo is None else updated.delivered_at
    assert int(delivered_at.timestamp()) == ts


def test_status_callback_read_transition(db_session):
    """Callback with status 'read' transitions delivery_status to READ."""
    test_wamid = "wamid.HBgLMReadTest333"
    set_otp_delivery_provider_for_testing(MockWamidOtpProvider(wamid=test_wamid))
    phone = "9876500004"

    db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
    db_session.query(User).filter(User.phone == phone).delete()
    db_session.commit()

    AuthService.send_otp(db_session, phone=phone, purpose="register")

    status_obj = {
        "id": test_wamid,
        "status": "read",
        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "recipient_id": f"91{phone}",
    }

    updated = AuthService.process_meta_delivery_status(db_session, status_obj)
    assert updated is not None
    assert updated.delivery_status == "READ"


def test_status_callback_failed_transition(db_session):
    """Callback with status 'failed' records FAILED and captures Meta error code and message."""
    test_wamid = "wamid.HBgLMFailedTest444"
    set_otp_delivery_provider_for_testing(MockWamidOtpProvider(wamid=test_wamid))
    phone = "9876500005"

    db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
    db_session.query(User).filter(User.phone == phone).delete()
    db_session.commit()

    AuthService.send_otp(db_session, phone=phone, purpose="register")

    status_obj = {
        "id": test_wamid,
        "status": "failed",
        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "recipient_id": f"91{phone}",
        "errors": [
            {
                "code": 131026,
                "title": "Message Undeliverable",
                "message": "Cloud API message could not be delivered to the recipient handset.",
            }
        ],
    }

    updated = AuthService.process_meta_delivery_status(db_session, status_obj)
    assert updated is not None
    assert updated.delivery_status == "FAILED"
    assert updated.delivery_error_code == "131026"
    assert "Message Undeliverable" in updated.delivery_error_message


def test_duplicate_callbacks_handling(db_session):
    """Duplicate status callbacks are safely handled idempotently."""
    test_wamid = "wamid.HBgLMDupTest555"
    set_otp_delivery_provider_for_testing(MockWamidOtpProvider(wamid=test_wamid))
    phone = "9876500006"

    db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
    db_session.query(User).filter(User.phone == phone).delete()
    db_session.commit()

    AuthService.send_otp(db_session, phone=phone, purpose="register")

    status_obj = {
        "id": test_wamid,
        "status": "delivered",
        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
        "recipient_id": f"91{phone}",
    }

    # First delivery
    first_res = AuthService.process_meta_delivery_status(db_session, status_obj)
    assert first_res.delivery_status == "DELIVERED"

    # Duplicate delivery
    second_res = AuthService.process_meta_delivery_status(db_session, status_obj)
    assert second_res.delivery_status == "DELIVERED"


def test_out_of_order_callbacks_handling(db_session):
    """Out-of-order callbacks do not downgrade higher precedence statuses (e.g. sent after delivered)."""
    test_wamid = "wamid.HBgLMOutOfOrderTest666"
    set_otp_delivery_provider_for_testing(MockWamidOtpProvider(wamid=test_wamid))
    phone = "9876500007"

    db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
    db_session.query(User).filter(User.phone == phone).delete()
    db_session.commit()

    AuthService.send_otp(db_session, phone=phone, purpose="register")

    # 1. 'delivered' arrives first
    AuthService.process_meta_delivery_status(
        db_session,
        {"id": test_wamid, "status": "delivered", "recipient_id": f"91{phone}"},
    )

    token = db_session.query(MobileOtpToken).filter(MobileOtpToken.provider_message_id == test_wamid).first()
    assert token.delivery_status == "DELIVERED"

    # 2. Delayed 'sent' arrives second — must NOT downgrade status to SENT
    AuthService.process_meta_delivery_status(
        db_session,
        {"id": test_wamid, "status": "sent", "recipient_id": f"91{phone}"},
    )

    db_session.refresh(token)
    assert token.delivery_status == "DELIVERED"

    # 3. Late 'failed' after confirmed delivered must NOT downgrade status to FAILED
    AuthService.process_meta_delivery_status(
        db_session,
        {"id": test_wamid, "status": "failed", "recipient_id": f"91{phone}", "errors": [{"code": 131026}]},
    )

    db_session.refresh(token)
    assert token.delivery_status == "DELIVERED"


def test_unknown_wamid_status_callback(db_session):
    """Status callback for an unknown or non-OTP wamid returns None without raising."""
    status_obj = {
        "id": "wamid.HBgLMUnknownMessageId777",
        "status": "delivered",
        "recipient_id": "919876543210",
    }
    result = AuthService.process_meta_delivery_status(db_session, status_obj)
    assert result is None


def test_webhook_status_processing_integration(db_session, monkeypatch):
    """
    POST /api/whatsapp/webhook with statuses updates token and never triggers
    complaint creation or message processing side effects.
    """
    secret = "test-webhook-secret-32-chars-long!"
    monkeypatch.setattr(config, "META_APP_SECRET", secret)

    test_wamid = "wamid.HBgLMWebhookInteg888"
    set_otp_delivery_provider_for_testing(MockWamidOtpProvider(wamid=test_wamid))
    phone = "9876500008"

    db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
    db_session.query(User).filter(User.phone == phone).delete()
    db_session.commit()

    AuthService.send_otp(db_session, phone=phone, purpose="register")

    initial_complaints_count = db_session.query(Complaint).count()

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_TEST_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "123456789",
                            },
                            "statuses": [
                                {
                                    "id": test_wamid,
                                    "status": "delivered",
                                    "timestamp": "1731234567",
                                    "recipient_id": f"91{phone}",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    raw_body = json.dumps(payload).encode("utf-8")
    sig = generate_meta_signature(raw_body, secret)

    res = client.post(
        "/api/whatsapp/webhook",
        content=raw_body,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )

    assert res.status_code == 200

    # Verify status was updated
    token = db_session.query(MobileOtpToken).filter(MobileOtpToken.provider_message_id == test_wamid).first()
    assert token.delivery_status == "DELIVERED"

    # Verify ZERO complaints were created by status webhook
    final_complaints_count = db_session.query(Complaint).count()
    assert final_complaints_count == initial_complaints_count

def test_missing_migration_compatibility_check(monkeypatch):
    """
    check_mobile_otp_tokens_schema must detect missing columns, log a clear
    error, return False, and NEVER execute ALTER TABLE or modify schemas at runtime.
    """
    from sqlalchemy import create_engine, text
    from server.models.mobile_otp import check_mobile_otp_tokens_schema
    import logging

    # Create an in-memory test database with legacy mobile_otp_tokens table (no migration 005)
    legacy_engine = create_engine("sqlite:///:memory:")
    with legacy_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE mobile_otp_tokens (
                id INTEGER PRIMARY KEY,
                phone VARCHAR(20) NOT NULL,
                otp_hash VARCHAR(64) NOT NULL,
                purpose VARCHAR(20) NOT NULL,
                ip_address VARCHAR(50),
                attempts INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                consumed_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL
            )
        """))
        conn.commit()

    # Capture logs
    error_logs = []
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            error_logs.append(record.getMessage())

    logger = logging.getLogger("server.models.mobile_otp")
    handler = InterceptHandler()
    logger.addHandler(handler)
    try:
        is_compatible = check_mobile_otp_tokens_schema(legacy_engine)
        assert is_compatible is False
        assert any("SCHEMA COMPATIBILITY ERROR" in msg for msg in error_logs)
        assert any("005_meta_otp_delivery_observability.sql" in msg for msg in error_logs)

        # Verify table was NOT altered (schema remained untouched)
        from sqlalchemy import inspect
        insp = inspect(legacy_engine)
        cols = {col["name"] for col in insp.get_columns("mobile_otp_tokens")}
        assert "provider_message_id" not in cols
        assert "delivery_status" not in cols
    finally:
        logger.removeHandler(handler)


def test_transaction_integrity_when_observability_commit_fails_preserves_otp_challenge(db_session, monkeypatch):
    """
    CRITICAL VERIFICATION:
    If persisting provider_message_id/delivery_status raises an exception (e.g. unapplied migration 005),
    the transaction rollback must NOT delete or invalidate the OTP challenge.
    The challenge must remain persisted and verifiable via AuthService.verify_otp.
    """
    test_wamid = "wamid.HBgLMErrorRecoveryTest"
    provider = MockWamidOtpProvider(wamid=test_wamid)
    set_otp_delivery_provider_for_testing(provider)

    phone = "9876500009"
    db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
    db_session.query(User).filter(User.phone == phone).delete()
    db_session.commit()

    # Intercept commits: allow initial commit (line 263), but raise exception on the observability commit (line 296)
    original_commit = db_session.commit
    commit_calls = 0

    def faulty_commit():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:  # 2nd commit is line 296 (observability persistence)
            from sqlalchemy.exc import OperationalError
            raise OperationalError("UPDATE mobile_otp_tokens", {}, Exception("no such column: provider_message_id"))
        return original_commit()

    monkeypatch.setattr(db_session, "commit", faulty_commit)

    # Dispatch OTP
    res = AuthService.send_otp(db_session, phone=phone, purpose="register")
    assert res["success"] is True
    assert "challenge_id" in res
    challenge_id = res["challenge_id"]

    # Verify token is STILL in DB (rollback did NOT delete it)
    token = db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).first()
    assert token is not None
    assert token.consumed_at is None
    # provider_message_id was rolled back due to error
    assert token.provider_message_id is None

    # Retrieve dispatched OTP from mock provider
    assert len(provider.dispatched) == 1
    dispatched_phone, plaintext_otp = provider.dispatched[0]

    # Verify the challenge remains 100% verifiable via verify_otp
    monkeypatch.setattr(db_session, "commit", original_commit)  # restore commit for verification
    verification_res = AuthService.verify_otp(
        db_session,
        phone=phone,
        otp=plaintext_otp,
        purpose="register",
        challenge_id=challenge_id
    )
    assert verification_res is not None

    # Verify token is now consumed
    db_session.refresh(token)
    assert token.consumed_at is not None


def test_failed_meta_dispatch_cleans_up_token_and_raises_503(db_session):
    """
    When Meta delivery provider returns success=False, the un-dispatched OTP token must be
    deleted from the database so the user is not locked or charged cooldown, and 503 is raised.
    """
    from fastapi import HTTPException

    class FailingOtpProvider(OtpDeliveryProvider):
        @property
        def provider_name(self) -> str:
            return "failing_provider"

        def send_otp(self, e164_phone: str, otp: str) -> OtpDeliveryResult:
            return OtpDeliveryResult(
                success=False,
                provider=self.provider_name,
                message="Meta Cloud API returned 500 internal server error",
                error_code="META_API_ERROR"
            )

    set_otp_delivery_provider_for_testing(FailingOtpProvider())

    phone = "9876500010"
    db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).delete()
    db_session.query(User).filter(User.phone == phone).delete()
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        AuthService.send_otp(db_session, phone=phone, purpose="register")

    assert exc_info.value.status_code == 503
    assert "WhatsApp OTP dispatch failed" in exc_info.value.detail

    # Verify token was cleaned up (deleted)
    token = db_session.query(MobileOtpToken).filter(MobileOtpToken.phone == phone).first()
    assert token is None


def test_process_meta_delivery_status_handles_db_commit_error_cleanly(db_session, monkeypatch):
    """
    When process_meta_delivery_status encounters a database commit error,
    it must catch the error, roll back the transaction, log it, and return safely.
    """
    test_wamid = "wamid.HBgLMRollbackTest999"
    token = MobileOtpToken(
        phone="9876500011",
        otp_hash="testhash12345",
        purpose="register",
        attempts=0,
        max_attempts=5,
        expires_at=datetime.now(timezone.utc),
        provider_message_id=test_wamid,
        delivery_status="ACCEPTED"
    )
    db_session.add(token)
    db_session.commit()

    original_commit = db_session.commit

    def failing_commit():
        raise Exception("Database disk full or connection dropped")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    status_obj = {
        "id": test_wamid,
        "status": "delivered",
        "timestamp": "1731234567",
        "recipient_id": "919876500011"
    }

    # Should not raise uncaught exception
    ret = AuthService.process_meta_delivery_status(db_session, status_obj)
    assert ret is not None

    monkeypatch.setattr(db_session, "commit", original_commit)
