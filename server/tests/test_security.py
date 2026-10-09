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
