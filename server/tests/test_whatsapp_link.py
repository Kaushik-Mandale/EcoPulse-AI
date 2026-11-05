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
