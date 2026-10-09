import pytest
import logging
import httpx
from fastapi.testclient import TestClient
from server.main import app
from server.utils.config import config

client = TestClient(app)

def test_meta_webhook_verification_handshake():
    # Valid handshake
    res = client.get(
        "/api/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": config.WHATSAPP_VERIFY_TOKEN,
            "hub.challenge": "11582014"
        }
    )
    assert res.status_code == 200
    assert res.text == "11582014"

    # Invalid token handshake
    res_bad = client.get(
        "/api/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token_123",
            "hub.challenge": "11582014"
        }
    )
    assert res_bad.status_code == 403

def test_unauthorized_user_prompt():
    unauth_phone = "917711223344"
    # Ensure this phone starts clean/unauthorized
    res = client.post(
        "/api/whatsapp/simulate-incoming",
        json={"phone": unauth_phone, "message": "Hello", "type": "text"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "unauthorized_prompt"
    assert "JOIN SHP-W12-H1042" in data["reply"]

def test_qr_code_authorization():
    auth_phone = "919988776655"
    res = client.post(
        "/api/whatsapp/simulate-incoming",
        json={"phone": auth_phone, "message": "JOIN SHP-W14-H2045", "type": "text"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "authorized"
    assert "Ward 14" in data["reply"]
    assert "SHP-W14-H2045" in data["reply"]

def test_authorized_dashboard_navigation():
    test_phone = "919988776655"

    # 1. Track complaints
    res_track = client.post(
        "/api/whatsapp/simulate-incoming",
        json={"phone": test_phone, "message": "2", "type": "text"}
    )
    assert res_track.status_code == 200
    assert res_track.json()["status"] == "track_complaints"

    # 2. Eco Wallet
    res_wallet = client.post(
        "/api/whatsapp/simulate-incoming",
        json={"phone": test_phone, "message": "3", "type": "text"}
    )
    assert res_wallet.status_code == 200
    assert res_wallet.json()["status"] == "wallet_info"
    assert "EcoCoin" in res_wallet.json()["reply"]

    # 3. Live Truck Tracking
    res_truck = client.post(
        "/api/whatsapp/simulate-incoming",
        json={"phone": test_phone, "message": "4", "type": "text"}
    )
    assert res_truck.status_code == 200
    assert res_truck.json()["status"] == "truck_tracking"
    assert "MH-18-BZ-4412" in res_truck.json()["reply"]

def test_photo_and_location_complaint_flow():
    test_phone = "919988776655"

    # Step 1: Send Photo
    res_photo = client.post(
        "/api/whatsapp/simulate-incoming",
        json={
            "phone": test_phone,
            "message": "",
            "type": "image",
            "media_url": "https://example.com/overflow_bin.jpg"
        }
    )
    assert res_photo.status_code == 200
    assert res_photo.json()["status"] == "awaiting_location"

    # Step 2: Send WhatsApp GPS Location Pin
    res_loc = client.post(
        "/api/whatsapp/simulate-incoming",
        json={
            "phone": test_phone,
            "message": "",
            "type": "location",
            "latitude": 21.3487,
            "longitude": 74.8812
        }
    )
    assert res_loc.status_code == 200
    data = res_loc.json()
    assert data["status"] == "complaint_created"
    assert "SHP-2026-W14" in data["ticket"]
    assert "+20" in data["reply"]

def test_generate_household_qr():
    res = client.post(
        "/api/whatsapp/generate-qr",
        json={"ward": 14, "household_number": 2045}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["household_code"] == "SHP-W14-H2045"
    assert "JOIN SHP-W14-H2045" in data["qr_scan_text"]
    assert "wa.me" in data["whatsapp_direct_link"]

def test_list_whatsapp_citizens_unauthenticated():
    res = client.get("/api/whatsapp/citizens")
    assert res.status_code == 401


def test_list_whatsapp_citizens_authorized_admin():
    # Login as pre-seeded admin
    login_res = client.post("/api/auth/login", json={
        "email": "admin@cityswap.io",
        "password": "Password123!",
        "role": "admin"
    })
    assert login_res.status_code == 200
    admin_token = login_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    res = client.get("/api/whatsapp/citizens", headers=admin_headers)
    assert res.status_code == 200
    citizens = res.json()
    assert isinstance(citizens, list)
    assert any(c["household_id"] == "SHP-W14-H2045" for c in citizens)


# -----------------------------------------------------------------
# Task 1 & 7: Meta Webhook HMAC Signature Verification Tests
# -----------------------------------------------------------------

import hmac
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from server.database.db import SessionLocal
from server.models.whatsapp_session import WhatsAppProcessedMessage


def _calc_sig(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _make_meta_payload(msg_id: str, sender: str, text: str = "Hello") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "104829104829104",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550234567",
                                "phone_number_id": "104829104829104"
                            },
                            "messages": [
                                {
                                    "from": sender,
                                    "id": msg_id,
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": text}
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }


def test_meta_webhook_signature_valid():
    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "super_secure_meta_app_secret_123"
    try:
        payload = _make_meta_payload("wamid.test_sig_001", "919876543210", "Hello")
        raw_body = json.dumps(payload).encode("utf-8")
        sig = _calc_sig(config.META_APP_SECRET, raw_body)

        res = client.post(
            "/api/whatsapp/webhook",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig
            }
        )
        assert res.status_code == 200
        assert res.json()["status"] == "processed"
    finally:
        config.META_APP_SECRET = orig_secret


def test_meta_webhook_signature_invalid():
    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "super_secure_meta_app_secret_123"
    try:
        payload = _make_meta_payload("wamid.test_sig_002", "919876543210", "Hello")
        raw_body = json.dumps(payload).encode("utf-8")

        res = client.post(
            "/api/whatsapp/webhook",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid_bogus_signature_hash_hex"
            }
        )
        assert res.status_code == 403
        assert "Invalid signature" in res.json()["detail"]
    finally:
        config.META_APP_SECRET = orig_secret


def test_meta_webhook_signature_missing():
    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "super_secure_meta_app_secret_123"
    try:
        payload = _make_meta_payload("wamid.test_sig_003", "919876543210", "Hello")
        raw_body = json.dumps(payload).encode("utf-8")

        res = client.post(
            "/api/whatsapp/webhook",
            content=raw_body,
            headers={"Content-Type": "application/json"}
        )
        assert res.status_code == 403
        assert "Missing" in res.json()["detail"]
    finally:
        config.META_APP_SECRET = orig_secret


# -----------------------------------------------------------------
# Task 3 & 7: Message Idempotency & Deduplication Tests
# -----------------------------------------------------------------

def test_message_idempotency_first_and_duplicate():
    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "test_idempotency_secret"
    try:
        msg_id = "wamid.idempotency_test_first_001"
        sender = "919988776655"
        payload = _make_meta_payload(msg_id, sender, "3")
        raw_body = json.dumps(payload).encode("utf-8")
        sig = _calc_sig(config.META_APP_SECRET, raw_body)
        headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

        # First delivery: processed
        res1 = client.post("/api/whatsapp/webhook", content=raw_body, headers=headers)
        assert res1.status_code == 200
        assert res1.json()["status"] == "processed"

        # Verify DB records processed message
        db = SessionLocal()
        try:
            record = db.query(WhatsAppProcessedMessage).filter(
                WhatsAppProcessedMessage.message_id == msg_id
            ).first()
            assert record is not None
            assert record.phone_number == sender
        finally:
            db.close()

        # Second delivery (replay / retry): should be ignored cleanly with 200
        res2 = client.post("/api/whatsapp/webhook", content=raw_body, headers=headers)
        assert res2.status_code == 200
        assert res2.json()["status"] == "processed"
    finally:
        config.META_APP_SECRET = orig_secret


def test_message_idempotency_concurrent():
    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "concurrent_secret"
    try:
        msg_id = "wamid.concurrent_test_batch_001"
        sender = "919988776655"
        payload = _make_meta_payload(msg_id, sender, "1")
        raw_body = json.dumps(payload).encode("utf-8")
        sig = _calc_sig(config.META_APP_SECRET, raw_body)
        headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

        def _send():
            return client.post("/api/whatsapp/webhook", content=raw_body, headers=headers)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_send) for _ in range(4)]
            results = [f.result() for f in futures]

        for r in results:
            assert r.status_code == 200

        # Verify exactly one record exists in DB for this message_id
        db = SessionLocal()
        try:
            count = db.query(WhatsAppProcessedMessage).filter(
                WhatsAppProcessedMessage.message_id == msg_id
            ).count()
            assert count == 1
        finally:
            db.close()
    finally:
        config.META_APP_SECRET = orig_secret


# -----------------------------------------------------------------
# Task 5 & 7: Simulator Environment Protection Tests
# -----------------------------------------------------------------

def test_simulator_environment_protection():
    orig_env = config.ENV

    # 1. Development: works
    config.ENV = "development"
    res_dev = client.post(
        "/api/whatsapp/simulate-incoming",
        json={"phone": "919988776655", "message": "1", "type": "text"}
    )
    assert res_dev.status_code == 200

    # 2. Production: rejected
    config.ENV = "production"
    res_prod = client.post(
        "/api/whatsapp/simulate-incoming",
        json={"phone": "919988776655", "message": "1", "type": "text"}
    )
    assert res_prod.status_code == 403
    assert "disabled in production" in res_prod.json()["detail"]

    # Reset
    config.ENV = orig_env


# =================================================================
# Job 1B: Real WhatsApp Media Pipeline Tests (A through Q)
# =================================================================

import os
from unittest.mock import patch
from server.services.whatsapp_service import WhatsAppService, validate_image_content, MediaValidationError
from server.services.media_storage import get_media_storage
from server.models.complaint import Complaint
from server.models.whatsapp_session import WhatsAppCitizen as _WhatsAppCitizenModel

# Alias for Job 1B tests (WhatsAppCitizen already imported via server.models.whatsapp_session above)
_Citizen1B = _WhatsAppCitizenModel


SAMPLE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x11" * 200
SAMPLE_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00" + b"\x22" * 200
SAMPLE_WEBP = b"RIFF\x30\x00\x00\x00WEBPVP8 \x24\x00\x00\x00" + b"\x33" * 200


def _mock_meta_get(mock_media_id: str, content: bytes, mime_type: str = "image/jpeg", meta_status: int = 200, bin_status: int = 200):
    cdn_path = f"/mock_media_cdn/{mock_media_id}"

    def fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        # Check CDN (binary download) URL FIRST to avoid matching media_id inside CDN path
        if "lookaside.fbsbx.com" in url:
            if bin_status != 200:
                return httpx.Response(bin_status, request=req, content=b"Download error")
            return httpx.Response(200, request=req, content=content)
        # Then check Meta Graph API metadata URL
        elif f"/{mock_media_id}" in url:
            if meta_status != 200:
                return httpx.Response(meta_status, request=req, json={"error": {"message": "Meta Error"}})
            return httpx.Response(200, request=req, json={
                "url": f"https://lookaside.fbsbx.com{cdn_path}",
                "mime_type": mime_type,
                "file_size": len(content),
                "id": mock_media_id
            })
        return httpx.Response(404, request=req)
    return fake_get


def test_media_validation_accepted_formats():
    # C. JPEG accepted
    mime_jpg, ext_jpg = validate_image_content(SAMPLE_JPEG, declared_mime_type="image/jpeg")
    assert mime_jpg == "image/jpeg"
    assert ext_jpg == ".jpg"

    # D. PNG accepted
    mime_png, ext_png = validate_image_content(SAMPLE_PNG, declared_mime_type="image/png")
    assert mime_png == "image/png"
    assert ext_png == ".png"

    # E. WebP accepted
    mime_webp, ext_webp = validate_image_content(SAMPLE_WEBP, declared_mime_type="image/webp")
    assert mime_webp == "image/webp"
    assert ext_webp == ".webp"


def test_media_validation_rejected_unsupported_formats():
    # F. Unsupported MIME rejected (PDF binary)
    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"\x00" * 100
    with pytest.raises(MediaValidationError, match="Unsupported image format"):
        validate_image_content(pdf_bytes, declared_mime_type="application/pdf")

    # Unsupported declared MIME
    with pytest.raises(MediaValidationError, match="not an allowed image format"):
        validate_image_content(SAMPLE_JPEG, declared_mime_type="image/gif")

    # Mismatched declared MIME vs content
    with pytest.raises(MediaValidationError, match="does not match declared"):
        validate_image_content(SAMPLE_JPEG, declared_mime_type="image/png")


def test_media_validation_oversized_rejected():
    # G. Oversized image rejected
    oversized = b"\xff\xd8\xff" + b"\x00" * (10 * 1024 * 1024 + 10)
    with pytest.raises(MediaValidationError, match="exceeds maximum limit"):
        validate_image_content(oversized, max_size=10 * 1024 * 1024)


def test_media_validation_invalid_corrupted_rejected():
    # H. Invalid / corrupted / truncated binary rejected
    with pytest.raises(MediaValidationError, match="Empty"):
        validate_image_content(b"")

    with pytest.raises(MediaValidationError, match="Corrupted or truncated"):
        validate_image_content(b"\xff\xd8")


def test_meta_media_pipeline_jpeg_success():
    # A. Metadata retrieval, B. Binary download, C. JPEG, J. Local storage persistence
    orig_token = config.WHATSAPP_TOKEN
    config.WHATSAPP_TOKEN = "test_meta_token_val_1"
    media_id = "test_media_wamid_jpeg_100"
    created_path = None
    try:
        with patch.object(httpx.Client, "get", side_effect=_mock_meta_get(media_id, SAMPLE_JPEG, "image/jpeg")):
            res = WhatsAppService.fetch_and_store_meta_media(media_id)
            assert res["success"] is True
            assert res["mime_type"] == "image/jpeg"
            assert res["media_id"] == media_id
            assert res["file_size"] == len(SAMPLE_JPEG)
            assert res["storage_ref"].startswith("/uploads/whatsapp/")
            assert res["storage_ref"].endswith(".jpg")

            # Verify persisted file exists on filesystem (J)
            filename = os.path.basename(res["storage_ref"])
            created_path = os.path.join(get_media_storage().upload_dir, filename)
            assert os.path.isfile(created_path)
            assert os.path.getsize(created_path) == len(SAMPLE_JPEG)
    finally:
        config.WHATSAPP_TOKEN = orig_token
        if created_path and os.path.exists(created_path):
            os.remove(created_path)


def test_meta_media_pipeline_png_and_webp_success():
    # D. PNG accepted, E. WebP accepted
    orig_token = config.WHATSAPP_TOKEN
    config.WHATSAPP_TOKEN = "test_meta_token_val_2"
    cleaned_files = []
    try:
        # PNG
        media_png = "test_media_png_200"
        with patch.object(httpx.Client, "get", side_effect=_mock_meta_get(media_png, SAMPLE_PNG, "image/png")):
            res_png = WhatsAppService.fetch_and_store_meta_media(media_png)
            assert res_png["success"] is True
            assert res_png["mime_type"] == "image/png"
            assert res_png["storage_ref"].endswith(".png")
            cleaned_files.append(os.path.join(get_media_storage().upload_dir, os.path.basename(res_png["storage_ref"])))

        # WebP
        media_webp = "test_media_webp_300"
        with patch.object(httpx.Client, "get", side_effect=_mock_meta_get(media_webp, SAMPLE_WEBP, "image/webp")):
            res_webp = WhatsAppService.fetch_and_store_meta_media(media_webp)
            assert res_webp["success"] is True
            assert res_webp["mime_type"] == "image/webp"
            assert res_webp["storage_ref"].endswith(".webp")
            cleaned_files.append(os.path.join(get_media_storage().upload_dir, os.path.basename(res_webp["storage_ref"])))
    finally:
        config.WHATSAPP_TOKEN = orig_token
        for f in cleaned_files:
            if os.path.exists(f):
                os.remove(f)


def test_meta_media_pipeline_failures_handled_safely():
    # I. Meta API failure handled safely
    orig_token = config.WHATSAPP_TOKEN
    config.WHATSAPP_TOKEN = "test_meta_token_val_3"
    try:
        # 1. Meta 404 metadata
        with patch.object(httpx.Client, "get", side_effect=_mock_meta_get("fail_404", SAMPLE_JPEG, meta_status=404)):
            res_404 = WhatsAppService.fetch_and_store_meta_media("fail_404")
            assert res_404["success"] is False
            assert "404" in res_404["error"]

        # 2. Meta 500 binary download
        with patch.object(httpx.Client, "get", side_effect=_mock_meta_get("fail_500", SAMPLE_JPEG, bin_status=500)):
            res_500 = WhatsAppService.fetch_and_store_meta_media("fail_500")
            assert res_500["success"] is False
            assert "500" in res_500["error"]

        # 3. Timeout
        with patch.object(httpx.Client, "get", side_effect=httpx.TimeoutException("Read timeout")):
            res_to = WhatsAppService.fetch_and_store_meta_media("fail_timeout")
            assert res_to["success"] is False
            assert "timed out" in res_to["error"]

        # 4. Meta returns corrupted binary
        with patch.object(httpx.Client, "get", side_effect=_mock_meta_get("fail_corrupt", b"\x00\x01\x02")):
            res_corrupt = WhatsAppService.fetch_and_store_meta_media("fail_corrupt")
            assert res_corrupt["success"] is False
            assert "Corrupted or truncated" in res_corrupt["error"]
    finally:
        config.WHATSAPP_TOKEN = orig_token


def test_meta_webhook_image_to_location_real_pipeline():
    # K. Pending complaint data contains real stored image reference
    # L. Location message creates complaint using stored image reference
    # M. Unsplash fallback is NOT used
    import uuid
    from server.models.whatsapp_session import WhatsAppProcessedMessage as _WPM
    orig_secret = config.META_APP_SECRET
    orig_token = config.WHATSAPP_TOKEN
    config.META_APP_SECRET = "webhook_real_pipeline_secret"
    config.WHATSAPP_TOKEN = "webhook_real_pipeline_meta_token"
    created_path = None
    media_id = "wamid_real_pipeline_media_555"
    sender = "919988776655"
    # Use unique message IDs per test run to avoid idempotency false-positives
    run_id = uuid.uuid4().hex[:12]
    img_msg_id = f"wamid.img_event_{run_id}"
    loc_msg_id = f"wamid.loc_event_{run_id}"

    try:
        # -- Setup: Pre-create & authorize the citizen in DB --
        from server.database.db import SessionLocal as _SessionLocal
        _setup_db = _SessionLocal()
        try:
            existing = _setup_db.query(_WhatsAppCitizenModel).filter(
                _WhatsAppCitizenModel.phone_number == sender
            ).first()
            if existing:
                existing.is_authorized = True
                existing.household_id = "SHP-W99-H5555"
                existing.ward = "Ward 99"
                existing.conversation_state = "IDLE"
            else:
                _setup_db.add(_WhatsAppCitizenModel(
                    phone_number=sender,
                    full_name="Test Citizen Real Pipeline",
                    ward="Ward 99",
                    household_id="SHP-W99-H5555",
                    is_authorized=True,
                    conversation_state="IDLE",
                ))
            _setup_db.commit()
        finally:
            _setup_db.close()

        # Step 1: Send Image via official Meta Webhook event format
        image_payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "104829104829104",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"display_phone_number": "15550234567", "phone_number_id": "104829104829104"},
                                "messages": [
                                    {
                                        "from": sender,
                                        "id": img_msg_id,
                                        "timestamp": "1710000000",
                                        "type": "image",
                                        "image": {
                                            "id": media_id,
                                            "mime_type": "image/jpeg",
                                            "sha256": "abc123mock"
                                        }
                                    }
                                ]
                            },
                            "field": "messages"
                        }
                    ]
                }
            ]
        }
        raw_body_img = json.dumps(image_payload).encode("utf-8")
        sig_img = _calc_sig(config.META_APP_SECRET, raw_body_img)

        with patch.object(httpx.Client, "get", side_effect=_mock_meta_get(media_id, SAMPLE_JPEG, "image/jpeg")):
            res_img = client.post(
                "/api/whatsapp/webhook",
                content=raw_body_img,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig_img}
            )
            assert res_img.status_code == 200

        # Check DB citizen pending data (K)
        db = SessionLocal()
        try:
            citizen = db.query(_WhatsAppCitizenModel).filter(_WhatsAppCitizenModel.phone_number == sender).first()
            assert citizen.conversation_state == "AWAITING_LOCATION"
            pending = json.loads(citizen.pending_complaint_data)
            stored_url = pending["image_url"]
            assert stored_url.startswith("/uploads/whatsapp/")
            assert "unsplash.com" not in stored_url
            assert pending["media_id"] == media_id
            assert pending["mime_type"] == "image/jpeg"

            filename = os.path.basename(stored_url)
            created_path = os.path.join(get_media_storage().upload_dir, filename)
            assert os.path.isfile(created_path)
        finally:
            db.close()

        # Step 2: Send Location Pin via official Meta Webhook
        loc_payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "104829104829104",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"display_phone_number": "15550234567", "phone_number_id": "104829104829104"},
                                "messages": [
                                    {
                                        "from": sender,
                                        "id": loc_msg_id,
                                        "timestamp": "1710000001",
                                        "type": "location",
                                        "location": {
                                            "latitude": 21.3487,
                                            "longitude": 74.8812
                                        }
                                    }
                                ]
                            },
                            "field": "messages"
                        }
                    ]
                }
            ]
        }
        raw_body_loc = json.dumps(loc_payload).encode("utf-8")
        sig_loc = _calc_sig(config.META_APP_SECRET, raw_body_loc)

        res_loc = client.post(
            "/api/whatsapp/webhook",
            content=raw_body_loc,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig_loc}
        )
        assert res_loc.status_code == 200

        # Check Complaint created in DB (L, M)
        db = SessionLocal()
        try:
            complaint = db.query(Complaint).order_by(Complaint.id.desc()).first()
            assert complaint is not None
            assert complaint.image_url == stored_url
            assert "unsplash" not in complaint.image_url
            assert complaint.latitude == 21.3487
            assert complaint.longitude == 74.8812
        finally:
            db.close()

    finally:
        config.META_APP_SECRET = orig_secret
        config.WHATSAPP_TOKEN = orig_token
        if created_path and os.path.exists(created_path):
            os.remove(created_path)
        # Cleanup: remove test citizen and processed message records to avoid pollution
        _cleanup_db = SessionLocal()
        try:
            _cleanup_db.query(_WhatsAppCitizenModel).filter(
                _WhatsAppCitizenModel.phone_number == sender
            ).delete()
            _cleanup_db.query(_WPM).filter(
                _WPM.message_id.in_([img_msg_id, loc_msg_id])
            ).delete(synchronize_session=False)
            _cleanup_db.commit()
        finally:
            _cleanup_db.close()


def test_meta_media_token_never_logged_or_exposed(caplog):
    # N. No WhatsApp token appears in logs/errors/responses
    orig_token = config.WHATSAPP_TOKEN
    secret_token_str = "SUPER_SECRET_TOKEN_NEVER_LOG_99999"
    config.WHATSAPP_TOKEN = secret_token_str
    created_path = None
    media_id = "test_media_token_privacy_001"

    try:
        with caplog.at_level(logging.DEBUG):
            # 1. Success flow
            with patch.object(httpx.Client, "get", side_effect=_mock_meta_get(media_id, SAMPLE_JPEG)):
                res_ok = WhatsAppService.fetch_and_store_meta_media(media_id)
                assert res_ok["success"] is True
                created_path = os.path.join(get_media_storage().upload_dir, os.path.basename(res_ok["storage_ref"]))

            # 2. Failure flow
            with patch.object(httpx.Client, "get", side_effect=_mock_meta_get("fail_token_test", SAMPLE_JPEG, meta_status=401)):
                res_err = WhatsAppService.fetch_and_store_meta_media("fail_token_test")
                assert res_err["success"] is False

        # Verify secret token is NEVER present in logged output
        assert secret_token_str not in caplog.text
        # Verify secret token is NEVER in returned dict
        assert secret_token_str not in json.dumps(res_ok)
        assert secret_token_str not in json.dumps(res_err)

    finally:
        config.WHATSAPP_TOKEN = orig_token
        if created_path and os.path.exists(created_path):
            os.remove(created_path)


# -----------------------------------------------------------------
# Job 1C: Dynamic Driver Assignment and WhatsApp Citizen Identity
# -----------------------------------------------------------------

def test_whatsapp_citizen_unambiguous_phone_match():
    # 1. WhatsApp citizen with an unambiguous existing phone-number match
    # 4. Complaint creation with the correct citizen association
    import random
    from uuid import uuid4
    from server.database.db import SessionLocal
    from server.models.user import User
    from server.models.complaint import Complaint
    from server.models.whatsapp_session import WhatsAppCitizen

    run_id = uuid4().hex[:8]
    test_phone = f"91987{random.randint(1000000, 9999999)}"
    test_email = f"citizen_{run_id}@cityswap.io"

    db = SessionLocal()
    created_user_id = None
    try:
        test_user = User(
            full_name=f"Verified Citizen {run_id}",
            email=test_email,
            phone=test_phone,
            role="citizen",
            hashed_password="dummy",
            ward="Ward 12",
            eco_coins=100
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        created_user_id = test_user.id

        w_citizen = WhatsAppCitizen(
            phone_number=test_phone,
            full_name="WhatsApp Reporter",
            ward="Ward 12",
            household_id="SHP-W12-H1042",
            is_authorized=True,
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/test.jpg", "waste_type": "Mixed Waste"})
        )
        db.add(w_citizen)
        db.commit()

        res = client.post(
            "/api/whatsapp/simulate-incoming",
            json={
                "phone": test_phone,
                "message": "",
                "type": "location",
                "latitude": 21.3487,
                "longitude": 74.8812
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "complaint_created"

        complaint = db.query(Complaint).filter(Complaint.tracking_number == data["ticket"]).first()
        assert complaint is not None
        assert complaint.citizen_id == created_user_id

        db.refresh(test_user)
        assert test_user.eco_coins == 120

    finally:
        from server.models.task import DriverTask as _DT1
        if created_user_id:
            # Delete associated DriverTasks before deleting Complaints (avoids orphaned tasks
            # that cause SQLite to reuse complaint IDs in subsequent tests).
            complaints_to_delete = db.query(Complaint).filter(
                Complaint.citizen_id == created_user_id
            ).all()
            for c in complaints_to_delete:
                db.query(_DT1).filter(_DT1.complaint_id == c.id).delete()
            db.query(Complaint).filter(Complaint.citizen_id == created_user_id).delete()
            db.query(User).filter(User.id == created_user_id).delete()
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == test_phone).delete()
        db.commit()
        db.close()


def test_whatsapp_sender_no_matching_citizen_account():
    # 2. WhatsApp sender with no matching citizen account (guest-citizen flow)
    import random
    from server.database.db import SessionLocal
    from server.models.complaint import Complaint
    from server.models.whatsapp_session import WhatsAppCitizen

    test_phone = f"91986{random.randint(1000000, 9999999)}"
    db = SessionLocal()
    ticket_created = None
    try:
        w_citizen = WhatsAppCitizen(
            phone_number=test_phone,
            full_name="Guest Resident",
            ward="Ward 12",
            household_id="SHP-W12-H9999",
            is_authorized=True,
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/test_guest.jpg", "waste_type": "Plastic Waste"})
        )
        db.add(w_citizen)
        db.commit()

        res = client.post(
            "/api/whatsapp/simulate-incoming",
            json={
                "phone": test_phone,
                "message": "",
                "type": "location",
                "latitude": 21.3487,
                "longitude": 74.8812
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "complaint_created"
        ticket_created = data["ticket"]

        complaint = db.query(Complaint).filter(Complaint.tracking_number == ticket_created).first()
        assert complaint is not None
        assert complaint.citizen_id is None

    finally:
        from server.models.task import DriverTask as _DT2
        if ticket_created:
            c_to_del = db.query(Complaint).filter(
                Complaint.tracking_number == ticket_created
            ).first()
            if c_to_del:
                db.query(_DT2).filter(_DT2.complaint_id == c_to_del.id).delete()
            db.query(Complaint).filter(Complaint.tracking_number == ticket_created).delete()
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == test_phone).delete()
        db.commit()
        db.close()


def test_whatsapp_sender_ambiguous_duplicate_phone_matches():
    # 3. Ambiguous or duplicate phone-number matches safely handled
    import random
    from uuid import uuid4
    from server.database.db import SessionLocal
    from server.models.user import User
    from server.models.complaint import Complaint
    from server.models.whatsapp_session import WhatsAppCitizen

    run_id = uuid4().hex[:8]
    test_phone = f"91985{random.randint(1000000, 9999999)}"
    user_ids = []
    db = SessionLocal()
    ticket_created = None
    try:
        u1 = User(full_name=f"Dupe 1 {run_id}", email=f"dupe1_{run_id}@cityswap.io", phone=test_phone, role="citizen", hashed_password="dummy")
        u2 = User(full_name=f"Dupe 2 {run_id}", email=f"dupe2_{run_id}@cityswap.io", phone=test_phone, role="citizen", hashed_password="dummy")
        db.add_all([u1, u2])
        db.commit()
        db.refresh(u1)
        db.refresh(u2)
        user_ids = [u1.id, u2.id]

        w_citizen = WhatsAppCitizen(
            phone_number=test_phone,
            full_name="Ambiguous Reporter",
            ward="Ward 12",
            household_id="SHP-W12-H1111",
            is_authorized=True,
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/ambig.jpg", "waste_type": "Mixed Waste"})
        )
        db.add(w_citizen)
        db.commit()

        res = client.post(
            "/api/whatsapp/simulate-incoming",
            json={
                "phone": test_phone,
                "message": "",
                "type": "location",
                "latitude": 21.3487,
                "longitude": 74.8812
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "complaint_created"
        ticket_created = data["ticket"]

        complaint = db.query(Complaint).filter(Complaint.tracking_number == ticket_created).first()
        assert complaint is not None
        assert complaint.citizen_id is None

    finally:
        from server.models.task import DriverTask as _DT3
        if ticket_created:
            c_to_del2 = db.query(Complaint).filter(
                Complaint.tracking_number == ticket_created
            ).first()
            if c_to_del2:
                db.query(_DT3).filter(_DT3.complaint_id == c_to_del2.id).delete()
            db.query(Complaint).filter(Complaint.tracking_number == ticket_created).delete()
        if user_ids:
            db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == test_phone).delete()
        db.commit()
        db.close()


def test_dynamic_driver_assignment_least_active_workload():
    # 5. Assignment to a real eligible driver by least active workload
    import random
    from uuid import uuid4
    from server.database.db import SessionLocal
    from server.models.user import User
    from server.models.task import DriverTask
    from server.models.whatsapp_session import WhatsAppCitizen
    from server.services.whatsapp_service import WhatsAppService

    run_id = uuid4().hex[:8]
    test_phone = f"91984{random.randint(1000000, 9999999)}"
    db = SessionLocal()
    driver_ids = []
    task_ids = []
    try:
        d_busy = User(
            full_name=f"Busy Driver {run_id}",
            email=f"busy_{run_id}@cityswap.io",
            employee_id=f"EMP-BSY-{run_id}",
            role="driver",
            is_active=True,
            is_locked=False,
            hashed_password="dummy"
        )
        d_idle = User(
            full_name=f"Idle Driver {run_id}",
            email=f"idle_{run_id}@cityswap.io",
            employee_id=f"EMP-IDL-{run_id}",
            role="driver",
            is_active=True,
            is_locked=False,
            hashed_password="dummy"
        )
        db.add_all([d_busy, d_idle])
        db.commit()
        db.refresh(d_busy)
        db.refresh(d_idle)
        driver_ids = [d_busy.id, d_idle.id]

        t1 = DriverTask(driver_id=d_busy.id, location_name="Loc 1", status="Pending")
        t2 = DriverTask(driver_id=d_busy.id, location_name="Loc 2", status="In Progress")
        db.add_all([t1, t2])
        db.commit()
        db.refresh(t1)
        db.refresh(t2)
        task_ids = [t1.id, t2.id]

        w_citizen = WhatsAppCitizen(
            phone_number=test_phone,
            is_authorized=True,
            ward="Ward 12",
            household_id="SHP-W12-H7777",
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/workload.jpg", "waste_type": "Mixed Waste"})
        )
        db.add(w_citizen)
        db.commit()

        selected = WhatsAppService.select_eligible_driver(db)
        assert selected is not None
        assert selected.role == "driver"
        assert selected.id != d_busy.id

    finally:
        if task_ids:
            db.query(DriverTask).filter(DriverTask.id.in_(task_ids)).delete(synchronize_session=False)
        if driver_ids:
            db.query(User).filter(User.id.in_(driver_ids)).delete(synchronize_session=False)
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == test_phone).delete()
        db.commit()
        db.close()


def test_no_eligible_driver_retains_unassigned_complaint_and_task():
    # 6. No eligible driver available: complaint and task are retained safely unassigned.
    # Calls the service directly (not via HTTP) to avoid cross-session driver-visibility
    # issues that arise when multiple SQLite connections see different snapshots.
    import random
    from server.database.db import SessionLocal
    from server.models.user import User
    from server.models.task import DriverTask
    from server.models.complaint import Complaint
    from server.models.whatsapp_session import WhatsAppCitizen
    from server.services.whatsapp_service import WhatsAppService

    test_ward = f"Ward {random.randint(500, 999)}"
    test_phone = f"91983{random.randint(1000000, 9999999)}"
    db = SessionLocal()
    ticket_created = None
    # Record original active state for ALL drivers so we can restore.
    drivers = db.query(User).filter(User.role == "driver").all()
    orig_active = {d.id: d.is_active for d in drivers}
    try:
        # Deactivate every driver in this session so select_eligible_driver returns None.
        for d in drivers:
            d.is_active = False
        db.commit()

        # Set up the WhatsApp citizen in AWAITING_LOCATION state (same session).
        w_citizen = WhatsAppCitizen(
            phone_number=test_phone,
            is_authorized=True,
            ward=test_ward,
            household_id=f"SHP-W99-H{random.randint(1000, 9999)}",
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({
                "image_url": "/uploads/whatsapp/nodriver.jpg",
                "waste_type": "Mixed Waste"
            })
        )
        db.add(w_citizen)
        db.commit()

        # Call the service directly with the same db session, bypassing the HTTP layer.
        # This guarantees select_eligible_driver sees the same committed state as above.
        result = WhatsAppService.handle_incoming_message(
            db=db,
            sender_phone=test_phone,
            message_type="location",
            latitude=21.3487,
            longitude=74.8812,
        )
        assert result["status"] == "complaint_created"
        ticket_created = result["ticket"]

        # Verify complaint is unassigned.
        complaint = db.query(Complaint).filter(
            Complaint.tracking_number == ticket_created
        ).first()
        assert complaint is not None
        assert complaint.assigned_driver_id is None
        assert complaint.assigned_driver_name is None
        assert complaint.status == "Pending"

        # Verify task is created and unassigned.
        task = db.query(DriverTask).filter(
            DriverTask.complaint_id == complaint.id
        ).first()
        assert task is not None
        assert task.driver_id is None
        assert task.status == "Pending"

    finally:
        # Restore all drivers.
        if orig_active:
            to_restore = db.query(User).filter(User.id.in_(list(orig_active.keys()))).all()
            for d in to_restore:
                d.is_active = orig_active.get(d.id, True)
        if ticket_created:
            complaint = db.query(Complaint).filter(
                Complaint.tracking_number == ticket_created
            ).first()
            if complaint:
                db.query(DriverTask).filter(DriverTask.complaint_id == complaint.id).delete()
                db.query(Complaint).filter(Complaint.id == complaint.id).delete()
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == test_phone).delete()
        db.commit()
        db.close()


def test_citizen_account_never_selected_as_driver():
    # 7. A citizen account is never selected as a driver
    from server.database.db import SessionLocal
    from server.models.user import User
    from server.services.whatsapp_service import WhatsAppService

    db = SessionLocal()
    drivers = db.query(User).filter(User.role == "driver").all()
    orig_active = {d.id: d.is_active for d in drivers}
    try:
        for d in drivers:
            d.is_active = False
        citizen = User(
            full_name="Active Citizen Never Driver",
            email="citizen_never_driver@cityswap.io",
            role="citizen",
            is_active=True,
            is_locked=False,
            hashed_password="dummy"
        )
        db.add(citizen)
        db.commit()
        db.refresh(citizen)

        selected = WhatsAppService.select_eligible_driver(db)
        assert selected is None

    finally:
        for d in drivers:
            d.is_active = orig_active.get(d.id, True)
        db.query(User).filter(User.email == "citizen_never_driver@cityswap.io").delete()
        db.commit()
        db.close()


def test_assigned_task_accessible_through_driver_workflow():
    # 8. The assigned task is accessible through the existing driver workflow
    from uuid import uuid4
    from server.database.db import SessionLocal
    from server.models.user import User
    from server.models.task import DriverTask
    from server.utils.security import create_access_token

    run_id = uuid4().hex[:8]
    db = SessionLocal()
    driver_id = None
    task_id = None
    try:
        driver = User(
            full_name=f"Duty Driver {run_id}",
            email=f"duty_{run_id}@cityswap.io",
            employee_id=f"EMP-DUTY-{run_id}",
            role="driver",
            is_active=True,
            is_locked=False,
            hashed_password="dummy"
        )
        db.add(driver)
        db.commit()
        db.refresh(driver)
        driver_id = driver.id

        task = DriverTask(
            driver_id=driver.id,
            location_name=f"Assigned Street {run_id}",
            status="Pending",
            route_order=1
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

        token = create_access_token({"sub": driver.email})
        res = client.get("/api/driver/tasks", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        tasks = res.json()
        assert any(t["id"] == task_id for t in tasks)

    finally:
        if task_id:
            db.query(DriverTask).filter(DriverTask.id == task_id).delete()
        if driver_id:
            db.query(User).filter(User.id == driver_id).delete()
        db.commit()
        db.close()


def test_duplicate_webhook_delivery_idempotency_for_tasks_and_complaints():
    # 9. Duplicate webhook delivery does not create duplicate complaints or tasks
    import random
    from uuid import uuid4
    from server.database.db import SessionLocal
    from server.models.complaint import Complaint
    from server.models.task import DriverTask
    from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage

    run_id = uuid4().hex[:12]
    msg_id = f"wamid.idem_dup_{run_id}"
    sender = f"91981{random.randint(1000000, 9999999)}"
    unique_household = f"SHP-IDEM-{run_id}"

    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "idem_test_secret"

    db = SessionLocal()
    created_complaint_id = None
    try:
        w_citizen = WhatsAppCitizen(
            phone_number=sender,
            is_authorized=True,
            household_id=unique_household,
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/idem.jpg", "waste_type": "Mixed Waste"})
        )
        db.add(w_citizen)
        db.commit()

        loc_payload = {
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
                            "timestamp": "1710000002",
                            "type": "location",
                            "location": {"latitude": 21.3487, "longitude": 74.8812}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        raw_bytes = json.dumps(loc_payload).encode("utf-8")
        sig = _calc_sig(config.META_APP_SECRET, raw_bytes)

        # 1st Delivery -> Creates complaint & task
        res1 = client.post(
            "/api/whatsapp/webhook",
            content=raw_bytes,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig}
        )
        assert res1.status_code == 200

        # Capture the uniquely created complaint ID
        created_c = db.query(Complaint).filter(
            Complaint.description.like(f"%{unique_household}%")
        ).first()
        if created_c:
            created_complaint_id = created_c.id

        initial_complaints = db.query(Complaint).count()
        initial_tasks = db.query(DriverTask).count()

        # 2nd Delivery (exact duplicate retry)
        res2 = client.post(
            "/api/whatsapp/webhook",
            content=raw_bytes,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig}
        )
        assert res2.status_code == 200

        # Assert no duplicate complaints or tasks were created
        assert db.query(Complaint).count() == initial_complaints
        assert db.query(DriverTask).count() == initial_tasks

    finally:
        config.META_APP_SECRET = orig_secret
        if created_complaint_id:
            db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).delete()
            db.query(Complaint).filter(Complaint.id == created_complaint_id).delete()
        else:
            fallback_c = db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).first()
            if fallback_c:
                db.query(DriverTask).filter(DriverTask.complaint_id == fallback_c.id).delete()
                db.delete(fallback_c)
        db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).delete()
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == sender).delete()
        db.commit()
        db.close()

    # Verify no test-created complaint or task was left in the database
    verify_db = SessionLocal()
    try:
        assert verify_db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).count() == 0
        if created_complaint_id:
            assert verify_db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).count() == 0
    finally:
        verify_db.close()


def test_whatsapp_invalid_phone_normalization_never_matches_empty_phone_user():
    # Fix 2 Regression: invalid input such as "", "+", "abc", whitespace never matches a user with phone=""
    from uuid import uuid4
    from server.database.db import SessionLocal
    from server.models.user import User
    from server.services.whatsapp_service import WhatsAppService

    run_id = uuid4().hex[:8]
    db = SessionLocal()
    user_id = None
    try:
        # User registered with empty string phone (e.g. from web registration without phone)
        blank_phone_user = User(
            full_name=f"No Phone Citizen {run_id}",
            email=f"nophone_{run_id}@cityswap.io",
            phone="",
            role="citizen",
            is_active=True,
            hashed_password="dummy"
        )
        db.add(blank_phone_user)
        db.commit()
        db.refresh(blank_phone_user)
        user_id = blank_phone_user.id

        # Verify normalize_phone outputs
        assert WhatsAppService.normalize_phone("") == ""
        assert WhatsAppService.normalize_phone("+") == ""
        assert WhatsAppService.normalize_phone("abc") == ""
        assert WhatsAppService.normalize_phone("   ") == ""
        assert WhatsAppService.normalize_phone(None) == ""

        # Verify none of these invalid inputs resolve to the user with phone=""
        assert WhatsAppService.find_matching_citizen_user(db, "") is None
        assert WhatsAppService.find_matching_citizen_user(db, "+") is None
        assert WhatsAppService.find_matching_citizen_user(db, "abc") is None
        assert WhatsAppService.find_matching_citizen_user(db, "   ") is None
        assert WhatsAppService.find_matching_citizen_user(db, "+--") is None
        assert WhatsAppService.find_matching_citizen_user(db, "12345") is None  # < 10 digits
        assert WhatsAppService.find_matching_citizen_user(db, None) is None

    finally:
        if user_id:
            db.query(User).filter(User.id == user_id).delete()
            db.commit()
        db.close()


def test_whatsapp_valid_indian_phone_matching_formats():
    # Fix 2: Preserves valid matching for +91, 91, and 10-digit Indian formats
    from uuid import uuid4
    import random
    from server.database.db import SessionLocal
    from server.models.user import User
    from server.services.whatsapp_service import WhatsAppService

    run_id = uuid4().hex[:8]
    base_10 = f"987{random.randint(1000000, 9999999)}"
    db = SessionLocal()
    user_id = None
    try:
        # Citizen registered with raw 10-digit phone
        user = User(
            full_name=f"Standard Indian Citizen {run_id}",
            email=f"indian_{run_id}@cityswap.io",
            phone=base_10,
            role="citizen",
            is_active=True,
            hashed_password="dummy"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        # All 3 incoming formats resolve to this user
        match_raw = WhatsAppService.find_matching_citizen_user(db, base_10)
        assert match_raw is not None and match_raw.id == user_id

        match_with_plus = WhatsAppService.find_matching_citizen_user(db, f"+91{base_10}")
        assert match_with_plus is not None and match_with_plus.id == user_id

        match_with_91 = WhatsAppService.find_matching_citizen_user(db, f"91{base_10}")
        assert match_with_91 is not None and match_with_91.id == user_id

    finally:
        if user_id:
            db.query(User).filter(User.id == user_id).delete()
            db.commit()
        db.close()


def test_atomic_complaint_task_rollback_on_task_persistence_failure(monkeypatch):
    # Fix 3: Simulate task persistence failure and verify atomic rollback (no partial complaint/task persisted)
    from uuid import uuid4
    import random
    from server.database.db import SessionLocal
    from server.models.complaint import Complaint
    from server.models.task import DriverTask
    from server.models.whatsapp_session import WhatsAppCitizen
    from server.services.whatsapp_service import WhatsAppService

    run_id = uuid4().hex[:8]
    test_phone = f"91989{random.randint(1000000, 9999999)}"
    unique_household = f"SHP-ATOMIC-{run_id}"

    db = SessionLocal()
    try:
        w_citizen = WhatsAppCitizen(
            phone_number=test_phone,
            is_authorized=True,
            household_id=unique_household,
            ward="Ward 12",
            eco_coins=100,
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/atomic.jpg", "waste_type": "Mixed Waste"})
        )
        db.add(w_citizen)
        db.commit()

        # Monkeypatch DriverTask instantiation to simulate an unexpected error during task creation
        original_init = DriverTask.__init__
        def failing_init(self, *args, **kwargs):
            raise RuntimeError("Simulated failure during DriverTask creation")

        monkeypatch.setattr(DriverTask, "__init__", failing_init)

        # Call handle_incoming_message and assert exception is raised
        with pytest.raises(RuntimeError, match="Simulated failure during DriverTask creation"):
            WhatsAppService.handle_incoming_message(
                db=db,
                sender_phone=test_phone,
                message_type="location",
                latitude=21.3487,
                longitude=74.8812
            )

        # Verify that atomic rollback prevented the Complaint from being committed
        uncommitted_complaint = db.query(Complaint).filter(
            Complaint.description.like(f"%{unique_household}%")
        ).first()
        assert uncommitted_complaint is None, "Complaint was committed despite task creation failure!"

        # Verify citizen state was rolled back to AWAITING_LOCATION and eco_coins unchanged
        db.refresh(w_citizen)
        assert w_citizen.conversation_state == "AWAITING_LOCATION"
        assert w_citizen.eco_coins == 100

    finally:
        # Cleanup
        db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).delete()
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == test_phone).delete()
        db.commit()
        db.close()


# =================================================================
# Job 1D: Webhook Idempotency State Machine & Retry Hardening Tests
# =================================================================

def test_webhook_transient_failure_then_successful_retry():
    # Job 1D: Transient failure allows safe retry with same message ID
    # Verifies failure does not leave message permanently unretryable or completed
    from uuid import uuid4
    import random
    from unittest.mock import patch
    from server.database.db import SessionLocal
    from server.models.complaint import Complaint
    from server.models.task import DriverTask
    from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage

    run_id = uuid4().hex[:12]
    msg_id = f"wamid.retry_test_{run_id}"
    sender = f"91971{random.randint(1000000, 9999999)}"
    unique_household = f"SHP-RETRY-{run_id}"

    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "job1d_retry_secret"

    db = SessionLocal()
    created_complaint_id = None
    try:
        # Pre-create authorized citizen awaiting location
        w_citizen = WhatsAppCitizen(
            phone_number=sender,
            is_authorized=True,
            household_id=unique_household,
            ward="Ward 12",
            eco_coins=100,
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/retry.jpg", "waste_type": "Mixed Waste"})
        )
        db.add(w_citizen)
        db.commit()

        loc_payload = {
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
                            "timestamp": "1710000100",
                            "type": "location",
                            "location": {"latitude": 21.3487, "longitude": 74.8812}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        raw_bytes = json.dumps(loc_payload).encode("utf-8")
        sig = _calc_sig(config.META_APP_SECRET, raw_bytes)
        headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

        # ----------------------------------------------------
        # Attempt 1: Transient processing error occurs
        # ----------------------------------------------------
        with patch.object(WhatsAppService, "handle_incoming_message", side_effect=RuntimeError("Transient DB connection glitch")):
            res1 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
            assert res1.status_code == 500

        # Verify DB state after failure:
        # 1. Message recorded as FAILED with error detail
        msg_record = db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).first()
        assert msg_record is not None
        assert msg_record.status == "FAILED"
        assert "Transient DB connection glitch" in (msg_record.error_message or "")

        # 2. No complaint or task created
        assert db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).count() == 0

        # 3. Citizen coins NOT awarded
        db.refresh(w_citizen)
        assert w_citizen.eco_coins == 100

        # ----------------------------------------------------
        # Attempt 2: Meta retries with the SAME message ID (success)
        # ----------------------------------------------------
        res2 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
        assert res2.status_code == 200
        assert res2.json()["status"] == "processed"

        # Verify DB state after retry success:
        # 1. Message status updated to COMPLETED
        db.refresh(msg_record)
        assert msg_record.status == "COMPLETED"
        assert msg_record.error_message is None

        # 2. Exactly one complaint created
        complaint = db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).first()
        assert complaint is not None
        created_complaint_id = complaint.id

        # 3. Exactly one task created
        task = db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).first()
        assert task is not None

        # 4. Citizen coins awarded once (+20)
        db.refresh(w_citizen)
        assert w_citizen.eco_coins == 120

        # ----------------------------------------------------
        # Attempt 3: Duplicate delivery after COMPLETED (idempotency replay)
        # ----------------------------------------------------
        res3 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
        assert res3.status_code == 200

        # Verify no duplicates were created
        assert db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).count() == 1
        assert db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).count() == 1
        db.refresh(w_citizen)
        assert w_citizen.eco_coins == 120

    finally:
        config.META_APP_SECRET = orig_secret
        if created_complaint_id:
            db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).delete()
            db.query(Complaint).filter(Complaint.id == created_complaint_id).delete()
        db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).delete()
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == sender).delete()
        db.commit()
        db.close()


def test_webhook_processing_failure_records_failed_status_with_error_detail():
    # Job 1D: A processing failure must not leave the message marked as COMPLETED
    from uuid import uuid4
    from unittest.mock import patch
    from server.database.db import SessionLocal
    from server.models.whatsapp_session import WhatsAppProcessedMessage

    run_id = uuid4().hex[:12]
    msg_id = f"wamid.fail_audit_{run_id}"
    sender = "919720001122"

    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "job1d_fail_secret"

    payload = _make_meta_payload(msg_id, sender, "test message")
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = _calc_sig(config.META_APP_SECRET, raw_bytes)
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

    db = SessionLocal()
    try:
        with patch.object(WhatsAppService, "handle_incoming_message", side_effect=ValueError("Custom processing failure")):
            res = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
            assert res.status_code == 500

        record = db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).first()
        assert record is not None
        assert record.status == "FAILED"
        assert "Custom processing failure" in (record.error_message or "")
    finally:
        config.META_APP_SECRET = orig_secret
        db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).delete()
        db.commit()
        db.close()


def test_webhook_concurrent_duplicate_delivery_state_machine_safety():
    # Job 1D: Concurrent duplicate deliveries do not create duplicate complaints or tasks
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4
    import random
    from server.database.db import SessionLocal
    from server.models.complaint import Complaint
    from server.models.task import DriverTask
    from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage

    run_id = uuid4().hex[:12]
    msg_id = f"wamid.concurrent_idem_{run_id}"
    sender = f"91973{random.randint(1000000, 9999999)}"
    unique_household = f"SHP-CONC-{run_id}"

    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "job1d_conc_secret"

    db = SessionLocal()
    created_complaint_id = None
    try:
        w_citizen = WhatsAppCitizen(
            phone_number=sender,
            is_authorized=True,
            household_id=unique_household,
            ward="Ward 12",
            eco_coins=100,
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/conc.jpg", "waste_type": "Mixed Waste"})
        )
        db.add(w_citizen)
        db.commit()

        loc_payload = {
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
                            "timestamp": "1710000200",
                            "type": "location",
                            "location": {"latitude": 21.3487, "longitude": 74.8812}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        raw_bytes = json.dumps(loc_payload).encode("utf-8")
        sig = _calc_sig(config.META_APP_SECRET, raw_bytes)
        headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

        def _send():
            return client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)

        # Send 4 duplicate deliveries simultaneously
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_send) for _ in range(4)]
            responses = [f.result() for f in futures]

        for r in responses:
            assert r.status_code == 200

        # Assert exactly one complaint and one task were created across all concurrent requests
        complaints = db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).all()
        assert len(complaints) == 1
        created_complaint_id = complaints[0].id

        tasks = db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).all()
        assert len(tasks) == 1

        # Assert message record is COMPLETED
        record = db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).first()
        assert record is not None
        assert record.status == "COMPLETED"

    finally:
        config.META_APP_SECRET = orig_secret
        if created_complaint_id:
            db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).delete()
            db.query(Complaint).filter(Complaint.id == created_complaint_id).delete()
        db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).delete()
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == sender).delete()
        db.commit()
        db.close()


def test_webhook_failure_after_handler_commit_does_not_duplicate_on_retry(monkeypatch):
    # Job 1D: Verifies that if a failure occurs after business logic commits but before
    # the message is marked COMPLETED, retrying with the same message ID does not create duplicate complaints.
    from uuid import uuid4
    import random
    from server.database.db import SessionLocal
    from server.models.complaint import Complaint
    from server.models.task import DriverTask
    from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage

    run_id = uuid4().hex[:12]
    msg_id = f"wamid.post_commit_fail_{run_id}"
    sender = f"91974{random.randint(1000000, 9999999)}"
    unique_household = f"SHP-PFAIL-{run_id}"

    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "job1d_pfail_secret"

    db = SessionLocal()
    created_complaint_id = None
    try:
        w_citizen = WhatsAppCitizen(
            phone_number=sender,
            is_authorized=True,
            household_id=unique_household,
            ward="Ward 12",
            eco_coins=100,
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/pfail.jpg", "waste_type": "Mixed Waste"})
        )
        db.add(w_citizen)
        db.commit()

        loc_payload = {
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
                            "timestamp": "1710000300",
                            "type": "location",
                            "location": {"latitude": 21.3487, "longitude": 74.8812}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        raw_bytes = json.dumps(loc_payload).encode("utf-8")
        sig = _calc_sig(config.META_APP_SECRET, raw_bytes)
        headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

        # -------------------------------------------------------------------------
        # Attempt 1: Handler commits complaint, but status update to COMPLETED raises
        # -------------------------------------------------------------------------
        real_handle = WhatsAppService.handle_incoming_message
        def handle_and_explode(*args, **kwargs):
            real_handle(*args, **kwargs)
            # Simulate unexpected failure after complaint commits but before route marks COMPLETED
            raise RuntimeError("Post-business-commit network glitch")

        monkeypatch.setattr(WhatsAppService, "handle_incoming_message", handle_and_explode)

        res1 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
        assert res1.status_code == 500

        # Complaint exists from attempt 1
        complaint = db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).first()
        assert complaint is not None
        created_complaint_id = complaint.id

        # Message is FAILED in DB but complaint_id is preserved
        msg_record = db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).first()
        assert msg_record.status == "FAILED"
        assert msg_record.complaint_id == created_complaint_id

        # -------------------------------------------------------------------------
        # Attempt 2: Meta retries with same message ID (un-patched)
        # -------------------------------------------------------------------------
        monkeypatch.undo()

        res2 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
        assert res2.status_code == 200

        # Verify that NO duplicate complaint or task was created on retry
        complaints_after = db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).all()
        assert len(complaints_after) == 1, "Duplicate complaint was created on retry!"

        tasks_after = db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).all()
        assert len(tasks_after) == 1, "Duplicate task was created on retry!"

        # Message is now marked COMPLETED
        db.refresh(msg_record)
        assert msg_record.status == "COMPLETED"

        # Verify correct recovery behavior: conversation state remains IDLE and coins not duplicated
        db.refresh(w_citizen)
        assert w_citizen.conversation_state == "IDLE", "Conversation state should remain IDLE, not reset to AWAITING_PHOTO"
        assert w_citizen.eco_coins == 120, "Eco coins should not be awarded multiple times on retry"

    finally:
        config.META_APP_SECRET = orig_secret
        if created_complaint_id:
            db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).delete()
            db.query(Complaint).filter(Complaint.id == created_complaint_id).delete()
        db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).delete()
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == sender).delete()
        db.commit()
        db.close()


def test_ensure_whatsapp_processed_messages_schema_repeatable():
    # Job 1D: Schema helper is idempotent, repeatable, and ensures required columns exist
    from sqlalchemy import inspect
    from server.database.db import engine
    from server.models.whatsapp_session import ensure_whatsapp_processed_messages_schema

    # Call twice to prove idempotence and safety
    ensure_whatsapp_processed_messages_schema(engine)
    ensure_whatsapp_processed_messages_schema(engine)

    insp = inspect(engine)
    cols = {col["name"] for col in insp.get_columns("whatsapp_processed_messages")}
    assert "status" in cols
    assert "complaint_id" in cols
    assert "error_message" in cols
    assert "updated_at" in cols
    assert "message_id" in cols


def test_webhook_concurrent_failed_retry_ownership():
    # Job 1D: Verifies that when a message in FAILED status is retried concurrently by multiple workers,
    # exactly one worker wins the atomic update claim and executes the business logic.
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4
    import random
    from server.database.db import SessionLocal
    from server.models.complaint import Complaint
    from server.models.task import DriverTask
    from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage

    run_id = uuid4().hex[:12]
    msg_id = f"wamid.conc_retry_{run_id}"
    sender = f"91975{random.randint(1000000, 9999999)}"
    unique_household = f"SHP-CRETRY-{run_id}"

    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "job1d_cretry_secret"

    db = SessionLocal()
    created_complaint_id = None
    try:
        w_citizen = WhatsAppCitizen(
            phone_number=sender,
            is_authorized=True,
            household_id=unique_household,
            ward="Ward 12",
            eco_coins=100,
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/cretry.jpg", "waste_type": "Mixed Waste"})
        )
        db.add(w_citizen)
        # Pre-seed a FAILED message record
        w_msg = WhatsAppProcessedMessage(
            message_id=msg_id,
            phone_number=sender,
            message_type="location",
            status="FAILED",
            error_message="Previous timeout"
        )
        db.add(w_msg)
        db.commit()

        loc_payload = {
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
                            "timestamp": "1710000400",
                            "type": "location",
                            "location": {"latitude": 21.3487, "longitude": 74.8812}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        raw_bytes = json.dumps(loc_payload).encode("utf-8")
        sig = _calc_sig(config.META_APP_SECRET, raw_bytes)
        headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

        def _send():
            return client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)

        # 3 workers race to retry the failed message simultaneously
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(_send) for _ in range(3)]
            responses = [f.result() for f in futures]

        for r in responses:
            assert r.status_code == 200

        # Verify exactly one complaint and one task created across all concurrent retries
        complaints = db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).all()
        assert len(complaints) == 1
        created_complaint_id = complaints[0].id

        tasks = db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).all()
        assert len(tasks) == 1

        # Verify citizen was awarded coins exactly once (+20 -> 120)
        db.refresh(w_citizen)
        assert w_citizen.eco_coins == 120

        # Verify message status transitioned to COMPLETED
        db.refresh(w_msg)
        assert w_msg.status == "COMPLETED"

    finally:
        config.META_APP_SECRET = orig_secret
        if created_complaint_id:
            db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).delete()
            db.query(Complaint).filter(Complaint.id == created_complaint_id).delete()
        db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).delete()
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == sender).delete()
        db.commit()
        db.close()


def test_webhook_post_commit_failure_recovery_returns_original_confirmation_and_preserves_state(monkeypatch):
    # Job 1D Final Check: Verifies that after a post-commit processing failure, a retry:
    # 1. Distinguishes the already-applied business operation from an unassisted message
    # 2. Recovers and delivers the original complaint confirmation (not "ask_photo")
    # 3. Leaves conversation state as IDLE (not reset to AWAITING_PHOTO)
    # 4. Does not create duplicate complaints, tasks, or coin awards
    from uuid import uuid4
    import random
    from server.database.db import SessionLocal
    from server.models.complaint import Complaint
    from server.models.task import DriverTask
    from server.models.whatsapp_session import WhatsAppCitizen, WhatsAppProcessedMessage

    run_id = uuid4().hex[:12]
    msg_id = f"wamid.recovery_check_{run_id}"
    sender = f"91976{random.randint(1000000, 9999999)}"
    unique_household = f"SHP-RECOV-{run_id}"

    orig_secret = config.META_APP_SECRET
    config.META_APP_SECRET = "job1d_recov_secret"

    outbound_messages = []
    def mock_send(to_phone, msg_text, *args, **kwargs):
        outbound_messages.append({"to": to_phone, "text": msg_text})
        return {"status": "simulated", "recipient": to_phone}

    monkeypatch.setattr(WhatsAppService, "send_meta_whatsapp", mock_send)

    db = SessionLocal()
    created_complaint_id = None
    try:
        w_citizen = WhatsAppCitizen(
            phone_number=sender,
            is_authorized=True,
            household_id=unique_household,
            ward="Ward 12",
            eco_coins=100,
            conversation_state="AWAITING_LOCATION",
            pending_complaint_data=json.dumps({"image_url": "/uploads/whatsapp/recov.jpg", "waste_type": "Mixed Waste"})
        )
        db.add(w_citizen)
        db.commit()

        loc_payload = {
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
                            "timestamp": "1710000500",
                            "type": "location",
                            "location": {"latitude": 21.3487, "longitude": 74.8812}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        raw_bytes = json.dumps(loc_payload).encode("utf-8")
        sig = _calc_sig(config.META_APP_SECRET, raw_bytes)
        headers = {"Content-Type": "application/json", "X-Hub-Signature-256": sig}

        # Attempt 1: Handler commits complaint, but raises right after
        real_handle = WhatsAppService.handle_incoming_message
        def handle_and_crash(*args, **kwargs):
            real_handle(*args, **kwargs)
            raise RuntimeError("Post-business-commit network crash")

        monkeypatch.setattr(WhatsAppService, "handle_incoming_message", handle_and_crash)

        res1 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
        assert res1.status_code == 500

        # Verify Attempt 1 created complaint and marked message FAILED with complaint_id correlated
        complaint = db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).first()
        assert complaint is not None
        assert "[msg:" not in complaint.description, "Complaint description must remain clean civic text without technical message ID tags"
        created_complaint_id = complaint.id
        original_ticket = complaint.tracking_number

        msg_rec = db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).first()
        assert msg_rec.status == "FAILED"
        assert msg_rec.complaint_id == created_complaint_id

        # Attempt 2: Meta retries with same message ID
        monkeypatch.setattr(WhatsAppService, "handle_incoming_message", real_handle)
        outbound_messages.clear()

        res2 = client.post("/api/whatsapp/webhook", content=raw_bytes, headers=headers)
        assert res2.status_code == 200

        # Verify no duplicate business records
        complaints_after = db.query(Complaint).filter(Complaint.description.like(f"%{unique_household}%")).all()
        assert len(complaints_after) == 1
        assert complaints_after[0].tracking_number == original_ticket

        tasks_after = db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).all()
        assert len(tasks_after) == 1

        # Verify citizen state and coin rewards
        db.refresh(w_citizen)
        assert w_citizen.conversation_state == "IDLE", "State should remain IDLE, not reset to AWAITING_PHOTO"
        assert w_citizen.eco_coins == 120, "Eco coins should not be awarded twice"

        # Verify message status is COMPLETED
        db.refresh(msg_rec)
        assert msg_rec.status == "COMPLETED"

        # Verify outbound WhatsApp message delivered was the ticket confirmation, NOT ask_photo
        assert len(outbound_messages) >= 1
        last_outbound = outbound_messages[-1]["text"]
        assert original_ticket in last_outbound
        assert "कचऱ्याचा" not in last_outbound and "photo" not in last_outbound.lower()

    finally:
        config.META_APP_SECRET = orig_secret
        if created_complaint_id:
            db.query(DriverTask).filter(DriverTask.complaint_id == created_complaint_id).delete()
            db.query(Complaint).filter(Complaint.id == created_complaint_id).delete()
        db.query(WhatsAppProcessedMessage).filter(WhatsAppProcessedMessage.message_id == msg_id).delete()
        db.query(WhatsAppCitizen).filter(WhatsAppCitizen.phone_number == sender).delete()
        db.commit()
        db.close()
