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
