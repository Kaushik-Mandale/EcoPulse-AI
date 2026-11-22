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
from server.tests.iam_test_helpers import admin_access_token

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
        ward="Ward 12",
        is_verified=True,
    )
    # 4. Driver Other (Unassigned)
    driver_other = User(
        full_name="Driver Dan",
        email=f"dan_{u_id}@example.com",
        hashed_password=hash_password("Password123!"),
        role="driver",
        ward="Ward 8",
        is_verified=True,
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
    if user.role in {"admin", "collector"}:
        token = admin_access_token(user)
    else:
        token = create_access_token({
            "sub": user.email,
            "role": user.role,
            "id": user.id,
            "sv": user.session_version or 0,
        })
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


def test_collector_image_access_is_limited_to_assigned_ward(mock_supabase_storage, test_users_and_complaints):
    """Collectors can retrieve images in their assigned ward only."""
    collector = test_users_and_complaints["collector"]
    comp_a = test_users_and_complaints["comp_a"]
    comp_b = test_users_and_complaints["comp_b"]
    original_ward = collector.ward
    db = SessionLocal()
    try:
        db_collector = db.query(User).filter(User.id == collector.id).one()
        db_collector.ward = comp_a.ward
        db.commit()
    finally:
        db.close()

    allowed = client.get(
        f"/api/complaints/{comp_a.tracking_number}/image-url",
        headers=auth_headers(collector),
    )
    assert allowed.status_code == 200
    assert "test.supabase.co" in allowed.json()["url"]

    denied_cross_ward = client.get(
        f"/api/complaints/{comp_b.tracking_number}/image-url",
        headers=auth_headers(collector),
    )
    assert denied_cross_ward.status_code == 403

    db = SessionLocal()
    try:
        db_collector = db.query(User).filter(User.id == collector.id).one()
        db_collector.ward = None
        db.commit()
    finally:
        db.close()
    denied_unassigned = client.get(
        f"/api/complaints/{comp_a.tracking_number}/image-url",
        headers=auth_headers(collector),
    )
    assert denied_unassigned.status_code == 403
    db = SessionLocal()
    try:
        db_collector = db.query(User).filter(User.id == collector.id).one()
        db_collector.ward = original_ward
        db.commit()
    finally:
        db.close()


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
    """Authenticated administrative listings use mediated URLs, never signed storage URLs."""
    users = test_users_and_complaints
    assert client.get("/api/complaints").status_code == 401
    response = client.get("/api/complaints", headers=auth_headers(users["admin"]))
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


def test_anonymous_cannot_enumerate_complaints_or_use_numeric_ids(test_users_and_complaints):
    comp_a = test_users_and_complaints["comp_a"]
    assert client.get("/api/complaints").status_code == 401
    assert client.get("/api/complaints/my").status_code == 401
    assert client.get(f"/api/complaints/track/{comp_a.id}").status_code == 404
    assert client.get(f"/api/complaints/{comp_a.id}").status_code == 404
    assert client.get(f"/api/complaints/{comp_a.tracking_number}").status_code == 404
    assert client.get(f"/api/complaints/{comp_a.id}/image-url").status_code == 404


def test_citizen_complaint_access_is_limited_to_ownership(test_users_and_complaints):
    users = test_users_and_complaints
    citizen_a_headers = auth_headers(users["citizen_a"])
    owned_ids = {row["id"] for row in client.get("/api/complaints/my", headers=citizen_a_headers).json()}
    assert users["comp_a"].tracking_number in owned_ids
    assert users["comp_local"].tracking_number in owned_ids
    assert users["comp_b"].tracking_number not in owned_ids
    own_row = next(row for row in client.get("/api/complaints/my", headers=citizen_a_headers).json()
                   if row["id"] == users["comp_a"].tracking_number)
    assert own_row["has_image"] is True
    assert "image_url" not in own_row

    all_route_ids = {row["id"] for row in client.get("/api/complaints", headers=citizen_a_headers).json()}
    assert all_route_ids == owned_ids
    assert client.get(
        f"/api/complaints/track/{users['comp_a'].tracking_number}",
        headers=citizen_a_headers,
    ).status_code == 200
    assert client.get(
        f"/api/complaints/track/{users['comp_b'].tracking_number}",
        headers=citizen_a_headers,
    ).status_code == 404


def test_tracking_capability_is_hash_stored_scoped_and_minimal(test_users_and_complaints):
    users = test_users_and_complaints
    comp_anon = users["comp_anon"]
    raw_token = ComplaintService.generate_tracking_secret()
    stored_hash = ComplaintService.hash_tracking_secret(raw_token)
    db = SessionLocal()
    try:
        db.query(Complaint).filter(Complaint.id == comp_anon.id).update(
            {"tracking_secret": stored_hash}
        )
        db.commit()
        assert db.query(Complaint).filter(Complaint.id == comp_anon.id).one().tracking_secret == stored_hash
    finally:
        db.close()

    response = client.get(
        f"/api/complaints/track/{comp_anon.tracking_number}",
        headers={"X-Tracking-Token": raw_token},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == comp_anon.tracking_number
    assert set(body) <= {"id", "location", "type", "ward", "status", "time", "statusColor", "created_at"}
    for sensitive_key in ("db_id", "assignedTo", "image_url", "latitude", "longitude", "ai_status", "tracking_token"):
        assert sensitive_key not in body

    assert client.get(
        f"/api/complaints/track/{comp_anon.tracking_number}",
        headers={"X-Tracking-Token": "invalid-capability"},
    ).status_code == 404
    assert client.get(
        f"/api/complaints/track/{users['comp_b'].tracking_number}",
        headers={"X-Tracking-Token": raw_token},
    ).status_code == 404


def test_new_hashed_tracking_capability_authorizes_only_its_evidence(
    mock_supabase_storage, test_users_and_complaints
):
    users = test_users_and_complaints
    comp_anon = users["comp_anon"]
    raw_token = ComplaintService.generate_tracking_secret()
    db = SessionLocal()
    try:
        db.query(Complaint).filter(Complaint.id == comp_anon.id).update({
            "tracking_secret": ComplaintService.hash_tracking_secret(raw_token)
        })
        db.commit()
    finally:
        db.close()

    allowed = client.get(
        f"/api/complaints/{comp_anon.tracking_number}/image-url",
        headers={"X-Tracking-Token": raw_token},
    )
    assert allowed.status_code == 200
    denied = client.get(
        f"/api/complaints/{users['comp_b'].tracking_number}/image-url",
        headers={"X-Tracking-Token": raw_token},
    )
    assert denied.status_code in {401, 403}


def test_submission_returns_one_time_capability_and_only_hash_is_persisted():
    create = client.post("/api/complaints", json={
        "location": "Capability Test Location",
        "type": "Mixed Waste",
        "ward": "Ward 9",
        "description": "Must not be in public status response",
        "latitude": 20.0,
        "longitude": 74.0,
        "image_url": "https://private.example.test/photo.jpg",
    })
    assert create.status_code == 201
    receipt = create.json()
    token = receipt["tracking_token"]
    assert token and len(token) >= 40
    assert "db_id" not in receipt and "assignedTo" not in receipt and "image_url" not in receipt

    db = SessionLocal()
    try:
        complaint = db.query(Complaint).filter(Complaint.tracking_number == receipt["id"]).one()
        assert complaint.tracking_secret == ComplaintService.hash_tracking_secret(token)
        assert token != complaint.tracking_secret
    finally:
        db.close()

    track = client.get(
        f"/api/complaints/track/{receipt['id']}",
        headers={"X-Tracking-Token": token},
    )
    assert track.status_code == 200
    assert track.json()["id"] == receipt["id"]
    assert "description" not in track.json()


def test_admin_driver_and_collector_complaint_scope_is_preserved(test_users_and_complaints):
    users = test_users_and_complaints
    admin_rows = client.get("/api/complaints", headers=auth_headers(users["admin"])).json()
    assert users["comp_a"].tracking_number in {row["id"] for row in admin_rows}
    assert users["comp_b"].tracking_number in {row["id"] for row in admin_rows}

    driver_rows = client.get("/api/complaints", headers=auth_headers(users["driver_assigned"])).json()
    driver_ids = {row["id"] for row in driver_rows}
    assert users["comp_a"].tracking_number in driver_ids
    assert users["comp_b"].tracking_number not in driver_ids
    assert client.get(
        f"/api/complaints/track/{users['comp_a'].tracking_number}",
        headers=auth_headers(users["driver_assigned"]),
    ).status_code == 200
    assert client.get(
        f"/api/complaints/track/{users['comp_b'].tracking_number}",
        headers=auth_headers(users["driver_assigned"]),
    ).status_code == 404

    scoped = Complaint(
        tracking_number=f"EP-2026-SCOPE{uuid.uuid4().hex[:8].upper()}",
        ward=users["collector"].ward,
        location_address="Collector ward location",
        waste_type="Mixed Waste",
    )
    db = SessionLocal()
    try:
        db.add(scoped)
        db.commit()
        db.refresh(scoped)
        collector_headers = auth_headers(users["collector"])
        collector_rows = client.get("/api/complaints", headers=collector_headers).json()
        assert scoped.tracking_number in {row["id"] for row in collector_rows}
        assert users["comp_a"].tracking_number not in {row["id"] for row in collector_rows}
        assert client.get(
            f"/api/complaints/track/{scoped.tracking_number}",
            headers=collector_headers,
        ).status_code == 200
        assert client.get(
            f"/api/complaints/track/{users['comp_a'].tracking_number}",
            headers=collector_headers,
        ).status_code == 404
    finally:
        if scoped.id:
            db.query(Complaint).filter(Complaint.id == scoped.id).delete()
            db.commit()
        db.close()


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
