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
