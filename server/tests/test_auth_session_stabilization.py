"""
Tests for authentication, session stability, /api/my alias, and API contracts.
"""
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from server.main import app
from server.database.db import SessionLocal
from server.models.user import User
from server.models.complaint import Complaint
from server.utils.security import hash_password, create_access_token

client = TestClient(app)


def _create_user(db, email: str, role: str = "citizen", phone: str = "+919876543210") -> User:
    user = User(
        email=email,
        hashed_password=hash_password("Password123!"),
        full_name=f"Test {role.capitalize()}",
        role=role,
        phone=phone,
        is_active=True,
        eco_coins=100
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_header(user: User) -> dict:
    token = create_access_token(data={"sub": user.email, "id": user.id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}


class TestAuthSessionEndpoints:
    """Verifies that /api/auth/me, /api/auth/my, and /api/my all resolve correctly."""

    def test_auth_me_returns_user_profile(self):
        db = SessionLocal()
        try:
            user = _create_user(db, f"user_me_{uuid.uuid4().hex[:6]}@test.com")
            headers = _auth_header(user)

            res = client.get("/api/auth/me", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == user.id
            assert data["email"] == user.email
            assert data["name"] == user.full_name
            assert data["role"] == "citizen"
        finally:
            db.close()

    def test_auth_my_alias_returns_user_profile(self):
        db = SessionLocal()
        try:
            user = _create_user(db, f"user_my_alias_{uuid.uuid4().hex[:6]}@test.com")
            headers = _auth_header(user)

            res = client.get("/api/auth/my", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == user.id
            assert data["email"] == user.email
            assert data["name"] == user.full_name
        finally:
            db.close()

    def test_api_my_root_alias_returns_user_profile(self):
        db = SessionLocal()
        try:
            user = _create_user(db, f"user_api_my_{uuid.uuid4().hex[:6]}@test.com")
            headers = _auth_header(user)

            res = client.get("/api/my", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["id"] == user.id
            assert data["email"] == user.email
            assert data["name"] == user.full_name
        finally:
            db.close()

    def test_api_my_unauthenticated_returns_401(self):
        res = client.get("/api/my")
        assert res.status_code == 401

    def test_api_my_expired_token_returns_401(self):
        db = SessionLocal()
        try:
            user = _create_user(db, f"user_exp_{uuid.uuid4().hex[:6]}@test.com")
            # Create expired token
            expired_token = create_access_token(
                data={"sub": user.email, "id": user.id, "role": user.role},
                expires_delta=timedelta(minutes=-10)
            )
            res = client.get("/api/my", headers={"Authorization": f"Bearer {expired_token}"})
            assert res.status_code == 401
        finally:
            db.close()


class TestRoleBasedAccessControl:
    """Verifies that role boundaries are strictly enforced across endpoints."""

    def test_citizen_denied_admin_endpoints(self):
        db = SessionLocal()
        try:
            citizen = _create_user(db, f"citizen_rbac_{uuid.uuid4().hex[:6]}@test.com", "citizen")
            headers = _auth_header(citizen)

            # /api/admin/drivers requires admin
            res = client.get("/api/admin/drivers", headers=headers)
            assert res.status_code == 403

            # /api/admin/analytics requires admin
            res_analytics = client.get("/api/admin/analytics", headers=headers)
            assert res_analytics.status_code == 403
        finally:
            db.close()

    def test_driver_denied_whatsapp_link_generation(self):
        db = SessionLocal()
        try:
            driver = _create_user(db, f"driver_rbac_{uuid.uuid4().hex[:6]}@test.com", "driver")
            headers = _auth_header(driver)

            res = client.post("/api/whatsapp/link/generate", headers=headers)
            assert res.status_code == 403
        finally:
            db.close()


class TestWhatsAppLinkResponseContracts:
    """Verifies that WhatsApp linking responses contain both expected field names."""

    def test_generate_contract_has_both_code_and_link_code(self):
        db = SessionLocal()
        try:
            citizen = _create_user(db, f"citizen_contract_{uuid.uuid4().hex[:6]}@test.com", "citizen")
            headers = _auth_header(citizen)

            res = client.post("/api/whatsapp/link/generate", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            # Both fields must exist and match for compatibility
            assert "code" in data and data["code"]
            assert "link_code" in data and data["link_code"]
            assert data["code"] == data["link_code"]
            assert data["expires_in"] == 600
            assert "bot_phone" in data
        finally:
            db.close()

    def test_status_contract(self):
        db = SessionLocal()
        try:
            citizen = _create_user(db, f"citizen_status_test_{uuid.uuid4().hex[:6]}@test.com", "citizen")
            headers = _auth_header(citizen)

            res = client.get("/api/whatsapp/link/status", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert "is_linked" in data
            assert data["is_linked"] is False
            assert data["whatsapp_phone"] is None
        finally:
            db.close()


class TestComplaintUserIsolation:
    """Verifies that /api/complaints/my returns only the complaints of the authenticated citizen."""

    def test_complaints_my_returns_only_own_complaints(self):
        db = SessionLocal()
        try:
            user1 = _create_user(db, f"c_user1_{uuid.uuid4().hex[:6]}@test.com", "citizen")
            user2 = _create_user(db, f"c_user2_{uuid.uuid4().hex[:6]}@test.com", "citizen")

            # Create complaint for user1
            c1 = Complaint(
                tracking_number=f"DHL-2026-{uuid.uuid4().hex[:8].upper()}",
                citizen_id=user1.id,
                location_address="Deopur, Dhule",
                latitude=20.9042,
                longitude=74.7749,
                status="Pending",
                waste_type="Mixed Waste",
                ward="Ward 12"
            )
            db.add(c1)
            db.commit()

            # User 1 requests their complaints
            res1 = client.get("/api/complaints/my", headers=_auth_header(user1))
            assert res1.status_code == 200
            complaints1 = res1.json()
            assert any(c["id"] == c1.tracking_number for c in complaints1)

            # User 2 requests their complaints — must not see user 1's complaint
            res2 = client.get("/api/complaints/my", headers=_auth_header(user2))
            assert res2.status_code == 200
            complaints2 = res2.json()
            assert not any(c["id"] == c1.tracking_number for c in complaints2)
        finally:
            db.close()
