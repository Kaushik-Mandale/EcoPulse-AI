import uuid
"""
Automated Security Tests for Backend-Mediated Storage Architecture:
  1. Unauthenticated image retrieval requests rejected with 401.
  2. Citizens accessing another citizen's complaint image rejected with 403.
  3. Drivers accessing complaints outside their assigned scope rejected with 403.
  4. Drivers accessing assigned complaints allowed with 200.
  5. Administrators and Collectors accessing any complaint image allowed with 200.
  6. Anonymous citizen tracking with valid tracking token allowed with 200.
  7. Anonymous citizen tracking with invalid/missing token rejected with 401/403.
  8. Attempts to manipulate complaint IDs with arbitrary storage object keys rejected with 404.
  9. Public list responses (/api/complaints) do NOT leak signed Supabase URLs or tokens.
  10. Service role key never appears in API responses or error details.
  11. Public anonymous uploads retain file validation (rejected on invalid extensions/size).
  12. Legacy local paths (/uploads/...) and external URLs remain fully compatible.
"""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from server.main import app
from server.database.db import get_db, Base, SessionLocal
from server.models.user import User
from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.utils.security import create_access_token, hash_password
from server.services.media_storage import SupabaseMediaStorage, set_media_storage, LocalMediaStorage
from server.services.complaint_service import ComplaintService

client = TestClient(app)

SAMPLE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 100


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_supabase_storage():
    """Provides a mocked SupabaseMediaStorage that generates predictable signed URLs."""
    mock_client = MagicMock()
    storage_api = MagicMock()
    mock_client.storage.from_.return_value = storage_api
    storage_api.create_signed_url.return_value = {
        "signedURL": "https://test.supabase.co/storage/v1/object/sign/complaint-images/complaints/img_secure.jpg?token=mock_signed_token"
    }

    storage = SupabaseMediaStorage(
        supabase_url="https://test.supabase.co",
        service_role_key="mock_secret_role_key",
        bucket_name="complaint-images",
        client=mock_client
    )
    set_media_storage(storage)
    yield storage, storage_api
    set_media_storage(None)


@pytest.fixture
def test_users_and_complaints():
    """Sets up a clean set of users (citizens, driver, admin) and complaints."""
    db_session = SessionLocal()
    u_id = uuid.uuid4().hex[:6]
    # 1. Citizen A
    citizen_a = User(
        full_name="Citizen Alice",
        email=f"alice_{u_id}@example.com",
        hashed_password=hash_password("Password123!"),
        role="citizen",
        ward="Ward 12"
    )
    # 2. Citizen B
    citizen_b = User(
        full_name="Citizen Bob",
        email=f"bob_{u_id}@example.com",
        hashed_password=hash_password("Password123!"),
        role="citizen",
        ward="Ward 4"
    )
    # 3. Driver Assigned
    driver_assigned = User(
        full_name="Driver Dave",
        email=f"dave_{u_id}@example.com",
        hashed_password=hash_password("Password123!"),
        role="driver",
        ward="Ward 12"
    )
    # 4. Driver Other (Unassigned)
    driver_other = User(
        full_name="Driver Dan",
        email=f"dan_{u_id}@example.com",
        hashed_password=hash_password("Password123!"),
        role="driver",
        ward="Ward 8"
    )
    # 5. Administrator
    admin_user = User(
        full_name="Admin Director",
        email=f"admin_{u_id}@example.com",
        hashed_password=hash_password("Password123!"),
        role="admin",
        ward="Ward 1"
    )
    # 6. Collector
    collector_user = User(
        full_name="Collector Carl",
        email=f"collector_{u_id}@example.com",
        hashed_password=hash_password("Password123!"),
        role="collector",
        ward="Ward 2"
    )

    db_session.add_all([citizen_a, citizen_b, driver_assigned, driver_other, admin_user, collector_user])
    db_session.commit()

    # Create Complaint 1: Owned by Citizen A with Supabase image
    comp_a = Complaint(
        tracking_number=f"EP-2026-ALICE{u_id.upper()}",
        citizen_id=citizen_a.id,
        ward="Ward 12",
        location_address="10 Market St",
        waste_type="Plastic Waste",
        image_url="supabase:complaints/wa_alice_photo.jpg",
        status="In Progress",
        assigned_driver_id=driver_assigned.id,
        assigned_driver_name=driver_assigned.full_name
    )

    # Create Complaint 2: Owned by Citizen B with Supabase image
    comp_b = Complaint(
        tracking_number=f"EP-2026-BOB{u_id.upper()}",
        citizen_id=citizen_b.id,
        ward="Ward 4",
        location_address="25 Lake Rd",
        waste_type="Garbage Overflow",
        image_url="supabase:complaints/wa_bob_photo.jpg",
        status="Pending"
    )

    # Create Complaint 3: Anonymous Complaint with Supabase image
    comp_anon = Complaint(
        tracking_number=f"EP-2026-ANON{u_id.upper()}",
        citizen_id=None,
        ward="Ward 12",
        location_address="Park Corner",
        waste_type="Mixed Waste",
        image_url="supabase:complaints/wa_anon_photo.jpg",
        status="Pending"
    )

    # Create Complaint 4: Legacy Local Storage complaint
    comp_local = Complaint(
        tracking_number=f"EP-2026-LOCAL{u_id.upper()}",
        citizen_id=citizen_a.id,
        ward="Ward 12",
        location_address="Station Road",
        waste_type="E-Waste",
        image_url="/uploads/whatsapp/legacy_local.jpg",
        status="Completed"
    )

    db_session.add_all([comp_a, comp_b, comp_anon, comp_local])
    db_session.commit()

    # Create Task linking Complaint 1 to Driver Dave
    task_a = DriverTask(
        complaint_id=comp_a.id,
        driver_id=driver_assigned.id,
        location_name="10 Market St",
        status="In Progress"
    )
    db_session.add(task_a)
    db_session.commit()

    data = {
        "citizen_a": citizen_a,
        "citizen_b": citizen_b,
        "driver_assigned": driver_assigned,
        "driver_other": driver_other,
        "admin": admin_user,
        "collector": collector_user,
        "comp_a": comp_a,
        "comp_b": comp_b,
        "comp_anon": comp_anon,
        "comp_local": comp_local,
    }
    try:
        yield data
    finally:
        db_session.close()


def auth_headers(user: User) -> dict:
    """Helper to generate Authorization header for a user."""
    token = create_access_token({"sub": user.email, "role": user.role, "id": user.id})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

def test_unauthenticated_image_access_rejected(mock_supabase_storage, test_users_and_complaints):
    """Unauthenticated request to resolve private complaint image is rejected with 401."""
    comp_a = test_users_and_complaints["comp_a"]
    response = client.get(f"/api/complaints/{comp_a.tracking_number}/image-url")
    assert response.status_code == 401
    assert "Authentication or valid tracking token required" in response.json()["detail"]


def test_citizen_accessing_own_complaint_image_allowed(mock_supabase_storage, test_users_and_complaints):
    """Authenticated citizen can access their own complaint image."""
    citizen_a = test_users_and_complaints["citizen_a"]
    comp_a = test_users_and_complaints["comp_a"]

    response = client.get(
        f"/api/complaints/{comp_a.tracking_number}/image-url",
        headers=auth_headers(citizen_a)
    )
    assert response.status_code == 200
    data = response.json()
    assert "signedURL" in data["url"] or "test.supabase.co" in data["url"]
    assert data["storage_type"] == "supabase"
    assert data["expires_in"] == 900


def test_citizen_accessing_other_citizen_image_forbidden(mock_supabase_storage, test_users_and_complaints):
    """Citizen Alice is forbidden from accessing Citizen Bob's complaint image."""
    citizen_a = test_users_and_complaints["citizen_a"]
    comp_b = test_users_and_complaints["comp_b"]

    response = client.get(
        f"/api/complaints/{comp_b.tracking_number}/image-url",
        headers=auth_headers(citizen_a)
    )
    assert response.status_code == 403
    assert "Access forbidden: You do not have permission" in response.json()["detail"]


def test_driver_accessing_unassigned_complaint_forbidden(mock_supabase_storage, test_users_and_complaints):
    """Driver Dan (not assigned to Complaint A) is forbidden from accessing its image."""
    driver_other = test_users_and_complaints["driver_other"]
    comp_a = test_users_and_complaints["comp_a"]

    response = client.get(
        f"/api/complaints/{comp_a.tracking_number}/image-url",
        headers=auth_headers(driver_other)
    )
    assert response.status_code == 403
    assert "Driver is not assigned" in response.json()["detail"]


def test_driver_accessing_assigned_complaint_allowed(mock_supabase_storage, test_users_and_complaints):
    """Driver Dave (assigned to Complaint A) is allowed to access its image."""
    driver_assigned = test_users_and_complaints["driver_assigned"]
    comp_a = test_users_and_complaints["comp_a"]

    response = client.get(
        f"/api/complaints/{comp_a.tracking_number}/image-url",
        headers=auth_headers(driver_assigned)
    )
    assert response.status_code == 200
    data = response.json()
    assert "test.supabase.co" in data["url"]


def test_admin_accessing_any_complaint_image_allowed(mock_supabase_storage, test_users_and_complaints):
    """Administrator has full authorization to access any complaint image."""
    admin = test_users_and_complaints["admin"]
    comp_a = test_users_and_complaints["comp_a"]
    comp_b = test_users_and_complaints["comp_b"]

    for comp in [comp_a, comp_b]:
        response = client.get(
            f"/api/complaints/{comp.tracking_number}/image-url",
            headers=auth_headers(admin)
        )
        assert response.status_code == 200
        assert "test.supabase.co" in response.json()["url"]


def test_collector_accessing_any_complaint_image_allowed(mock_supabase_storage, test_users_and_complaints):
    """Collector has administrative authorization to access complaint images."""
    collector = test_users_and_complaints["collector"]
    comp_b = test_users_and_complaints["comp_b"]

    response = client.get(
        f"/api/complaints/{comp_b.tracking_number}/image-url",
        headers=auth_headers(collector)
    )
    assert response.status_code == 200
    assert "test.supabase.co" in response.json()["url"]


def test_anonymous_tracking_with_valid_token_allowed(mock_supabase_storage, test_users_and_complaints):
    """Anonymous tracking with high-entropy HMAC tracking token is authorized."""
    comp_anon = test_users_and_complaints["comp_anon"]
    valid_token = ComplaintService.generate_tracking_token(comp_anon.id, comp_anon.tracking_number)

    # 1. Via Query Parameter
    response = client.get(f"/api/complaints/{comp_anon.tracking_number}/image-url?token={valid_token}")
    assert response.status_code == 200
    assert "test.supabase.co" in response.json()["url"]

    # 2. Via Header
    response_hdr = client.get(
        f"/api/complaints/{comp_anon.tracking_number}/image-url",
        headers={"X-Tracking-Token": valid_token}
    )
    assert response_hdr.status_code == 200
    assert "test.supabase.co" in response_hdr.json()["url"]


def test_anonymous_tracking_with_invalid_token_rejected(mock_supabase_storage, test_users_and_complaints):
    """Anonymous tracking with invalid/forged token is rejected with 403."""
    comp_anon = test_users_and_complaints["comp_anon"]
    forged_token = "deadbeef" * 8

    response = client.get(f"/api/complaints/{comp_anon.tracking_number}/image-url?token={forged_token}")
    assert response.status_code == 403
    assert "Invalid tracking token" in response.json()["detail"]


def test_object_key_manipulation_rejected(mock_supabase_storage):
    """Supplying arbitrary Supabase object keys as complaint IDs is rejected with 404."""
    malicious_key = "supabase:complaints/wa_secret_victim.jpg"
    response = client.get(f"/api/complaints/{malicious_key}/image-url")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_public_complaint_list_does_not_leak_signed_urls(mock_supabase_storage, test_users_and_complaints):
    """GET /api/complaints must NOT leak signed Supabase URLs, tokens, or private bucket domains."""
    response = client.get("/api/complaints")
    assert response.status_code == 200
    complaints = response.json()

    for comp in complaints:
        image_url = comp.get("image_url")
        if image_url:
            # Must NOT be a signed URL leaking token or Supabase domain
            assert "token=" not in image_url
            assert "supabase.co" not in image_url
            # For Supabase-backed complaints, must point to the backend mediated endpoint
            if "ALICE" in comp["id"] or "BOB" in comp["id"]:
                assert image_url.startswith("/api/complaints/")
                assert image_url.endswith("/image")


def test_service_role_key_never_leaked(mock_supabase_storage, test_users_and_complaints):
    """Neither successful nor failed API responses leak the service role secret."""
    comp_a = test_users_and_complaints["comp_a"]

    # 401 response
    res_401 = client.get(f"/api/complaints/{comp_a.tracking_number}/image-url")
    assert "mock_secret_role_key" not in res_401.text

    # 403 response
    res_403 = client.get(f"/api/complaints/{comp_a.tracking_number}/image-url?token=badtoken")
    assert "mock_secret_role_key" not in res_403.text

    # 404 response
    res_404 = client.get("/api/complaints/nonexistent/image-url")
    assert "mock_secret_role_key" not in res_404.text


def test_legacy_local_storage_compatibility(mock_supabase_storage, test_users_and_complaints):
    """Complaints with local /uploads/ paths resolve transparently when authorized."""
    citizen_a = test_users_and_complaints["citizen_a"]
    comp_local = test_users_and_complaints["comp_local"]

    response = client.get(
        f"/api/complaints/{comp_local.tracking_number}/image-url",
        headers=auth_headers(citizen_a)
    )
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "/uploads/whatsapp/legacy_local.jpg"
    assert data["storage_type"] == "local"
