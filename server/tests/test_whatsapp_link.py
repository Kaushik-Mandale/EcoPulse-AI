import random
import uuid
import hashlib
import json
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from server.main import app
from server.database.db import SessionLocal
from server.models.user import User
from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage
from server.models.whatsapp_link_token import WhatsAppLinkToken
from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.services.whatsapp_service import WhatsAppService
from server.services.whatsapp_link_service import WhatsAppLinkService
from server.utils.security import hash_password, create_access_token

client = TestClient(app)


def _create_test_user(db, email, role="citizen", phone="+919876543210"):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            hashed_password=hash_password("Password123!"),
            full_name=f"Test {role.capitalize()}",
            role=role,
            phone=phone,
            is_active=True,
            is_locked=False,
            eco_coins=100
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _auth_header(user):
    token = create_access_token(data={"sub": user.email, "id": user.id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}


class TestWhatsAppLinkTokenGeneration:
    """Tests for POST /api/whatsapp/link/generate"""

    def test_authenticated_citizen_generates_code(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"citizen_gen_1_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919811111111")
            headers = _auth_header(user)

            res = client.post("/api/whatsapp/link/generate", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert "code" in data
            assert len(data["code"]) >= 20
            assert data["expires_in"] == 600
            assert "bot_phone" in data

            # Verify token is stored as SHA-256 hash in DB, NOT plaintext
            token_record = db.query(WhatsAppLinkToken).filter(
                WhatsAppLinkToken.user_id == user.id,
                WhatsAppLinkToken.consumed_at.is_(None)
            ).order_by(WhatsAppLinkToken.id.desc()).first()
            assert token_record is not None
            expected_hash = hashlib.sha256(data["code"].encode("utf-8")).hexdigest()
            assert token_record.token_hash == expected_hash
            assert data["code"] not in token_record.token_hash
        finally:
            db.close()

    def test_unauthenticated_request_rejected(self):
        res = client.post("/api/whatsapp/link/generate")
        assert res.status_code == 401

    def test_non_citizen_rejected(self):
        db = SessionLocal()
        try:
            driver = _create_test_user(db, f"driver_gen_1_{uuid.uuid4().hex[:6]}@test.com", "driver", "+919822222222")
            headers = _auth_header(driver)

            res = client.post("/api/whatsapp/link/generate", headers=headers)
            assert res.status_code == 403
            assert "citizen" in res.json()["detail"].lower()
        finally:
            db.close()

    def test_generate_invalidates_previous_token(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"citizen_gen_inv_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919833333333")
            headers = _auth_header(user)

            res1 = client.post("/api/whatsapp/link/generate", headers=headers)
            assert res1.status_code == 200
            code1 = res1.json()["code"]

            res2 = client.post("/api/whatsapp/link/generate", headers=headers)
            assert res2.status_code == 200
            code2 = res2.json()["code"]
            assert code1 != code2

            # Attempting to redeem code1 should fail because it was invalidated
            redeem_res = WhatsAppLinkService.redeem_link_code(db, code1, "919999000001")
            assert redeem_res is None
        finally:
            db.close()

    def test_rate_limiting(self):
        db = SessionLocal()
        try:
            import uuid
            user = _create_test_user(db, f"citizen_rate_limit_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919844444444")
            headers = _auth_header(user)

            # Consume the 5 allowed tokens in window
            for i in range(5):
                res = client.post("/api/whatsapp/link/generate", headers=headers)
                assert res.status_code == 200

            # 6th request should hit rate limit (HTTP 429)
            res_limit = client.post("/api/whatsapp/link/generate", headers=headers)
            assert res_limit.status_code == 429
            assert "too many" in res_limit.json()["detail"].lower()
        finally:
            db.close()


class TestWhatsAppLinkRedemption:
    """Tests for redeeming link code via WhatsApp message LINK <code>"""

    def test_successful_linking_flexible_number(self):
        db = SessionLocal()
        try:
            # Website user registered with +919111111111
            user = _create_test_user(db, f"citizen_flex_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919111111111")
            headers = _auth_header(user)

            gen_res = client.post("/api/whatsapp/link/generate", headers=headers)
            assert gen_res.status_code == 200
            code = gen_res.json()["code"]

            # Citizen sends code from a DIFFERENT WhatsApp number: +919999888877
            wa_sender = f"91{random.randint(1000000000, 9999999999)}"
            sim_res = client.post(
                "/api/whatsapp/simulate-incoming",
                json={"phone": wa_sender, "message": f"LINK {code}", "type": "text"}
            )
            assert sim_res.status_code == 200
            data = sim_res.json()
            assert data["status"] == "linked"
            assert "यशस्वीरित्या जोडले" in data["reply"] or "Linked" in data["reply"] or "धुळे" in data["reply"]

            # Verify in DB that WhatsAppCitizen now has user_id set and is_authorized is True
            citizen = db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == wa_sender).first()
            assert citizen is not None
            assert citizen.user_id == user.id
            assert citizen.is_authorized is True

            # Verify status endpoint reflects linked state
            status_res = client.get("/api/whatsapp/link/status", headers=headers)
            assert status_res.status_code == 200
            status_data = status_res.json()
            assert status_data["is_linked"] is True
            assert "****" in status_data["whatsapp_phone_masked"]
        finally:
            db.close()

    def test_wrong_code_rejected(self):
        db = SessionLocal()
        try:
            sim_res = client.post(
                "/api/whatsapp/simulate-incoming",
                json={"phone": "918888777766", "message": "LINK invalidCode1234567890123", "type": "text"}
            )
            assert sim_res.status_code == 200
            assert sim_res.json()["status"] == "link_failed"
        finally:
            db.close()

    def test_expired_token_rejected(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"citizen_expired_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919855555555")
            headers = _auth_header(user)

            gen_res = client.post("/api/whatsapp/link/generate", headers=headers)
            code = gen_res.json()["code"]

            # Manually expire the token in DB
            code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
            token = db.query(WhatsAppLinkToken).filter(WhatsAppLinkToken.token_hash == code_hash).first()
            token.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()

            # Attempt redemption
            redeem_result = WhatsAppLinkService.redeem_link_code(db, code, f"91{random.randint(1000000000, 9999999999)}")
            assert redeem_result is None
        finally:
            db.close()

    def test_reused_code_rejected(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"citizen_reused_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919866666666")
            headers = _auth_header(user)

            gen_res = client.post("/api/whatsapp/link/generate", headers=headers)
            code = gen_res.json()["code"]

            # First redemption succeeds
            res1 = WhatsAppLinkService.redeem_link_code(db, code, f"91{random.randint(1000000000, 9999999999)}")
            assert res1 is not None

            # Second redemption of same code must fail
            res2 = WhatsAppLinkService.redeem_link_code(db, code, f"91{random.randint(1000000000, 9999999999)}")
            assert res2 is None
        finally:
            db.close()

    def test_phone_already_linked_to_different_user_rejected(self):
        db = SessionLocal()
        try:
            user1 = _create_test_user(db, f"citizen_u1_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919877777771")
            user2 = _create_test_user(db, f"citizen_u2_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919877777772")

            shared_wa_phone = f"91{random.randint(1000000000, 9999999999)}"
            # Link user1 to WhatsApp phone
            h1 = _auth_header(user1)
            code1 = client.post("/api/whatsapp/link/generate", headers=h1).json()["code"]
            res1 = WhatsAppLinkService.redeem_link_code(db, code1, shared_wa_phone)
            assert res1 is not None

            # User2 tries to link to same WhatsApp phone 915555444433
            h2 = _auth_header(user2)
            code2 = client.post("/api/whatsapp/link/generate", headers=h2).json()["code"]
            res2 = WhatsAppLinkService.redeem_link_code(db, code2, shared_wa_phone)
            assert res2 is None
        finally:
            db.close()


class TestWhatsAppLinkUnlink:
    """Tests for DELETE /api/whatsapp/link/unlink"""

    def test_unlink_flow(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"citizen_unlink_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919888888888")
            headers = _auth_header(user)

            # Generate and link
            code = client.post("/api/whatsapp/link/generate", headers=headers).json()["code"]
            wa_phone = f"91{random.randint(1000000000, 9999999999)}"
            WhatsAppLinkService.redeem_link_code(db, code, wa_phone)

            # Verify linked
            status1 = client.get("/api/whatsapp/link/status", headers=headers).json()
            assert status1["is_linked"] is True

            # Unlink
            del_res = client.delete("/api/whatsapp/link/unlink", headers=headers)
            assert del_res.status_code == 200
            del_data = del_res.json()
            assert del_data["success"] is True

            # Verify unlinked
            status2 = client.get("/api/whatsapp/link/status", headers=headers).json()
            assert status2["is_linked"] is False

            # Verify in DB: citizen has user_id = None and is_authorized = False
            citizen = db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == wa_phone).first()
            assert citizen.user_id is None
            assert citizen.is_authorized is False
        finally:
            db.close()


class TestComplaintAssociationWithLinkedUser:
    """Tests ensuring complaints logged via WhatsApp associate with the linked web User"""

    def test_complaint_associates_with_linked_citizen_user_id(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"citizen_complaint_link_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919899999999")
            headers = _auth_header(user)

            # Link account
            code = client.post("/api/whatsapp/link/generate", headers=headers).json()["code"]
            wa_phone = f"91{random.randint(1000000000, 9999999999)}"
            WhatsAppLinkService.redeem_link_code(db, code, wa_phone)

            # Send photo
            res_photo = client.post(
                "/api/whatsapp/simulate-incoming",
                json={
                    "phone": wa_phone,
                    "message": "",
                    "type": "image",
                    "media_url": "https://example.com/waste_dump.jpg"
                }
            )
            assert res_photo.status_code == 200
            assert res_photo.json()["status"] == "awaiting_location"

            # Send location
            res_loc = client.post(
                "/api/whatsapp/simulate-incoming",
                json={
                    "phone": wa_phone,
                    "message": "",
                    "type": "location",
                    "latitude": 20.9042,
                    "longitude": 74.7749
                }
            )
            assert res_loc.status_code == 200
            loc_data = res_loc.json()
            assert loc_data["status"] == "complaint_created"
            assert "DHL-2026-" in loc_data["ticket"]

            # Query the complaint in DB: citizen_id must match linked User.id!
            complaint = db.query(Complaint).filter(Complaint.tracking_number == loc_data["ticket"]).first()
            assert complaint is not None
            assert complaint.citizen_id == user.id
            assert "Dhule" in complaint.location_address
        finally:
            db.close()

import hmac
import json
import random
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from server.utils.config import config
from server.services.whatsapp_service import WhatsAppService, _build_texts
from server.services.whatsapp_link_service import WhatsAppLinkService
from server.models.whatsapp_link_token import WhatsAppLinkToken
from server.models.complaint import Complaint


def _calc_sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class TestWhatsAppWebhookRegression:
    """Regression tests for incoming webhook messages, Dhule branding, and linking."""

    def test_unlinked_sender_sends_hey(self):
        wa_phone = f"91{random.randint(1000000000, 9999999999)}"
        res = client.post(
            "/api/whatsapp/simulate-incoming",
            json={"phone": wa_phone, "message": "hey", "type": "text"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "not_linked"
        assert "धुळे महानगरपालिका स्वच्छता व्यवस्थापन" in data["reply"]
        assert "https://ecopulse-ai-frontend.onrender.com/" in data["reply"]
        assert "LINK <code>" in data["reply"]
        assert "Shirpur" not in data["reply"]
        assert "SHP" not in data["reply"]

    def test_unlinked_sender_sends_arbitrary_text(self):
        wa_phone = f"91{random.randint(1000000000, 9999999999)}"
        res = client.post(
            "/api/whatsapp/simulate-incoming",
            json={"phone": wa_phone, "message": "When will the garbage truck arrive in my area?", "type": "text"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "not_linked"
        assert "धुळे महानगरपालिका स्वच्छता व्यवस्थापन" in data["reply"]
        assert "https://ecopulse-ai-frontend.onrender.com/" in data["reply"]
        assert "Shirpur" not in data["reply"]
        assert "SHP" not in data["reply"]

    def test_linked_citizen_sends_hey(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"linked_hey_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919800000001")
            code = client.post("/api/whatsapp/link/generate", headers=_auth_header(user)).json()["code"]
            wa_phone = f"91{random.randint(1000000000, 9999999999)}"
            WhatsAppLinkService.redeem_link_code(db, code, wa_phone)

            res = client.post(
                "/api/whatsapp/simulate-incoming",
                json={"phone": wa_phone, "message": "hey", "type": "text"}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "menu_presented"
            assert "धुळे महानगरपालिका स्वच्छता व्यवस्थापन" in data["reply"]
            # 9-option menu present
            assert "1️⃣" in data["reply"]
            assert "9️⃣" in data["reply"]
            assert "Shirpur" not in data["reply"]
            assert "SHP" not in data["reply"]
        finally:
            db.close()

    def test_linked_citizen_sends_hello(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"linked_hello_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919800000002")
            code = client.post("/api/whatsapp/link/generate", headers=_auth_header(user)).json()["code"]
            wa_phone = f"91{random.randint(1000000000, 9999999999)}"
            WhatsAppLinkService.redeem_link_code(db, code, wa_phone)

            res = client.post(
                "/api/whatsapp/simulate-incoming",
                json={"phone": wa_phone, "message": "hello", "type": "text"}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "menu_presented"
            assert "1️⃣" in data["reply"]
            assert "9️⃣" in data["reply"]
            assert "Shirpur" not in data["reply"]
            assert "SHP" not in data["reply"]
        finally:
            db.close()

    def test_citizen_sends_link_with_valid_code(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"valid_link_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919800000003")
            code = client.post("/api/whatsapp/link/generate", headers=_auth_header(user)).json()["code"]
            wa_phone = f"91{random.randint(1000000000, 9999999999)}"

            res = client.post(
                "/api/whatsapp/simulate-incoming",
                json={"phone": wa_phone, "message": f"LINK {code}", "type": "text"}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "linked"
            assert "यशस्वीरित्या जोडले" in data["reply"]
            assert "1️⃣" in data["reply"]
            assert "9️⃣" in data["reply"]
            assert "Shirpur" not in data["reply"]
            assert "SHP" not in data["reply"]
        finally:
            db.close()

    def test_citizen_sends_link_with_invalid_code(self):
        wa_phone = f"91{random.randint(1000000000, 9999999999)}"
        res = client.post(
            "/api/whatsapp/simulate-incoming",
            json={"phone": wa_phone, "message": "LINK invalid_token_xyz_12345678", "type": "text"}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "link_failed"
        assert "कालबाह्य" in res.json()["reply"] or "Invalid" in res.json()["reply"]
        assert "https://ecopulse-ai-frontend.onrender.com/" in res.json()["reply"]

    def test_citizen_sends_link_with_expired_code(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"expired_link_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919800000004")
            code = client.post("/api/whatsapp/link/generate", headers=_auth_header(user)).json()["code"]
            # Force expiration
            token_record = db.query(WhatsAppLinkToken).filter(WhatsAppLinkToken.user_id == user.id).first()
            token_record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()

            wa_phone = f"91{random.randint(1000000000, 9999999999)}"
            res = client.post(
                "/api/whatsapp/simulate-incoming",
                json={"phone": wa_phone, "message": f"LINK {code}", "type": "text"}
            )
            assert res.status_code == 200
            assert res.json()["status"] == "link_failed"
        finally:
            db.close()

    def test_citizen_sends_link_with_reused_code(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"reused_link_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919800000005")
            code = client.post("/api/whatsapp/link/generate", headers=_auth_header(user)).json()["code"]
            wa_phone_1 = f"91{random.randint(1000000000, 9999999999)}"

            # First redemption succeeds
            res1 = client.post(
                "/api/whatsapp/simulate-incoming",
                json={"phone": wa_phone_1, "message": f"LINK {code}", "type": "text"}
            )
            assert res1.status_code == 200
            assert res1.json()["status"] == "linked"

            # Second attempt to reuse the same code fails
            wa_phone_2 = f"91{random.randint(1000000000, 9999999999)}"
            res2 = client.post(
                "/api/whatsapp/simulate-incoming",
                json={"phone": wa_phone_2, "message": f"LINK {code}", "type": "text"}
            )
            assert res2.status_code == 200
            assert res2.json()["status"] == "link_failed"
        finally:
            db.close()

    def test_linked_user_sends_waste_photo_and_creates_associated_complaint(self):
        db = SessionLocal()
        try:
            user = _create_test_user(db, f"photo_user_{uuid.uuid4().hex[:6]}@test.com", "citizen", "+919800000006")
            code = client.post("/api/whatsapp/link/generate", headers=_auth_header(user)).json()["code"]
            wa_phone = f"91{random.randint(1000000000, 9999999999)}"
            WhatsAppLinkService.redeem_link_code(db, code, wa_phone)

            # Send photo
            res_photo = client.post(
                "/api/whatsapp/simulate-incoming",
                json={"phone": wa_phone, "message": "", "type": "image", "media_url": "https://example.com/waste_dhule.jpg"}
            )
            assert res_photo.status_code == 200
            assert res_photo.json()["status"] == "awaiting_location"

            # Send GPS location
            res_loc = client.post(
                "/api/whatsapp/simulate-incoming",
                json={"phone": wa_phone, "message": "", "type": "location", "latitude": 20.9042, "longitude": 74.7749}
            )
            assert res_loc.status_code == 200
            data = res_loc.json()
            assert data["status"] == "complaint_created"
            assert data["ticket"].startswith("DHL-")

            # Verify database record belongs to the linked website user
            complaint = db.query(Complaint).filter(Complaint.tracking_number == data["ticket"]).first()
            assert complaint is not None
            assert complaint.citizen_id == user.id
            assert "Dhule" in complaint.location_address
            assert "Shirpur" not in complaint.location_address
        finally:
            db.close()

    def test_duplicate_webhook_delivery(self):
        run_id = uuid.uuid4().hex[:12]
        msg_id = f"wamid.regr_dup_{run_id}"
        sender = f"91{random.randint(1000000000, 9999999999)}"
        orig_secret = config.META_APP_SECRET
        config.META_APP_SECRET = "webhook_regression_secret"

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "104829104829104",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "15550234567", "phone_number_id": "104829104829104"},
                        "messages": [{
                            "from": sender,
                            "id": msg_id,
                            "timestamp": "1710000000",
                            "type": "text",
                            "text": {"body": "hey"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        raw_bytes = json.dumps(payload).encode("utf-8")
        sig = _calc_sig(config.META_APP_SECRET, raw_bytes)
        headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

        try:
            # First delivery
            res1 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
            assert res1.status_code == 200
            assert res1.json()["status"] == "processed"

            # Duplicate delivery with identical message_id
            res2 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
            assert res2.status_code == 200
            assert res2.json()["status"] == "processed"
        finally:
            config.META_APP_SECRET = orig_secret

    def test_no_shirpur_branding_or_shp_in_active_responses(self):
        texts = _build_texts()
        forbidden = ["shirpur", "शिरपूर", "shp-"]

        for lang in ["mr", "en"]:
            lang_dict = texts[lang]
            for key in ["unauthorized", "not_linked_prompt", "authorized_welcome", "menu_options", "help_text", "link_invalid"]:
                text_val = lang_dict[key].lower()
                for bad_word in forbidden:
                    assert bad_word not in text_val, f"Found '{bad_word}' in texts['{lang}']['{key}']"
            # Verify frontend URL is actual Render URL
            assert "https://ecopulse-ai-frontend.onrender.com/" in lang_dict["not_linked_prompt"]
            assert "ecopulse.ai" not in lang_dict["not_linked_prompt"]
