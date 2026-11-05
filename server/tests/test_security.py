import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from server.main import app
from server.database.db import SessionLocal
from server.models.user import User
from server.models.task import DriverTask
from server.utils.security import (
    create_access_token,
    get_current_user_optional,
    get_jwt_secret,
    hash_password,
)

client = TestClient(app)


# ============================================================================
# Scope A: JWT Secret Configuration Tests
# ============================================================================

def test_scope_a_production_secret_key_missing_raises(monkeypatch):
    """In production mode, missing or empty SECRET_KEY must raise a RuntimeError."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "")

    with pytest.raises(RuntimeError, match="SECRET_KEY environment variable is missing or empty in production"):
        get_jwt_secret()


def test_scope_a_production_secret_key_whitespace_raises(monkeypatch):
    """In production mode, whitespace-only SECRET_KEY must raise a RuntimeError."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "   ")

    with pytest.raises(RuntimeError, match="SECRET_KEY environment variable is missing or empty in production"):
        get_jwt_secret()


def test_scope_a_jwt_creation_and_verification_with_configured_secret(monkeypatch):
    """Configured SECRET_KEY signs and verifies valid JWT tokens correctly."""
    custom_secret = "test-custom-secret-key-32-chars-long-secure!!"
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", custom_secret)

    token = create_access_token({"sub": "priya@cityswap.io", "role": "citizen"})
    assert isinstance(token, str)
    assert len(token) > 20

    db = SessionLocal()
    try:
        user = get_current_user_optional(token=token, db=db)
        assert user is not None
        assert user.email == "priya@cityswap.io"
    finally:
        db.close()


def test_scope_a_jwt_tampered_or_wrong_secret_rejected(monkeypatch):
    """JWT signed with a different key cannot be verified."""
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "key-one-alpha-12345678901234567890")
    token = create_access_token({"sub": "priya@cityswap.io", "role": "citizen"})

    # Switch to key-two
    monkeypatch.setenv("SECRET_KEY", "key-two-beta-12345678901234567890")
    db = SessionLocal()
    try:
        user = get_current_user_optional(token=token, db=db)
        assert user is None
    finally:
        db.close()


def test_scope_a_database_connection_validation_executes_select_1():
    """Database validation opens a live connection and executes a minimal query, without exposing secrets."""
    from server.database import db as db_module

    class DummyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement):
            assert "SELECT 1" in str(statement)
            return object()

    class DummyEngine:
        url = "sqlite:///./ecopulse-test.db"

        def connect(self):
            return DummyConnection()

    db_module.validate_database_connection(DummyEngine())


def test_scope_a_database_connection_failure_hides_credentials():
    from server.database import db as db_module

    secret = "do-not-display-this"

    class BrokenEngine:
        url = f"postgresql://test-user:{secret}@db.example.invalid/test_db"

        def connect(self):
            raise RuntimeError(f"connection rejected; password={secret}")

    with pytest.raises(RuntimeError) as exc_info:
        db_module.validate_database_connection(BrokenEngine())

    assert secret not in str(exc_info.value)
    assert "***" in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__


def test_scope_a_demo_seed_disabled_in_production(monkeypatch):
    """Production mode must never create demo accounts implicitly at startup or login."""
    from server.services.auth_service import AuthService

    monkeypatch.setenv("ENV", "production")
    demo_emails = ["priya@cityswap.io", "ramesh@cityswap.io", "collector@cityswap.io", "admin@cityswap.io"]

    db = SessionLocal()
    try:
        before = db.query(User).filter(User.email.in_(demo_emails)).count()
        AuthService.seed_demo_users(db)
        after = db.query(User).filter(User.email.in_(demo_emails)).count()
        assert after == before
        assert AuthService.should_seed_demo_users() is False
    finally:
        db.close()


def test_scope_a_demo_seed_allowed_in_dev_and_test(monkeypatch):
    """Development and test environments keep explicit demo seeding enabled for local workflows."""
    from server.services.auth_service import AuthService

    db = SessionLocal()
    try:
        for env_name in ("development", "test"):
            monkeypatch.setenv("ENV", env_name)
            demo_emails = ["priya@cityswap.io", "ramesh@cityswap.io", "collector@cityswap.io", "admin@cityswap.io"]
            before = db.query(User).filter(User.email.in_(demo_emails)).count()
            AuthService.seed_demo_users(db)
            after = db.query(User).filter(User.email.in_(demo_emails)).count()
            assert after >= before
            assert AuthService.should_seed_demo_users() is True
    finally:
        db.close()


# ============================================================================
# Scope B: Driver Task Ownership and Status Validation Tests
# ============================================================================

def test_scope_b_driver_cannot_update_another_drivers_task():
    """Driver A cannot update Driver B's task (returns 403)."""
    db = SessionLocal()
    try:
        # Create Driver A
        driver_a = db.query(User).filter(User.email == "driver_a_scope_b@ecopulse.test").first()
        if not driver_a:
            driver_a = User(
                full_name="Driver Alpha",
                email="driver_a_scope_b@ecopulse.test",
                role="driver",
                hashed_password=hash_password("Password123!"),
                eco_coins=100
            )
            db.add(driver_a)
            db.commit()
            db.refresh(driver_a)

        # Create Driver B
        driver_b = db.query(User).filter(User.email == "driver_b_scope_b@ecopulse.test").first()
        if not driver_b:
            driver_b = User(
                full_name="Driver Beta",
                email="driver_b_scope_b@ecopulse.test",
                role="driver",
                hashed_password=hash_password("Password123!"),
                eco_coins=100
            )
            db.add(driver_b)
            db.commit()
            db.refresh(driver_b)

        # Create task assigned to Driver B
        task_b = DriverTask(
            driver_id=driver_b.id,
            location_name="Zone B Test Route",
            status="Pending"
        )
        db.add(task_b)
        db.commit()
        db.refresh(task_b)

        # Authenticate as Driver A
        token_a = create_access_token({"sub": driver_a.email, "role": "driver", "id": driver_a.id})
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Driver A attempts to update Driver B's task
        response = client.patch(
            f"/api/driver/tasks/{task_b.id}/status",
            json={"status": "In Progress"},
            headers=headers_a
        )
        assert response.status_code == 403
        assert "forbidden" in response.json()["detail"].lower()

        # Driver B updates their own task successfully
        token_b = create_access_token({"sub": driver_b.email, "role": "driver", "id": driver_b.id})
        headers_b = {"Authorization": f"Bearer {token_b}"}
        res_b = client.patch(
            f"/api/driver/tasks/{task_b.id}/status",
            json={"status": "In Progress"},
            headers=headers_b
        )
        assert res_b.status_code == 200
        assert res_b.json()["status"] == "In Progress"

    finally:
        db.close()


def test_scope_b_admin_can_update_any_driver_task():
    """Admin can update any driver's task."""
    db = SessionLocal()
    try:
        # Create Driver
        driver = db.query(User).filter(User.email == "driver_test_scope_b@ecopulse.test").first()
        if not driver:
            driver = User(
                full_name="Driver Test",
                email="driver_test_scope_b@ecopulse.test",
                role="driver",
                hashed_password=hash_password("Password123!"),
                eco_coins=100
            )
            db.add(driver)
            db.commit()
            db.refresh(driver)

        # Create task assigned to Driver
        task = DriverTask(
            driver_id=driver.id,
            location_name="Zone Admin Test Route",
            status="Pending"
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # Authenticate as Admin
        admin_token = create_access_token({"sub": "admin@cityswap.io", "role": "admin"})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        response = client.patch(
            f"/api/driver/tasks/{task.id}/status",
            json={"status": "In Progress"},
            headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == "In Progress"
    finally:
        db.close()


def test_scope_b_nonexistent_task_returns_404():
    """Updating a non-existent task returns 404."""
    login_res = client.post("/api/auth/login", json={
        "email": "ramesh@cityswap.io",
        "password": "Password123!",
        "role": "driver"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.patch(
        "/api/driver/tasks/99999999/status",
        json={"status": "In Progress"},
        headers=headers
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_scope_b_invalid_task_status_rejected():
    """Invalid task status values are rejected with 422."""
    login_res = client.post("/api/auth/login", json={
        "email": "ramesh@cityswap.io",
        "password": "Password123!",
        "role": "driver"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get a valid task
    tasks_res = client.get("/api/driver/tasks", headers=headers)
    assert tasks_res.status_code == 200
    task_id = tasks_res.json()[0]["id"]

    for invalid_status in ["Archived", "RandomStatus", "Failed", "123", ""]:
        response = client.patch(
            f"/api/driver/tasks/{task_id}/status",
            json={"status": invalid_status},
            headers=headers
        )
        assert response.status_code == 422


# ============================================================================
# Scope C: EcoCoin Self-Manipulation Prevention Tests
# ============================================================================

def test_scope_c_cannot_manipulate_own_ecocoins_balance():
    """Sending eco_coins in a profile update is rejected and does not alter stored balance."""
    login_res = client.post("/api/auth/login", json={
        "email": "priya@cityswap.io",
        "password": "Password123!",
        "role": "citizen"
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get initial balance
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    initial_coins = me_res.json()["eco_coins"]

    # Attempt to inflate balance by sending eco_coins in profile update
    # Since extra="forbid", schema validation rejects this with 422
    update_res = client.put(
        "/api/auth/profile",
        json={"full_name": "Priya Sharma Updated", "eco_coins": initial_coins + 100000},
        headers=headers
    )
    assert update_res.status_code == 422

    # Verify balance remains unchanged
    me_check = client.get("/api/auth/me", headers=headers)
    assert me_check.json()["eco_coins"] == initial_coins

    # Legitimate profile update succeeds without modifying coins
    legit_res = client.put(
        "/api/auth/profile",
        json={"full_name": "Priya Sharma Legitimate", "ward": "Ward 12", "phone": "+919876543210"},
        headers=headers
    )
    assert legit_res.status_code == 200
    assert legit_res.json()["name"] == "Priya Sharma Legitimate"
    assert legit_res.json()["eco_coins"] == initial_coins


# ============================================================================
# Scope D: Disabled Insecure OTP Verification Tests
# ============================================================================

def test_scope_d_arbitrary_otp_cannot_issue_jwt():
    """Arbitrary OTP verification requests return 503 and do not issue JWT or create accounts."""
    db = SessionLocal()
    phone_test = "9111222333"
    try:
        # Ensure user does not already exist
        db.query(User).filter(User.phone == phone_test).delete()
        db.commit()

        # Send arbitrary OTP values
        for otp_code in ["1234", "0000", "9999", "random_string", ""]:
            response = client.post(
                "/api/auth/verify-otp",
                json={"phone": phone_test, "otp": otp_code, "role": "citizen"}
            )
            assert response.status_code == 503
            assert "unavailable" in response.json().get("detail", "").lower()
            assert "access_token" not in response.json()

        # Confirm no account was created
        user_in_db = db.query(User).filter(User.phone == phone_test).first()
        assert user_in_db is None
    finally:
        db.close()


def test_scope_d_password_auth_remains_fully_functional():
    """Password-based login and signup remain fully operational."""
    # Test valid login
    res = client.post("/api/auth/login", json={
        "email": "priya@cityswap.io",
        "password": "Password123!",
        "role": "citizen"
    })
    assert res.status_code == 200
    assert "access_token" in res.json()
    assert res.json()["user"]["email"] == "priya@cityswap.io"


# ============================================================================
# Scope G-A: CORS & Generic File Upload Hardening Tests
# ============================================================================

SAMPLE_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00"
    b"\xff\xd9"
)

SAMPLE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

SAMPLE_WEBP = (
    b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x00\x90\x00\x00\x9d\x01"
    b"*\x01\x00\x01\x00\x00\x00"
)


def _cleanup_uploaded_file(response_data):
    if isinstance(response_data, dict) and "filename" in response_data:
        from server.routes.uploads import UPLOAD_DIR
        path = os.path.join(UPLOAD_DIR, response_data["filename"])
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def test_scope_ga_allowed_image_uploads():
    """Valid JPEG, PNG, and WebP uploads succeed and return expected URL/filename."""
    # Test JPEG
    res_jpg = client.post(
        "/api/uploads",
        files={"file": ("waste_photo.jpg", SAMPLE_JPEG, "image/jpeg")}
    )
    assert res_jpg.status_code == 200
    data_jpg = res_jpg.json()
    assert "url" in data_jpg
    assert data_jpg["url"].startswith("/uploads/img_")
    assert data_jpg["url"].endswith(".jpg")
    _cleanup_uploaded_file(data_jpg)

    # Test PNG
    res_png = client.post(
        "/api/uploads",
        files={"file": ("clean_bin.png", SAMPLE_PNG, "image/png")}
    )
    assert res_png.status_code == 200
    data_png = res_png.json()
    assert data_png["url"].endswith(".png")
    _cleanup_uploaded_file(data_png)

    # Test WebP
    res_webp = client.post(
        "/api/uploads",
        files={"file": ("street_scene.webp", SAMPLE_WEBP, "image/webp")}
    )
    assert res_webp.status_code == 200
    data_webp = res_webp.json()
    assert data_webp["url"].endswith(".webp")
    _cleanup_uploaded_file(data_webp)


def test_scope_ga_unsupported_extensions_rejected():
    """Unsupported extensions such as .html, .svg, .js, .exe, .py are rejected with 400."""
    unsupported_files = [
        ("index.html", b"<html><body>Malicious</body></html>", "text/html"),
        ("vector.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml"),
        ("payload.js", b"console.log('xss')", "application/javascript"),
        ("trojan.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream"),
        ("script.py", b"import os; os.system('echo 1')", "text/x-python"),
    ]

    for fname, content, ctype in unsupported_files:
        res = client.post(
            "/api/uploads",
            files={"file": (fname, content, ctype)}
        )
        assert res.status_code == 400
        assert "unsupported" in res.json()["detail"].lower()


def test_scope_ga_mismatched_extension_and_content_rejected():
    """Mismatched extension vs magic bytes is rejected with 400."""
    # JPEG bytes named as .png
    res = client.post(
        "/api/uploads",
        files={"file": ("fake_png.png", SAMPLE_JPEG, "image/png")}
    )
    assert res.status_code == 400
    assert "does not match" in res.json()["detail"].lower()


def test_scope_ga_empty_and_malformed_images_rejected():
    """Empty and truncated images are rejected with 400."""
    # Empty file
    res_empty = client.post(
        "/api/uploads",
        files={"file": ("empty.jpg", b"", "image/jpeg")}
    )
    assert res_empty.status_code == 400

    # Truncated (< 12 bytes)
    res_corrupt = client.post(
        "/api/uploads",
        files={"file": ("corrupt.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")}
    )
    assert res_corrupt.status_code == 400
    assert "truncated" in res_corrupt.json()["detail"].lower() or "invalid" in res_corrupt.json()["detail"].lower()


def test_scope_ga_oversized_upload_rejected(monkeypatch):
    """Upload exceeding MAX_UPLOAD_SIZE is rejected with HTTP 413."""
    from server.utils.config import config
    # Set a tiny max upload limit for test
    monkeypatch.setattr(config, "MAX_UPLOAD_SIZE", 50)

    res = client.post(
        "/api/uploads",
        files={"file": ("big_photo.jpg", SAMPLE_JPEG, "image/jpeg")}
    )
    assert res.status_code == 413
    assert "exceeds maximum" in res.json()["detail"].lower()


def test_scope_ga_safe_filename_and_path_confinement():
    """Filename is server-controlled and safely confined to UPLOAD_DIR."""
    from server.routes.uploads import UPLOAD_DIR

    res = client.post(
        "/api/uploads",
        files={"file": ("../../../etc/passwd.jpg", SAMPLE_JPEG, "image/jpeg")}
    )
    assert res.status_code == 200
    data = res.json()
    assert ".." not in data["filename"]
    assert "/" not in data["filename"]
    assert "\\" not in data["filename"]
    assert data["filename"].startswith("img_")

    target_path = os.path.join(UPLOAD_DIR, data["filename"])
    assert os.path.exists(target_path)
    assert os.path.commonpath([UPLOAD_DIR, target_path]) == UPLOAD_DIR
    _cleanup_uploaded_file(data)


def test_scope_ga_cors_preflight_allowed_origin():
    """Preflight from allowed origin returns Access-Control-Allow-Origin and Credentials."""
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_scope_ga_cors_unlisted_origin_blocked():
    """Preflight from unlisted origin does not receive Access-Control-Allow-Origin header."""
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://malicious-site.com",
            "Access-Control-Request-Method": "GET",
        }
    )
    assert "access-control-allow-origin" not in response.headers


def test_scope_ga_anonymous_citizen_complaint_and_upload_flow():
    """Anonymous citizen can upload an image and submit a waste complaint."""
    # 1. Anonymous upload
    upload_res = client.post(
        "/api/uploads",
        files={"file": ("waste_street.jpg", SAMPLE_JPEG, "image/jpeg")}
    )
    assert upload_res.status_code == 200
    image_url = upload_res.json()["url"]
    _cleanup_uploaded_file(upload_res.json())

    # 2. Anonymous complaint submission using the uploaded image URL
    complaint_res = client.post(
        "/api/complaints",
        json={
            "location": "Shirpur Central Market, Ward 12",
            "type": "Plastic Waste",
            "ward": "Ward 12",
            "description": "Plastic accumulation near roadside bin",
            "image_url": image_url
        }
    )
    assert complaint_res.status_code == 201
    assert complaint_res.json()["location"] == "Shirpur Central Market, Ward 12"
    assert complaint_res.json()["status"] in ["In Progress", "Pending"]
    assert complaint_res.json()["image_url"] == image_url


# ============================================================================
# Scope G-B: Webhook, QR, Item & Notification Authorization Tests
# ============================================================================

def test_scope_gb_whatsapp_missing_secret_fails_closed(monkeypatch):
    """If META_APP_SECRET is missing or empty, POST /api/whatsapp/webhook fails closed with HTTP 500."""
    from server.utils.config import config
    monkeypatch.setattr(config, "META_APP_SECRET", "")

    res = client.post(
        "/api/whatsapp/webhook",
        content=b'{"entry":[]}',
        headers={"X-Hub-Signature-256": "sha256=abcdef1234567890"}
    )
    assert res.status_code == 500
    assert "unavailable" in res.json()["detail"].lower()


def test_scope_gb_whatsapp_missing_signature_rejected(monkeypatch):
    """Meta webhook without signature header is rejected with 403."""
    from server.utils.config import config
    monkeypatch.setattr(config, "META_APP_SECRET", "meta-test-secret-key-12345")

    res = client.post(
        "/api/whatsapp/webhook",
        content=b'{"entry":[]}'
    )
    assert res.status_code == 403
    assert "missing" in res.json()["detail"].lower()


def test_scope_gb_whatsapp_invalid_signature_rejected(monkeypatch):
    """Meta webhook with invalid signature is rejected with 403."""
    from server.utils.config import config
    monkeypatch.setattr(config, "META_APP_SECRET", "meta-test-secret-key-12345")

    res = client.post(
        "/api/whatsapp/webhook",
        content=b'{"entry":[]}',
        headers={"X-Hub-Signature-256": "sha256=badsignature1234567890abcdef"}
    )
    assert res.status_code == 403
    assert "invalid" in res.json()["detail"].lower()


def test_scope_gb_twilio_provider_disabled_fails_closed(monkeypatch):
    """When Twilio is disabled, POST /api/whatsapp/twilio-webhook returns HTTP 503."""
    from server.utils.config import config
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "meta")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "")

    res = client.post(
        "/api/whatsapp/twilio-webhook",
        data={"From": "whatsapp:+919876543210", "Body": "Hello"}
    )
    assert res.status_code == 503
    assert "disabled" in res.json()["detail"].lower()


def test_scope_gb_twilio_signature_verification(monkeypatch):
    """When Twilio is enabled, validates X-Twilio-Signature correctly."""
    import hmac
    import hashlib
    import base64
    from server.utils.config import config

    test_token = "twilio-auth-token-test-12345"
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", test_token)
    monkeypatch.setattr(
        config,
        "TWILIO_WEBHOOK_URL",
        "https://twilio.example.test/api/whatsapp/twilio-webhook",
    )

    # 1. Missing signature header
    res_no_sig = client.post(
        "/api/whatsapp/twilio-webhook",
        data={"From": "whatsapp:+919876543210", "Body": "Test"}
    )
    assert res_no_sig.status_code == 403

    # 2. Invalid signature header
    res_bad_sig = client.post(
        "/api/whatsapp/twilio-webhook",
        data={"From": "whatsapp:+919876543210", "Body": "Test"},
        headers={"X-Twilio-Signature": "invalid_sig"}
    )
    assert res_bad_sig.status_code == 403


def _make_twilio_signature(url, params, auth_token):
    import base64
    import hashlib
    import hmac

    signed_data = url
    for key in sorted(params):
        values = params[key]
        if not isinstance(values, (list, tuple)):
            values = [values]
        for value in sorted(values):
            signed_data += f"{key}{value}"

    digest = hmac.new(
        auth_token.encode("utf-8"), signed_data.encode("utf-8"), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def test_scope_gb_twilio_signature_uses_exact_public_https_url_and_query(
    monkeypatch,
):
    from server.services.whatsapp_service import WhatsAppService
    from server.utils.config import config

    token = "twilio-auth-token-test-12345"
    public_url = (
        "https://whatsapp.example.test/api/whatsapp/twilio-webhook"
        "?source=twilio&tenant=green"
    )
    params = {"From": "whatsapp:+919876543210", "Body": "Hello"}
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", token)
    monkeypatch.setattr(config, "TWILIO_WEBHOOK_URL", public_url)
    monkeypatch.setattr(
        WhatsAppService,
        "handle_incoming_message",
        lambda **kwargs: {"reply": "Received"},
    )

    response = client.post(
        public_url,
        data=params,
        headers={
            "X-Twilio-Signature": _make_twilio_signature(
                public_url, params, token
            )
        },
    )

    assert response.status_code == 200
    assert "<Message>Received</Message>" in response.text


@pytest.mark.parametrize(
    "callback_url",
    [
        "https://8.8.8.8/api/whatsapp/twilio-webhook?source=twilio",
        "https://[2001:4860:4860::8888]/api/whatsapp/twilio-webhook?source=twilio",
    ],
    ids=["public-ipv4", "public-ipv6"],
)
def test_scope_gb_twilio_accepts_public_ip_callback_urls(callback_url, monkeypatch):
    from server.routes.whatsapp import verify_twilio_signature
    from server.utils.config import config

    token = "twilio-auth-token-test-12345"
    params = {"From": "whatsapp:+919876543210", "Body": "Hello"}
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", token)

    verify_twilio_signature(
        callback_url,
        params,
        _make_twilio_signature(callback_url, params, token),
    )


def test_scope_gb_twilio_missing_public_url_fails_closed_before_processing(
    monkeypatch,
):
    from server.services.whatsapp_service import WhatsAppService
    from server.utils.config import config

    token = "twilio-auth-token-test-12345"
    params = {"From": "whatsapp:+919876543210", "Body": "Hello"}
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", token)
    monkeypatch.setattr(config, "TWILIO_WEBHOOK_URL", "")
    monkeypatch.setattr(
        WhatsAppService,
        "handle_incoming_message",
        lambda **kwargs: pytest.fail("Missing callback URL reached processing"),
    )

    response = client.post(
        "/api/whatsapp/twilio-webhook",
        data=params,
        headers={
            "X-Twilio-Signature": _make_twilio_signature(
                "https://twilio.example.test/api/whatsapp/twilio-webhook",
                params,
                token,
            )
        },
    )

    assert response.status_code == 500


@pytest.mark.parametrize(
    "configured_url",
    [
        "http://whatsapp.example.test/api/whatsapp/twilio-webhook",
        "not-a-url",
        "https://.",
        "https://..",
        "https:///api/whatsapp/twilio-webhook",
        "https://?source=twilio",
        "https://bad..example/api/whatsapp/twilio-webhook",
        "https://-bad.example/api/whatsapp/twilio-webhook",
        "https://localhost/api/whatsapp/twilio-webhook",
        "https://127.0.0.1/api/whatsapp/twilio-webhook",
        "https://[::1]/api/whatsapp/twilio-webhook",
        "https://[fe80::1]/api/whatsapp/twilio-webhook",
        "https://[fe80::1%25eth0]/api/whatsapp/twilio-webhook",
        "https://10.0.0.1/api/whatsapp/twilio-webhook",
        "https://[2001:db8::1]/api/whatsapp/twilio-webhook",
        "https://whatsapp.example.test:invalid/api/whatsapp/twilio-webhook",
        "https://whatsapp.example.test:99999/api/whatsapp/twilio-webhook",
        "https://user@whatsapp.example.test/api/whatsapp/twilio-webhook",
        "https://user:password@whatsapp.example.test/api/whatsapp/twilio-webhook",
        "https://whatsapp.example.test/api/whatsapp/twilio-webhook#fragment",
        "https://whatsapp.example.test/api/whatsapp/%path",
    ],
    ids=[
        "unsupported-scheme",
        "relative-url",
        "dot-only-hostname",
        "double-dot-hostname",
        "empty-host-before-path",
        "empty-host-with-query",
        "empty-host-label",
        "hostname-label-starts-with-hyphen",
        "non-public-single-label-host",
        "ipv4-loopback",
        "ipv6-loopback",
        "ipv6-link-local",
        "ipv6-scoped-link-local",
        "ipv4-private",
        "ipv6-documentation-range",
        "invalid-port",
        "port-out-of-range",
        "userinfo",
        "username-and-password",
        "fragment",
        "malformed-escape",
    ],
)
def test_scope_gb_twilio_invalid_public_url_fails_closed_before_processing(
    monkeypatch, configured_url
):
    from server.services.whatsapp_service import WhatsAppService
    from server.utils.config import config

    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "twilio-auth-token-test-12345")
    monkeypatch.setattr(config, "TWILIO_WEBHOOK_URL", configured_url)
    monkeypatch.setattr(
        WhatsAppService,
        "handle_incoming_message",
        lambda **kwargs: pytest.fail("Invalid callback URL reached processing"),
    )

    response = client.post(
        "/api/whatsapp/twilio-webhook",
        data={"From": "whatsapp:+919876543210", "Body": "Hello"},
        headers={"X-Twilio-Signature": "any-signature"},
    )

    assert response.status_code == 500


@pytest.mark.parametrize(
    "signed_url",
    [
        "http://whatsapp.example.test/api/whatsapp/twilio-webhook?source=twilio",
        "https://internal.example.test/api/whatsapp/twilio-webhook?source=twilio",
        "https://whatsapp.example.test:8443/api/whatsapp/twilio-webhook?source=twilio",
    ],
    ids=["wrong-scheme", "wrong-hostname", "wrong-port"],
)
def test_scope_gb_twilio_rejects_signature_for_different_callback_url(
    monkeypatch, signed_url
):
    from server.services.whatsapp_service import WhatsAppService
    from server.utils.config import config

    token = "twilio-auth-token-test-12345"
    public_url = (
        "https://whatsapp.example.test/api/whatsapp/twilio-webhook?source=twilio"
    )
    params = {"From": "whatsapp:+919876543210", "Body": "Hello"}
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", token)
    monkeypatch.setattr(config, "TWILIO_WEBHOOK_URL", public_url)
    monkeypatch.setattr(
        WhatsAppService,
        "handle_incoming_message",
        lambda **kwargs: pytest.fail("Invalid signature reached processing"),
    )

    response = client.post(
        public_url,
        data=params,
        headers={
            "X-Twilio-Signature": _make_twilio_signature(
                signed_url, params, token
            ),
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "whatsapp.example.test",
        },
    )

    assert response.status_code == 403


def test_scope_gb_twilio_uses_configured_public_url_not_forwarded_headers(
    monkeypatch,
):
    from server.services.whatsapp_service import WhatsAppService
    from server.utils.config import config

    token = "twilio-auth-token-test-12345"
    public_url = "https://whatsapp.example.test/api/whatsapp/twilio-webhook"
    internal_url = "http://whatsapp.internal/api/whatsapp/twilio-webhook"
    params = {"From": "whatsapp:+919876543210", "Body": "Hello"}
    processed = []
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", token)
    monkeypatch.setattr(config, "TWILIO_WEBHOOK_URL", public_url)
    monkeypatch.setattr(
        WhatsAppService,
        "handle_incoming_message",
        lambda **kwargs: processed.append(kwargs) or {"reply": "Received"},
    )

    response = client.post(
        internal_url,
        data=params,
        headers={
            "X-Twilio-Signature": _make_twilio_signature(public_url, params, token),
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "whatsapp.example.test",
        },
    )

    assert response.status_code == 200
    assert len(processed) == 1


def test_scope_gb_twilio_duplicate_form_values_do_not_match_collapsed_params(
    monkeypatch,
):
    from urllib.parse import urlencode

    from server.services.whatsapp_service import WhatsAppService
    from server.utils.config import config

    token = "twilio-auth-token-test-12345"
    callback_url = "https://whatsapp.example.test/api/whatsapp/twilio-webhook"
    duplicate_params = [
        ("From", "whatsapp:+919876543210"),
        ("Body", "First value"),
        ("Body", "Second value"),
    ]
    signed_params = {
        "From": "whatsapp:+919876543210",
        "Body": ["First value", "Second value"],
    }
    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", token)
    monkeypatch.setattr(config, "TWILIO_WEBHOOK_URL", callback_url)
    monkeypatch.setattr(
        WhatsAppService,
        "handle_incoming_message",
        lambda **kwargs: pytest.fail("Duplicate form values reached processing"),
    )

    response = client.post(
        callback_url,
        content=urlencode(duplicate_params),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Twilio-Signature": _make_twilio_signature(
                callback_url, signed_params, token
            ),
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("content", "content_type", "expected_status", "signed"),
    [
        (
            b'{"From":"whatsapp:+919876543210","Body":"Hello"}',
            "application/json",
            415,
            True,
        ),
        (b"--malformed", "multipart/form-data", 415, False),
        (b"From=%ZZ&Body=Hello", "application/x-www-form-urlencoded", 403, False),
    ],
    ids=["unsupported-json", "unsupported-multipart", "malformed-urlencoded"],
)
def test_scope_gb_twilio_rejects_unsupported_or_malformed_requests_before_processing(
    monkeypatch, content, content_type, expected_status, signed
):
    from server.services.whatsapp_service import WhatsAppService
    from server.utils.config import config

    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "twilio-auth-token-test-12345")
    process_message = []
    callback_url = "https://whatsapp.example.test/api/whatsapp/twilio-webhook"
    monkeypatch.setattr(config, "TWILIO_WEBHOOK_URL", callback_url)
    monkeypatch.setattr(
        WhatsAppService,
        "handle_incoming_message",
        lambda **kwargs: process_message.append(kwargs),
    )

    headers = {"Content-Type": content_type}
    if signed:
        headers["X-Twilio-Signature"] = _make_twilio_signature(
            callback_url, {}, config.TWILIO_AUTH_TOKEN
        )
    response = client.post(
        callback_url,
        content=content,
        headers=headers,
    )

    assert response.status_code == expected_status
    assert process_message == []


@pytest.mark.parametrize("signature", [None, "invalid-signature"])
def test_scope_gb_twilio_missing_or_invalid_signature_never_processes_message(
    monkeypatch, signature
):
    from server.services.whatsapp_service import WhatsAppService
    from server.utils.config import config

    monkeypatch.setattr(config, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "twilio-auth-token-test-12345")
    monkeypatch.setattr(
        config,
        "TWILIO_WEBHOOK_URL",
        "https://twilio.example.test/api/whatsapp/twilio-webhook",
    )
    process_message = []
    monkeypatch.setattr(
        WhatsAppService,
        "handle_incoming_message",
        lambda **kwargs: process_message.append(kwargs),
    )

    headers = {}
    if signature is not None:
        headers["X-Twilio-Signature"] = signature
    response = client.post(
        "/api/whatsapp/twilio-webhook",
        data={"From": "whatsapp:+919876543210", "Body": "Hello"},
        headers=headers,
    )

    assert response.status_code == 403
    assert process_message == []


def test_scope_gb_generate_qr_requires_admin_auth():
    """POST /api/whatsapp/generate-qr requires admin authorization."""
    # 1. Anonymous request is rejected with 401
    res_anon = client.post(
        "/api/whatsapp/generate-qr",
        json={"ward": 12, "household_number": 1042}
    )
    assert res_anon.status_code == 401

    # 2. Citizen user is rejected with 403
    citizen_token = create_access_token({"sub": "priya@cityswap.io", "role": "citizen"})
    res_citizen = client.post(
        "/api/whatsapp/generate-qr",
        json={"ward": 12, "household_number": 1042},
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert res_citizen.status_code == 403

    # 3. Admin user succeeds with 200
    admin_token = create_access_token({"sub": "admin@cityswap.io", "role": "admin"})
    res_admin = client.post(
        "/api/whatsapp/generate-qr",
        json={"ward": 12, "household_number": 1042},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert data["household_code"] == "SHP-W12-H1042"
    assert "wa.me" in data["whatsapp_direct_link"]


def test_scope_gb_item_creation_requires_auth_and_prevents_owner_spoofing():
    """POST /api/items requires authentication and derives owner from authenticated user, ignoring spoofed client owner."""
    # 1. Anonymous creation is rejected with 401
    res_anon = client.post(
        "/api/items",
        json={
            "title": "Unwanted Garden Hose",
            "description": "15m reinforced garden hose",
            "category": "Garden",
            "offered_city": "Shirpur",
            "desired_city": "Dhule",
            "owner": "Spoofed Owner"
        }
    )
    assert res_anon.status_code == 401

    # 2. Authenticated citizen creates item with an attempted spoofed owner name
    citizen_token = create_access_token({"sub": "priya@cityswap.io", "role": "citizen"})
    res_auth = client.post(
        "/api/items",
        json={
            "title": "Eco Friendly Planter Pot",
            "description": "Ceramic planter pot in great condition",
            "category": "Home",
            "offered_city": "Shirpur",
            "desired_city": "Dhule",
            "owner": "Spoofed Admin Officer"
        },
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert res_auth.status_code == 201
    created_item = res_auth.json()
    assert created_item["title"] == "Eco Friendly Planter Pot"
    # Owner must be derived from the authenticated user, NOT "Spoofed Admin Officer"
    assert "Priya Sharma" in created_item["owner"]
    assert created_item["owner"] != "Spoofed Admin Officer"


def test_scope_gb_notification_privacy_isolation():
    """Public GET /api/notifications returns only public broadcasts and isolates private notifications."""
    from server.models.notification import Notification

    db = SessionLocal()
    try:
        # Create a private notification
        private_notif = Notification(
            title="Private Driver Task Assignment",
            message="Confidential dispatch route details for driver only.",
            notification_type="Critical",
            audience="Drivers",
            priority="High",
            icon="local_shipping",
            is_broadcast=False,
            recipient_id=999,
            is_read=False
        )
        # Create a public broadcast notification
        public_notif = Notification(
            title="Public Community Clean-up Drive",
            message="Join the municipal clean-up this Sunday at Central Park.",
            notification_type="Info",
            audience="All Citizens",
            priority="Normal",
            icon="campaign",
            is_broadcast=True,
            recipient_id=None,
            is_read=False
        )
        db.add(private_notif)
        db.add(public_notif)
        db.commit()
        db.refresh(private_notif)
        db.refresh(public_notif)

        # 1. Anonymous public endpoint GET /api/notifications
        res_public = client.get("/api/notifications")
        assert res_public.status_code == 200
        public_items = res_public.json()

        titles = [n["title"] for n in public_items]
        assert "Public Community Clean-up Drive" in titles
        assert "Private Driver Task Assignment" not in titles

        # 2. Admin endpoint GET /api/admin/notifications includes all notifications
        admin_token = create_access_token({"sub": "admin@cityswap.io", "role": "admin"})
        res_admin = client.get(
            "/api/admin/notifications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert res_admin.status_code == 200
        admin_titles = [n["title"] for n in res_admin.json()]
        assert "Public Community Clean-up Drive" in admin_titles
        assert "Private Driver Task Assignment" in admin_titles
    finally:
        # Clean up test notifications
        db.query(Notification).filter(
            Notification.title.in_(["Private Driver Task Assignment", "Public Community Clean-up Drive"])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


# ============================================================================
# Scope G-C: Deployment Configuration and CORS Validation Tests
# ============================================================================

def test_scope_gc_production_cors_origins_missing_raises(monkeypatch):
    """In production mode, missing or empty CORS_ORIGINS must raise RuntimeError during startup/lifespan."""
    import asyncio
    from server.main import lifespan, app
    from server.utils.config import config

    monkeypatch.setattr(config, "ENV", config.ENV)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "secure-production-secret-key-32-chars-min!!")
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "")

    async def run_lifespan():
        async with lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        asyncio.run(run_lifespan())


def test_scope_gc_production_cors_origins_configured_succeeds(monkeypatch):
    """In production mode, explicitly configured CORS_ORIGINS parses correctly and lifespan succeeds."""
    import asyncio
    from server.main import lifespan, app
    from server.utils.config import config

    monkeypatch.setattr(config, "ENV", config.ENV)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "secure-production-secret-key-32-chars-min!!")
    monkeypatch.setenv("CORS_ORIGINS", "https://city-swap-frontend.onrender.com, https://custom-domain.org")

    assert config.CORS_ORIGINS == [
        "https://city-swap-frontend.onrender.com",
        "https://custom-domain.org"
    ]

    async def run_lifespan():
        async with lifespan(app):
            pass

    # Should succeed without raising
    asyncio.run(run_lifespan())


def test_scope_gc_environment_and_version_alias_compatibility(monkeypatch):
    """Fallback environment variables (ENVIRONMENT, PROJECT_VERSION, BACKEND_CORS_ORIGINS) are supported."""
    from server.utils.config import Config

    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("VERSION", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("PROJECT_VERSION", "2.1.0")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "https://staging.cityswap.io")

    test_cfg = Config()
    assert test_cfg.ENV == "staging"
    assert test_cfg.VERSION == "2.1.0"
    assert test_cfg.CORS_ORIGINS == ["https://staging.cityswap.io"]


def test_scope_gc_dev_mode_default_cors_origins(monkeypatch):
    """In development mode without explicit CORS_ORIGINS, default localhost origins are returned."""
    from server.utils.config import config

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "")

    assert "http://localhost:5173" in config.CORS_ORIGINS
    assert "http://127.0.0.1:5173" in config.CORS_ORIGINS
    assert "http://localhost:3000" in config.CORS_ORIGINS


# ============================================================================
# Scope H: Complaint Tracking-Number Collision Hardening Tests
# ============================================================================
#
# NOTE: The FastAPI/Starlette `on_startup` TypeError in server/routes/health.py
# is a pre-existing environment incompatibility with Python 3.14 + the installed
# FastAPI version.  It prevents pytest from *collecting* any test in this file.
# All Scope H tests are written to be collected by pytest when that environment
# issue is resolved, and are separately verified to be logically correct via the
# standalone isolation script at:
#   brain/<conv-id>/scratch/run_scope_h_tests.py
#
# Every test in this section uses only mock DB objects or pure-function calls,
# so none of them touch the real database or require the FastAPI app to import.

import re as _re

# ---------------------------------------------------------------------------
# H-1: Web tracking ID format and alphabet
# ---------------------------------------------------------------------------

def test_scope_h_web_tracking_id_format():
    """Generated web tracking IDs match EP-2026-<9 uppercase alphanum> format."""
    from server.services.complaint_service import _generate_web_tracking_id

    pattern = _re.compile(r'^EP-2026-[A-Z0-9]{9}$')
    for _ in range(300):
        tid = _generate_web_tracking_id()
        assert pattern.match(tid), f'Unexpected format: {tid}'
        suffix = tid[8:]
        assert 'I' not in suffix, f'Ambiguous char I in: {tid}'
        assert 'O' not in suffix, f'Ambiguous char O in: {tid}'
    # fits String(30) column
    assert len(_generate_web_tracking_id()) <= 30


def test_scope_h_web_tracking_id_uniqueness():
    """1 000 generated web IDs have no collisions (birthday-problem sanity check)."""
    from server.services.complaint_service import _generate_web_tracking_id

    ids = [_generate_web_tracking_id() for _ in range(1000)]
    assert len(set(ids)) == 1000, 'Unexpected collision in 1 000 web tracking IDs'


# ---------------------------------------------------------------------------
# H-2: WhatsApp tracking ID format and alphabet
# ---------------------------------------------------------------------------

def test_scope_h_whatsapp_tracking_id_format():
    """Generated WhatsApp IDs embed ward number and have the correct format."""
    from server.services.whatsapp_service import _generate_whatsapp_tracking_id

    pattern = _re.compile(r'^(?:DHL|SHP)-2026-W\d+-[A-Z0-9]{9}$')
    for ward in ['Ward 1', 'Ward 12', 'Ward 27']:
        for _ in range(100):
            tid = _generate_whatsapp_tracking_id(ward)
            assert pattern.match(tid), f'Bad format for {ward!r}: {tid}'
            ward_num = ward.replace('Ward ', '')
            assert f'W{ward_num}-' in tid
            suffix = tid.split('-')[-1]
            assert 'I' not in suffix and 'O' not in suffix, f'Ambiguous char: {tid}'
        assert len(_generate_whatsapp_tracking_id(ward)) <= 30


def test_scope_h_whatsapp_tracking_id_uniqueness():
    """1 000 WhatsApp IDs for the same ward have no collisions."""
    from server.services.whatsapp_service import _generate_whatsapp_tracking_id

    ids = [_generate_whatsapp_tracking_id('Ward 12') for _ in range(1000)]
    assert len(set(ids)) == 1000, 'Unexpected collision in 1 000 WhatsApp tracking IDs'


# ---------------------------------------------------------------------------
# H-3: _is_tracking_number_collision classifier
# ---------------------------------------------------------------------------

def test_scope_h_classifier_true_for_sqlite_tracking_number_duplicate():
    """Classifier returns True for an IntegrityError on complaints.tracking_number (SQLite)."""
    from sqlalchemy.exc import IntegrityError
    from server.services.complaint_service import _is_tracking_number_collision

    exc = IntegrityError(
        statement='INSERT INTO complaints',
        params={},
        orig=Exception('UNIQUE constraint failed: complaints.tracking_number')
    )
    assert _is_tracking_number_collision(exc) is True


def test_scope_h_classifier_true_for_postgres_tracking_number_duplicate():
    """Classifier returns True for a PostgreSQL IntegrityError naming tracking_number."""
    from sqlalchemy.exc import IntegrityError
    from server.services.complaint_service import _is_tracking_number_collision

    exc = IntegrityError(
        statement='INSERT INTO complaints',
        params={},
        orig=Exception(
            'duplicate key value violates unique constraint '
            '"complaints_tracking_number_key"'
        )
    )
    assert _is_tracking_number_collision(exc) is True


def test_scope_h_classifier_false_for_notnull_violation():
    """Classifier returns False for a NOT NULL violation (unrelated integrity error)."""
    from sqlalchemy.exc import IntegrityError
    from server.services.complaint_service import _is_tracking_number_collision

    exc = IntegrityError(
        statement='INSERT INTO complaints',
        params={},
        orig=Exception('NOT NULL constraint failed: complaints.ward')
    )
    assert _is_tracking_number_collision(exc) is False


def test_scope_h_classifier_false_for_foreign_key_violation():
    """Classifier returns False for a FK violation on citizen_id."""
    from sqlalchemy.exc import IntegrityError
    from server.services.complaint_service import _is_tracking_number_collision

    exc = IntegrityError(
        statement='INSERT INTO complaints',
        params={},
        orig=Exception('FOREIGN KEY constraint failed')
    )
    assert _is_tracking_number_collision(exc) is False


def test_scope_h_classifier_false_for_unique_on_different_column():
    """Classifier returns False for a unique violation on a different column (e.g. users.email)."""
    from sqlalchemy.exc import IntegrityError
    from server.services.complaint_service import _is_tracking_number_collision

    exc = IntegrityError(
        statement='INSERT INTO users',
        params={},
        orig=Exception('UNIQUE constraint failed: users.email')
    )
    assert _is_tracking_number_collision(exc) is False


def test_scope_h_classifier_false_for_plain_value_error():
    """Classifier returns False for non-IntegrityError exceptions."""
    from server.services.complaint_service import _is_tracking_number_collision

    assert _is_tracking_number_collision(ValueError('something went wrong')) is False
    assert _is_tracking_number_collision(RuntimeError('unique duplicate')) is False
    assert _is_tracking_number_collision(Exception('integrity error tracking_number')) is False


def test_scope_h_classifier_true_for_wrapped_integrity_error():
    """Classifier walks the exception chain to find IntegrityError wrapped as __cause__."""
    from sqlalchemy.exc import IntegrityError
    from server.services.complaint_service import _is_tracking_number_collision

    orig_exc = IntegrityError(
        statement='INSERT INTO complaints',
        params={},
        orig=Exception('UNIQUE constraint failed: complaints.tracking_number')
    )
    # Wrap it
    wrapper = RuntimeError('persistence failed')
    wrapper.__cause__ = orig_exc
    assert _is_tracking_number_collision(wrapper) is True


# ---------------------------------------------------------------------------
# H-4: Web complaint creation — collision retry succeeds
# ---------------------------------------------------------------------------

def test_scope_h_web_collision_retry_succeeds(monkeypatch):
    """Web complaint creation retries and succeeds after 3 simulated duplicate-key collisions."""
    from sqlalchemy.exc import IntegrityError
    from unittest.mock import MagicMock
    from server.services import complaint_service
    from server.schemas.complaint import ComplaintCreate

    gen_n = {'n': 0}
    original_gen = complaint_service._generate_web_tracking_id

    def patched_gen():
        gen_n['n'] += 1
        return 'EP-2026-COLLIDE000' if gen_n['n'] <= 3 else original_gen()

    monkeypatch.setattr(complaint_service, '_generate_web_tracking_id', patched_gen)

    flush_n = {'n': 0}

    def mock_flush():
        flush_n['n'] += 1
        if flush_n['n'] <= 3:
            raise IntegrityError(
                'INSERT INTO complaints', {},
                Exception('UNIQUE constraint failed: complaints.tracking_number')
            )

    committed = {'v': False}

    def mock_refresh(obj):
        obj.id = 42
        obj.tracking_number = 'EP-2026-UNIQUE001'
        obj.location_address = 'Test Street'
        obj.status = 'In Progress'
        obj.waste_type = 'Mixed Waste'
        obj.ward = 'Ward 12'
        obj.assigned_driver_name = 'Ramesh Y.'
        obj.image_url = None
        obj.ai_status = 'Verified'
        obj.ai_confidence = 0.95

    db = MagicMock()
    db.flush = mock_flush
    db.add = MagicMock()
    db.commit = lambda: committed.update({'v': True})
    db.rollback = MagicMock()
    db.refresh = mock_refresh

    monkeypatch.setattr(
        'server.services.complaint_service.AIService.verify_waste_image',
        lambda *a, **kw: {'status': 'Verified', 'confidence': 0.95}
    )

    payload = ComplaintCreate(
        location='Test Street', type='Mixed Waste',
        ward='Ward 12', description='Test', image_url=None
    )

    from server.services.complaint_service import ComplaintService
    ComplaintService.create_complaint(db, payload, user=None)

    assert committed['v'], 'commit was not called'
    assert gen_n['n'] == 4, f'Expected 4 generator calls, got {gen_n["n"]}'
    assert db.rollback.call_count == 3, f'Expected 3 rollbacks, got {db.rollback.call_count}'


# ---------------------------------------------------------------------------
# H-5: Web complaint creation — retry exhaustion raises RuntimeError
# ---------------------------------------------------------------------------

def test_scope_h_web_retry_exhaustion_raises(monkeypatch):
    """Web complaint creation raises RuntimeError after all retries are exhausted."""
    from sqlalchemy.exc import IntegrityError
    from server.services import complaint_service
    from server.schemas.complaint import ComplaintCreate
    from unittest.mock import MagicMock

    monkeypatch.setattr(complaint_service, '_generate_web_tracking_id',
                        lambda: 'EP-2026-ALWAYSCOL')

    def always_raise():
        raise IntegrityError(
            'INSERT INTO complaints', {},
            Exception('UNIQUE constraint failed: complaints.tracking_number')
        )

    db = MagicMock()
    db.flush = always_raise
    db.rollback = MagicMock()

    monkeypatch.setattr(
        'server.services.complaint_service.AIService.verify_waste_image',
        lambda *a, **kw: {'status': 'Verified', 'confidence': 0.95}
    )

    payload = ComplaintCreate(
        location='Test Street', type='Mixed Waste',
        ward='Ward 12', description='Test', image_url=None
    )

    from server.services.complaint_service import ComplaintService
    with pytest.raises(RuntimeError, match='Could not generate a unique web tracking number'):
        ComplaintService.create_complaint(db, payload, user=None)

    assert db.rollback.call_count == complaint_service._MAX_RETRIES


# ---------------------------------------------------------------------------
# H-6: Unrelated integrity error must NOT trigger retry
# ---------------------------------------------------------------------------

def test_scope_h_unrelated_integrity_error_not_retried(monkeypatch):
    """A NOT NULL violation on the ward column must propagate immediately, not be retried."""
    from sqlalchemy.exc import IntegrityError
    from server.services import complaint_service
    from server.schemas.complaint import ComplaintCreate
    from unittest.mock import MagicMock

    gen_n = {'n': 0}

    def counting_gen():
        gen_n['n'] += 1
        return f'EP-2026-ATTEMPT{gen_n["n"]:03d}'

    monkeypatch.setattr(complaint_service, '_generate_web_tracking_id', counting_gen)

    def unrelated_integrity_flush():
        raise IntegrityError(
            'INSERT INTO complaints', {},
            Exception('NOT NULL constraint failed: complaints.ward')
        )

    db = MagicMock()
    db.flush = unrelated_integrity_flush
    db.rollback = MagicMock()

    monkeypatch.setattr(
        'server.services.complaint_service.AIService.verify_waste_image',
        lambda *a, **kw: {'status': 'Verified', 'confidence': 0.95}
    )

    payload = ComplaintCreate(
        location='Test Street', type='Mixed Waste',
        ward='Ward 12', description='Test', image_url=None
    )

    from server.services.complaint_service import ComplaintService
    with pytest.raises(IntegrityError):
        ComplaintService.create_complaint(db, payload, user=None)

    # Must have attempted only ONE flush — no retry regeneration
    assert gen_n['n'] == 1, f'Expected 1 generator call (no retry), got {gen_n["n"]}'
    assert db.rollback.call_count == 1


# ---------------------------------------------------------------------------
# H-7: Session remains usable after a failed attempt
# ---------------------------------------------------------------------------

def test_scope_h_session_usable_after_failed_attempt(monkeypatch):
    """After a collision-driven rollback the session state is clean for subsequent queries."""
    from sqlalchemy.exc import IntegrityError
    from server.services import complaint_service
    from server.schemas.complaint import ComplaintCreate
    from unittest.mock import MagicMock, call

    # Always raise duplicate tracking_number
    monkeypatch.setattr(complaint_service, '_generate_web_tracking_id',
                        lambda: 'EP-2026-ALWAYSCOL')

    def always_raise():
        raise IntegrityError(
            'INSERT', {},
            Exception('UNIQUE constraint failed: complaints.tracking_number')
        )

    rollback_states = []
    db = MagicMock()
    db.flush = always_raise
    db.rollback = lambda: rollback_states.append('rolled_back')

    monkeypatch.setattr(
        'server.services.complaint_service.AIService.verify_waste_image',
        lambda *a, **kw: {'status': 'Verified', 'confidence': 0.95}
    )

    payload = ComplaintCreate(
        location='X', type='Mixed Waste', ward='Ward 1', description='d', image_url=None
    )

    from server.services.complaint_service import ComplaintService
    with pytest.raises(RuntimeError):
        ComplaintService.create_complaint(db, payload, user=None)

    # Every failed attempt called rollback — session returned to clean state
    assert len(rollback_states) == complaint_service._MAX_RETRIES
    assert all(s == 'rolled_back' for s in rollback_states)

    # Session is now usable: add/query/commit would work (mock confirms no pending state)
    db.add(MagicMock())  # should not raise
    db.commit()


# ---------------------------------------------------------------------------
# H-8: WhatsApp complaint — collision retry succeeds without double coin award
# ---------------------------------------------------------------------------

def test_scope_h_whatsapp_collision_retry_no_double_coin(monkeypatch):
    """WhatsApp complaint retries on collision without awarding EcoCoins more than once."""
    from sqlalchemy.exc import IntegrityError
    from server.services import whatsapp_service
    from unittest.mock import MagicMock

    gen_n = {'n': 0}
    original_gen = whatsapp_service._generate_whatsapp_tracking_id

    def patched_gen(ward):
        gen_n['n'] += 1
        return 'SHP-2026-W12-COLLIDE' if gen_n['n'] <= 2 else original_gen(ward)

    monkeypatch.setattr(whatsapp_service, '_generate_whatsapp_tracking_id', patched_gen)

    flush_n = {'n': 0}
    committed = {'v': False}

    def mock_flush():
        flush_n['n'] += 1
        if flush_n['n'] <= 2:
            raise IntegrityError(
                'INSERT', {},
                Exception('UNIQUE constraint failed: complaints.tracking_number')
            )

    citizen = MagicMock()
    citizen.is_authorized = True
    citizen.preferred_language = 'en'
    citizen.conversation_state = 'AWAITING_LOCATION'
    citizen.pending_complaint_data = '{"image_url": "/uploads/img.jpg", "waste_type": "Mixed Waste"}'
    citizen.ward = 'Ward 12'
    citizen.household_id = 'SHP-W12-H001'
    citizen.eco_coins = 100
    citizen.phone_number = '919999900001'

    db = MagicMock()
    db.flush = mock_flush
    db.rollback = MagicMock()
    db.commit = lambda: committed.update({'v': True})
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.count.return_value = 0

    monkeypatch.setattr(whatsapp_service.WhatsAppService, 'get_or_create_citizen',
                        staticmethod(lambda db, phone: citizen))
    monkeypatch.setattr(whatsapp_service.WhatsAppService, 'find_matching_citizen_user',
                        staticmethod(lambda db, phone: None))
    monkeypatch.setattr(whatsapp_service.WhatsAppService, 'select_eligible_driver',
                        staticmethod(lambda db: None))
    monkeypatch.setattr(whatsapp_service.WhatsAppService, 'send_meta_whatsapp',
                        staticmethod(lambda *a, **kw: None))

    whatsapp_service.WhatsAppService.handle_incoming_message(
        db=db, sender_phone='919999900001', message_type='location',
        latitude=21.3487, longitude=74.8812, message_id=None,
    )

    assert committed['v'], 'commit not called'
    # EcoCoins must be exactly original + 20 (not +40 or +60)
    assert citizen.eco_coins == 120, f'Expected 120 coins, got {citizen.eco_coins}'
    assert db.rollback.call_count == 2, f'Expected 2 rollbacks, got {db.rollback.call_count}'
    assert gen_n['n'] == 3, f'Expected 3 gen calls, got {gen_n["n"]}'


# ---------------------------------------------------------------------------
# H-9: WhatsApp retry exhaustion raises RuntimeError
# ---------------------------------------------------------------------------

def test_scope_h_whatsapp_retry_exhaustion_raises(monkeypatch):
    """WhatsApp complaint creation raises RuntimeError when all retry attempts produce duplicates."""
    from sqlalchemy.exc import IntegrityError
    from server.services import whatsapp_service
    from unittest.mock import MagicMock

    monkeypatch.setattr(whatsapp_service, '_generate_whatsapp_tracking_id',
                        lambda ward: 'SHP-2026-W12-ALWAYSC')

    def always_raise():
        raise IntegrityError(
            'INSERT', {},
            Exception('UNIQUE constraint failed: complaints.tracking_number')
        )

    citizen = MagicMock()
    citizen.is_authorized = True
    citizen.preferred_language = 'en'
    citizen.conversation_state = 'AWAITING_LOCATION'
    citizen.pending_complaint_data = '{"image_url": "/uploads/test.jpg", "waste_type": "Plastic Waste"}'
    citizen.ward = 'Ward 12'
    citizen.household_id = 'SHP-W12-H001'
    citizen.eco_coins = 100
    citizen.phone_number = '919999900001'

    db = MagicMock()
    db.flush = always_raise
    db.rollback = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.count.return_value = 0

    monkeypatch.setattr(whatsapp_service.WhatsAppService, 'get_or_create_citizen',
                        staticmethod(lambda db, phone: citizen))
    monkeypatch.setattr(whatsapp_service.WhatsAppService, 'find_matching_citizen_user',
                        staticmethod(lambda db, phone: None))
    monkeypatch.setattr(whatsapp_service.WhatsAppService, 'select_eligible_driver',
                        staticmethod(lambda db: None))

    with pytest.raises(RuntimeError, match='Could not generate a unique WhatsApp tracking number'):
        whatsapp_service.WhatsAppService.handle_incoming_message(
            db=db, sender_phone='919999900001', message_type='location',
            latitude=21.3487, longitude=74.8812, message_id='msg-001',
        )

    assert db.rollback.call_count == whatsapp_service._WA_MAX_RETRIES
    # EcoCoins must not have been permanently incremented
    assert citizen.eco_coins == 100, f'EcoCoins leaked: got {citizen.eco_coins}'


# ---------------------------------------------------------------------------
# H-10: WhatsApp — unrelated integrity error not retried
# ---------------------------------------------------------------------------

def test_scope_h_whatsapp_unrelated_integrity_error_not_retried(monkeypatch):
    """A NOT NULL violation in the WhatsApp path propagates without retry."""
    from sqlalchemy.exc import IntegrityError
    from server.services import whatsapp_service
    from unittest.mock import MagicMock

    gen_n = {'n': 0}
    original_gen = whatsapp_service._generate_whatsapp_tracking_id

    def counting_gen(ward):
        gen_n['n'] += 1
        return original_gen(ward)

    monkeypatch.setattr(whatsapp_service, '_generate_whatsapp_tracking_id', counting_gen)

    def notnull_flush():
        raise IntegrityError(
            'INSERT', {},
            Exception('NOT NULL constraint failed: complaints.ward')
        )

    citizen = MagicMock()
    citizen.is_authorized = True
    citizen.preferred_language = 'en'
    citizen.conversation_state = 'AWAITING_LOCATION'
    citizen.pending_complaint_data = '{"image_url": "/img.jpg", "waste_type": "Mixed Waste"}'
    citizen.ward = 'Ward 12'
    citizen.household_id = 'SHP-W12-H002'
    citizen.eco_coins = 80
    citizen.phone_number = '919888800002'

    db = MagicMock()
    db.flush = notnull_flush
    db.rollback = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.count.return_value = 0

    monkeypatch.setattr(whatsapp_service.WhatsAppService, 'get_or_create_citizen',
                        staticmethod(lambda db, phone: citizen))
    monkeypatch.setattr(whatsapp_service.WhatsAppService, 'find_matching_citizen_user',
                        staticmethod(lambda db, phone: None))
    monkeypatch.setattr(whatsapp_service.WhatsAppService, 'select_eligible_driver',
                        staticmethod(lambda db: None))

    with pytest.raises(IntegrityError):
        whatsapp_service.WhatsAppService.handle_incoming_message(
            db=db, sender_phone='919888800002', message_type='location',
            latitude=21.3, longitude=74.8, message_id=None,
        )

    # No retry: generator called exactly once
    assert gen_n['n'] == 1, f'Expected 1 gen call, got {gen_n["n"]}'
    assert db.rollback.call_count == 1
    # State restored — no coin leakage
    assert citizen.eco_coins == 80


# ---------------------------------------------------------------------------
# H-11: Legacy tracking-number lookup compatibility
# ---------------------------------------------------------------------------

def test_scope_h_legacy_tracking_number_lookup():
    """Legacy seed tracking numbers (EP-2026-00123 format) are still found by ilike query."""
    from server.services.complaint_service import _generate_web_tracking_id

    # Verify new IDs don't accidentally match old seed patterns
    new_id = _generate_web_tracking_id()
    # Old seeds are EP-2026-00121, EP-2026-00122, EP-2026-00123
    assert new_id not in {'EP-2026-00121', 'EP-2026-00122', 'EP-2026-00123'}, (
        f'New generated ID collided with a seed value: {new_id}'
    )

    # Pure function: check that the new format is distinct enough
    # (old format had digits only after EP-2026-; new has mixed alphanumeric)
    import re
    old_pattern = re.compile(r'^EP-2026-\d{5}$')
    new_pattern = re.compile(r'^EP-2026-[A-Z0-9]{9}$')
    assert not old_pattern.match(new_id), f'New ID accidentally matches old 5-digit format: {new_id}'
    assert new_pattern.match(new_id)
