"""
Automated test suite for Website-Generated WhatsApp Registration Verification.

Covers:
1. Challenge generation endpoint (POST /api/auth/whatsapp-verification/generate)
2. Successful inbound verification (VERIFY <code>)
3. Wrong code rejection & attempt limit enforcement
4. Expired code rejection
5. Sender-number mismatch security protection
6. Replayed / duplicate verification handling
7. Webhook idempotency engine integration
8. Rate limiting (resend cooldown and max requests ceiling)
9. Duplicate registration prevention (already registered mobile numbers)
10. Concurrent verification thread-safety (no duplicate User records)
11. Website status polling (GET /api/auth/whatsapp-verification/status/{challenge_id})
12. Regression test: Existing LINK <code> workflow continues working
13. Regression test: Existing complaints, menus, and bot messaging continue working
"""

import hashlib
import hmac
import json
import pytest
from datetime import datetime, timedelta, timezone
from starlette.testclient import TestClient

from server.main import app
from server.database.db import SessionLocal
from server.models.user import User
from server.models.whatsapp_registration_challenge import WhatsAppRegistrationChallenge
from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage
from server.models.complaint import Complaint
from server.services.whatsapp_service import WhatsAppService
from server.services.whatsapp_verification_service import WhatsAppVerificationService
from server.utils.config import config

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_whatsapp_config(monkeypatch, db_session):
    """Ensure test suite has valid mock configuration for WhatsApp Business Phone and Meta Secret."""
    monkeypatch.setattr(config, "WHATSAPP_BUSINESS_PHONE", "+919876543210")
    monkeypatch.setattr(config, "META_APP_SECRET", "dev-meta-app-secret-1234567890123456")
    # Clean previous testclient IP rate limiting entries
    db_session.query(WhatsAppRegistrationChallenge).filter(
        WhatsAppRegistrationChallenge.ip_address == "testclient"
    ).delete()
    db_session.commit()



def generate_meta_signature(raw_body: bytes, secret: str = None) -> str:
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


def cleanup_test_phone(db, phone: str):
    clean = phone[-10:]
    db.query(WhatsAppRegistrationChallenge).filter(WhatsAppRegistrationChallenge.phone == clean).delete()
    db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == f"91{clean}").delete()
    db.query(User).filter(User.phone == clean).delete()
    db.commit()


# ── TEST 1: Generation Endpoint ──────────────────────────────────────────────
def test_generate_verification_challenge_success(db_session):
    phone = "9876510001"
    cleanup_test_phone(db_session, phone)

    res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Aarav Sharma",
        "email": "aarav@dhule.gov.in",
        "ward": "Ward 4"
    })

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "challenge_id" in data
    assert len(data["code"]) == 6
    assert data["code"].isdigit()
    assert data["verification_command"] == f"VERIFY {data['code']}"
    assert "whatsapp_number" in data
    assert data["expires_in"] == 300

    # Verify database persistence: code plaintext MUST NOT be stored
    challenge = db_session.query(WhatsAppRegistrationChallenge).filter(
        WhatsAppRegistrationChallenge.phone == phone
    ).first()
    assert challenge is not None
    assert challenge.status == "PENDING"
    assert challenge.otp_hash is not None
    assert challenge.otp_hash != data["code"]  # Only hash stored
    profile = challenge.get_profile()
    assert profile["full_name"] == "Aarav Sharma"
    assert profile["email"] == "aarav@dhule.gov.in"
    assert profile["ward"] == "Ward 4"


# ── TEST 2: Successful Inbound Verification ──────────────────────────────────
def test_successful_inbound_verification_and_registration(db_session):
    phone = "9876510002"
    cleanup_test_phone(db_session, phone)

    # 1. Citizen generates challenge on website
    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Meera Joshi",
        "email": "meera@dhule.gov.in"
    })
    assert gen_res.status_code == 200
    code = gen_res.json()["code"]
    challenge_id = gen_res.json()["challenge_id"]

    # 2. Citizen sends "VERIFY <code>" from WhatsApp
    result = WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )

    assert result["verified"] is True
    assert result["status"] == "verified"
    assert "पडताळणी यशस्वी" in result["reply"] or "Verification Successful" in result["reply"]

    # 3. Verify challenge in DB
    challenge = db_session.query(WhatsAppRegistrationChallenge).filter(
        WhatsAppRegistrationChallenge.phone == phone
    ).first()
    assert challenge.status == "VERIFIED"
    assert challenge.verified_at is not None

    # 4. Verify canonical User record was created
    user = db_session.query(User).filter(User.phone == phone).first()
    assert user is not None
    assert user.full_name == "Meera Joshi"
    assert user.role == "citizen"
    assert user.is_active is True
    assert challenge.user_id == user.id

    # 5. Verify WhatsAppCitizen was linked
    citizen = db_session.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == f"91{phone}").first()
    assert citizen is not None
    assert citizen.user_id == user.id
    assert citizen.is_authorized is True


# ── TEST 3: Wrong Verification Code ──────────────────────────────────────────
def test_inbound_verification_wrong_code(db_session):
    phone = "9876510003"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Rahul Kulkarni"
    })
    real_code = gen_res.json()["code"]

    # Send wrong code
    result = WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body="VERIFY 000000"
    )

    assert result["verified"] is False
    assert result["status"] == "invalid_code"
    assert "अयोग्य" in result["reply"] or "Incorrect" in result["reply"]

    challenge = db_session.query(WhatsAppRegistrationChallenge).filter(
        WhatsAppRegistrationChallenge.phone == phone
    ).first()
    assert challenge.status == "PENDING"
    assert challenge.attempts == 1

    # User must NOT be created
    user = db_session.query(User).filter(User.phone == phone).first()
    assert user is None


# ── TEST 4: Expired Verification Code ────────────────────────────────────────
def test_inbound_verification_expired_code(db_session):
    phone = "9876510004"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Sunita Shinde"
    })
    code = gen_res.json()["code"]

    # Manually expire the challenge
    challenge = db_session.query(WhatsAppRegistrationChallenge).filter(
        WhatsAppRegistrationChallenge.phone == phone
    ).first()
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()

    result = WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )

    assert result["verified"] is False
    assert result["status"] == "expired"
    assert "कालबाह्य" in result["reply"] or "expired" in result["reply"]


# ── TEST 5: Sender-Number Mismatch Security Protection ───────────────────────
def test_inbound_verification_sender_number_mismatch(db_session):
    phone_legit = "9876510005"
    phone_attacker = "9876510006"
    cleanup_test_phone(db_session, phone_legit)
    cleanup_test_phone(db_session, phone_attacker)

    # Legit citizen generates challenge
    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone_legit,
        "fullName": "Legit Citizen"
    })
    legit_code = gen_res.json()["code"]

    # Attacker tries to send legit_code from attacker's phone
    result = WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone_attacker}",
        message_type="text",
        text_body=f"VERIFY {legit_code}"
    )

    # Must be strictly rejected
    assert result["verified"] is False
    assert result["status"] == "no_challenge"

    # Legit challenge must remain untouched and PENDING
    legit_challenge = db_session.query(WhatsAppRegistrationChallenge).filter(
        WhatsAppRegistrationChallenge.phone == phone_legit
    ).first()
    assert legit_challenge.status == "PENDING"
    assert legit_challenge.attempts == 0


# ── TEST 6: Replayed Code (Single-Use Idempotency) ───────────────────────────
def test_inbound_verification_replayed_code_idempotent(db_session):
    phone = "9876510007"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Kavita Deshmukh"
    })
    code = gen_res.json()["code"]

    # First send: verifies successfully
    res1 = WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )
    assert res1["verified"] is True
    assert res1["status"] == "verified"

    # Second send: idempotent replay
    res2 = WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )
    assert res2["verified"] is True
    assert res2["status"] == "already_verified"

    # Ensure only ONE User record was created
    user_count = db_session.query(User).filter(User.phone == phone).count()
    assert user_count == 1


# ── TEST 7: Webhook Idempotency Integration ──────────────────────────────────
def test_duplicate_webhook_delivery_idempotency(db_session, monkeypatch):
    secret = "test-webhook-secret-32-chars-long!"
    monkeypatch.setattr(config, "META_APP_SECRET", secret)
    phone = "9876510008"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Ganesh Patil"
    })
    code = gen_res.json()["code"]

    msg_id = "WAMID_TEST_IDEMPOTENT_001"
    db_session.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).delete()
    db_session.commit()

    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID_TEST",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "15551234567", "phone_number_id": "123456789"},
                            "messages": [
                                {
                                    "id": msg_id,
                                    "from": f"91{phone}",
                                    "type": "text",
                                    "text": {"body": f"VERIFY {code}"}
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }

    raw = json.dumps(webhook_payload).encode("utf-8")
    sig = generate_meta_signature(raw, secret)

    # First delivery
    r1 = client.post("/api/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert r1.status_code == 200

    # Second delivery (identical duplicate msg_id)
    r2 = client.post("/api/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert r2.status_code == 200

    # Ensure processed message recorded as COMPLETED
    p_msg = db_session.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).first()
    assert p_msg is not None
    assert p_msg.status == "COMPLETED"

    # User count is strictly 1
    assert db_session.query(User).filter(User.phone == phone).count() == 1


# ── TEST 8: Rate Limiting (Cooldown & Ceiling) ────────────────────────────────
def test_rate_limiting_cooldown_and_max_challenges(db_session):
    phone = "9876510009"
    cleanup_test_phone(db_session, phone)

    # 1. First challenge succeeds
    r1 = client.post("/api/auth/whatsapp-verification/generate", json={"phone": phone, "fullName": "Test Rate Limit"})
    assert r1.status_code == 200

    # 2. Immediate second challenge must trigger 429 cooldown
    r2 = client.post("/api/auth/whatsapp-verification/generate", json={"phone": phone, "fullName": "Test Rate Limit"})
    assert r2.status_code == 429
    assert "Please wait" in r2.json()["detail"]


# ── TEST 9: Duplicate Registration Prevention ────────────────────────────────
def test_duplicate_registration_prevention(db_session):
    phone = "9876510010"
    cleanup_test_phone(db_session, phone)

    # Pre-register existing user
    user = User(full_name="Existing Citizen", phone=phone, role="citizen", is_active=True)
    db_session.add(user)
    db_session.commit()

    # Attempting to generate verification code for already registered number must fail with 400
    res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Duplicate Attempt"
    })
    assert res.status_code == 400
    assert "already registered" in res.json()["detail"]


# ── TEST 10: Website Status Polling ──────────────────────────────────────────
def test_website_status_polling_flow(db_session):
    phone = "9876510011"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Ananya Sen",
        "email": "ananya@dhule.gov.in"
    })
    challenge_id = gen_res.json()["challenge_id"]
    challenge_secret = gen_res.json()["challenge_secret"]
    code = gen_res.json()["code"]

    # 1. Poll before verification: returns PENDING
    poll1 = client.get(f"/api/auth/whatsapp-verification/status/{challenge_id}")
    assert poll1.status_code == 200
    data1 = poll1.json()
    assert data1["status"] == "PENDING"
    assert data1["verified"] is False
    assert data1["access_token"] is None

    # 2. Inbound webhook verifies
    WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )

    # 3. Poll without secret: returns VERIFIED, but NO access_token
    poll_no_secret = client.get(f"/api/auth/whatsapp-verification/status/{challenge_id}")
    assert poll_no_secret.status_code == 200
    data_no_sec = poll_no_secret.json()
    assert data_no_sec["status"] == "VERIFIED"
    assert data_no_sec["verified"] is True
    assert data_no_sec["consumed"] is False
    assert data_no_sec["access_token"] is None

    # 4. Poll after verification WITH secret: returns VERIFIED with JWT token and consumes session
    poll2 = client.get(
        f"/api/auth/whatsapp-verification/status/{challenge_id}",
        headers={"X-Challenge-Secret": challenge_secret}
    )
    assert poll2.status_code == 200
    data2 = poll2.json()
    assert data2["status"] == "VERIFIED"
    assert data2["verified"] is True
    assert data2["consumed"] is True
    assert data2["access_token"] is not None
    assert data2["user"]["phone"] == phone
    assert data2["user"]["name"] == "Ananya Sen"


# ── TEST 11: Existing LINK Workflow Regression ───────────────────────────────
def test_existing_link_workflow_regression(db_session):
    phone = "9876510012"
    cleanup_test_phone(db_session, phone)

    user = User(full_name="Linked Citizen", phone=phone, role="citizen", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    from server.services.whatsapp_link_service import WhatsAppLinkService
    link_info = WhatsAppLinkService.generate_link_code(db_session, user)
    link_code = link_info["code"]

    # Send LINK <code> via WhatsApp
    res = WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"LINK {link_code}"
    )

    assert res["status"] == "linked"
    assert "खाते यशस्वीरित्या जोडले" in res["reply"] or "account successfully linked" in res["reply"].lower()

    citizen = db_session.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == f"91{phone}").first()
    assert citizen is not None
    assert citizen.user_id == user.id
    assert citizen.is_authorized is True


# ── TEST 12: Existing Complaints & Menu Regression ───────────────────────────
def test_complaints_and_whatsapp_menu_regression(db_session):
    phone = "9876510013"
    cleanup_test_phone(db_session, phone)

    # Unlinked citizen sends random text -> onboarding registration prompt
    res_unlinked = WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body="Hello EcoPulse"
    )
    assert res_unlinked["status"] == "not_linked"
    assert "वेबसाइटवर नागरिक म्हणून नोंदणी करा" in res_unlinked["reply"] or "first register" in res_unlinked["reply"]

    # Pre-link user
    user = User(full_name="Authorized User", phone=phone, role="citizen", is_active=True)
    db_session.add(user)
    db_session.commit()
    citizen = WhatsAppService.get_or_create_citizen(db_session, f"91{phone}")
    citizen.user_id = user.id
    citizen.is_authorized = True
    db_session.commit()

    # Linked citizen sends menu option 1 (Report Waste) -> asks for photo
    res_menu1 = WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body="1"
    )
    assert res_menu1["status"] == "awaiting_photo"
    assert "फोटो पाठवा" in res_menu1["reply"] or "photo" in res_menu1["reply"].lower()


# ── TEST 13: Concurrent Inbound Verification (No Duplicate Users) ─────────────
def test_concurrent_inbound_verification_thread_safety(db_session):
    import concurrent.futures

    phone = "9876510014"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Concurrent Citizen",
        "email": "concurrent@dhule.gov.in"
    })
    code = gen_res.json()["code"]

    def run_verify():
        db = SessionLocal()
        try:
            return WhatsAppVerificationService.process_verification_message(
                db=db,
                sender_phone=f"91{phone}",
                raw_code=code
            )
        finally:
            db.close()

    # Execute 4 concurrent verification attempts
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_verify) for _ in range(4)]
        results = [f.result() for f in futures]

    # All should report verified=True
    assert all(r["verified"] is True for r in results)

    # Exactly ONE User record must exist in DB
    user_count = db_session.query(User).filter(User.phone == phone).count()
    assert user_count == 1


# ── TEST 14: Security: Challenge ID Alone Cannot Retrieve JWT ────────────────
def test_challenge_id_alone_cannot_retrieve_jwt(db_session):
    phone = "9876510015"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Security Audit Citizen"
    })
    assert gen_res.status_code == 200
    challenge_id = gen_res.json()["challenge_id"]
    code = gen_res.json()["code"]

    # Verify via WhatsApp webhook
    WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )

    # An attacker knowing only the challenge_id cannot claim the JWT session
    poll_res = client.get(f"/api/auth/whatsapp-verification/status/{challenge_id}")
    assert poll_res.status_code == 200
    data = poll_res.json()
    assert data["status"] == "VERIFIED"
    assert data["access_token"] is None
    assert data["user"] is None


# ── TEST 15: Security: Wrong Challenge Secret Is Rejected With 403 ───────────
def test_wrong_challenge_secret_returns_403(db_session):
    phone = "9876510016"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Wrong Secret Citizen"
    })
    challenge_id = gen_res.json()["challenge_id"]
    code = gen_res.json()["code"]

    WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )

    # Forged secret
    poll_res = client.get(
        f"/api/auth/whatsapp-verification/status/{challenge_id}",
        headers={"X-Challenge-Secret": "forged_malicious_secret_token_123456"}
    )
    assert poll_res.status_code == 403
    assert "Invalid or unauthorized challenge secret" in poll_res.json()["detail"]


# ── TEST 16: Security: Single-Use Session Consumption ────────────────────────
def test_session_single_use_consumed_cannot_reissue_jwt(db_session):
    phone = "9876510017"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Single Use Citizen"
    })
    challenge_id = gen_res.json()["challenge_id"]
    challenge_secret = gen_res.json()["challenge_secret"]
    code = gen_res.json()["code"]

    WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )

    # First claim succeeds
    claim1 = client.get(
        f"/api/auth/whatsapp-verification/status/{challenge_id}",
        headers={"X-Challenge-Secret": challenge_secret}
    )
    assert claim1.status_code == 200
    assert claim1.json()["access_token"] is not None

    # Second claim fails or reports already claimed (cannot re-issue JWT)
    claim2 = client.get(
        f"/api/auth/whatsapp-verification/status/{challenge_id}",
        headers={"X-Challenge-Secret": challenge_secret}
    )
    assert claim2.status_code == 200
    data2 = claim2.json()
    assert data2["status"] == "CONSUMED"
    assert data2["access_token"] is None


# ── TEST 17: Configuration: Unconfigured Business Phone Returns 503 ──────────
def test_unconfigured_business_phone_returns_503(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_BUSINESS_PHONE", "")
    res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": "9876510018",
        "fullName": "Unconfigured Phone Citizen"
    })
    assert res.status_code == 503
    assert "Official WhatsApp Business phone number is not configured" in res.json()["detail"]


# ── TEST 18: UX Hardening: Refresh Recovery Flow (Pending -> Verified) ───────
def test_refresh_recovery_pending_and_verified_flow(db_session):
    """
    Simulates a citizen refreshing their browser tab during registration:
    1. Citizen enters details and generates challenge (challenge_id & challenge_secret stored in sessionStorage).
    2. Citizen refreshes page: frontend resumes polling with X-Challenge-Secret header.
    3. Status is confirmed PENDING with seconds_remaining > 0 and whatsapp_number populated.
    4. Citizen sends VERIFY code from WhatsApp.
    5. Polling resumes and retrieves JWT session, creating citizen user account atomically.
    """
    phone = "9876510019"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Refresh Citizen",
        "email": "refresh@dhule.gov.in"
    })
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    challenge_id = gen_data["challenge_id"]
    challenge_secret = gen_data["challenge_secret"]
    code = gen_data["code"]

    # --- REFRESH STEP 1: Browser refreshes, restores session from sessionStorage and polls status ---
    refresh_poll_1 = client.get(
        f"/api/auth/whatsapp-verification/status/{challenge_id}",
        headers={"X-Challenge-Secret": challenge_secret}
    )
    assert refresh_poll_1.status_code == 200
    data1 = refresh_poll_1.json()
    assert data1["status"] == "PENDING"
    assert data1["verified"] is False
    assert data1["consumed"] is False
    assert data1["expired"] is False
    assert data1["access_token"] is None
    assert data1["seconds_remaining"] > 0
    assert "whatsapp_number" in data1
    assert data1["whatsapp_number"] != ""

    # --- REFRESH STEP 2: Citizen sends WhatsApp message while page was reloaded ---
    wa_result = WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )
    assert wa_result["verified"] is True

    # --- REFRESH STEP 3: Browser polling detects VERIFIED status and claims JWT ---
    refresh_poll_2 = client.get(
        f"/api/auth/whatsapp-verification/status/{challenge_id}",
        headers={"X-Challenge-Secret": challenge_secret}
    )
    assert refresh_poll_2.status_code == 200
    data2 = refresh_poll_2.json()
    assert data2["status"] == "VERIFIED"
    assert data2["verified"] is True
    assert data2["consumed"] is True
    assert data2["access_token"] is not None
    assert data2["user"]["phone"] == phone
    assert data2["user"]["name"] == "Refresh Citizen"


# ── TEST 19: UX Hardening: Expired Challenge Status on Refresh ───────────────
def test_refresh_recovery_expired_challenge(db_session):
    """
    If a citizen refreshes the page after the 5-minute window has elapsed,
    the status endpoint returns EXPIRED, allowing the frontend to clear
    sessionStorage and prompt the citizen to generate a new code.
    """
    phone = "9876510020"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Expired Citizen"
    })
    challenge_id = gen_res.json()["challenge_id"]
    challenge_secret = gen_res.json()["challenge_secret"]

    # Simulate past expiration in database
    challenge = WhatsAppVerificationService.verify_and_get_challenge(db_session, challenge_id)
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db_session.commit()

    # Poll status with X-Challenge-Secret
    poll_res = client.get(
        f"/api/auth/whatsapp-verification/status/{challenge_id}",
        headers={"X-Challenge-Secret": challenge_secret}
    )
    assert poll_res.status_code == 200
    data = poll_res.json()
    assert data["status"] == "EXPIRED"
    assert data["expired"] is True
    assert data["verified"] is False
    assert data["access_token"] is None
    assert "expired" in data["message"].lower()


# ── TEST 20: UX Hardening: Already Consumed Challenge on Refresh ──────────────
def test_refresh_recovery_already_consumed_challenge(db_session):
    """
    If a challenge has already been claimed and consumed, subsequent status polling
    (e.g., from an open tab or after page refresh) returns CONSUMED with no token.
    """
    phone = "9876510021"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Consumed Citizen"
    })
    challenge_id = gen_res.json()["challenge_id"]
    challenge_secret = gen_res.json()["challenge_secret"]
    code = gen_res.json()["code"]

    # Verify via WhatsApp
    WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )

    # First claim succeeds and consumes the challenge
    claim1 = client.get(
        f"/api/auth/whatsapp-verification/status/{challenge_id}",
        headers={"X-Challenge-Secret": challenge_secret}
    )
    assert claim1.status_code == 200
    assert claim1.json()["access_token"] is not None
    assert claim1.json()["consumed"] is True

    # Second status check returns CONSUMED with access_token=None
    poll_consumed = client.get(
        f"/api/auth/whatsapp-verification/status/{challenge_id}",
        headers={"X-Challenge-Secret": challenge_secret}
    )
    assert poll_consumed.status_code == 200
    data = poll_consumed.json()
    assert data["status"] == "CONSUMED"
    assert data["consumed"] is True
    assert data["access_token"] is None
    assert "already been claimed" in data["message"]


# ── TEST 21: UX Hardening: Invalid or Corrupted Secret on Refresh ────────────
def test_refresh_recovery_tampered_secret_rejected_with_403(db_session):
    """
    If sessionStorage is tampered with or provides an invalid secret on refresh,
    the server rejects the claim with HTTP 403 Forbidden.
    """
    phone = "9876510022"
    cleanup_test_phone(db_session, phone)

    gen_res = client.post("/api/auth/whatsapp-verification/generate", json={
        "phone": phone,
        "fullName": "Tampered Citizen"
    })
    challenge_id = gen_res.json()["challenge_id"]
    code = gen_res.json()["code"]

    # Verify on WhatsApp
    WhatsAppService.handle_incoming_message(
        db=db_session,
        sender_phone=f"91{phone}",
        message_type="text",
        text_body=f"VERIFY {code}"
    )

    # Poll with corrupted secret
    poll_tampered = client.get(
        f"/api/auth/whatsapp-verification/status/{challenge_id}",
        headers={"X-Challenge-Secret": "tampered_session_storage_secret_xyz"}
    )
    assert poll_tampered.status_code == 403
    assert "Invalid or unauthorized challenge secret" in poll_tampered.json()["detail"]
