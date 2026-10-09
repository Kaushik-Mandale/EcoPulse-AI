from fastapi.testclient import TestClient
from server.main import app
from server.services.auth_service import AuthService
from server.database.db import SessionLocal

client = TestClient(app)


def get_admin_token():
    db = SessionLocal()
    try:
        # Ensure demo users are seeded
        AuthService.seed_demo_users(db)
    finally:
        db.close()
    
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@cityswap.io", "password": "Password123!", "role": "admin"}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


def test_admin_metrics():
    token = get_admin_token()
    response = client.get("/api/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "total_complaints" in data
    assert "resolution_rate" in data
    assert "top_wards" in data


def test_admin_drivers_crud():
    token = get_admin_token()
    # List drivers
    response = client.get("/api/admin/drivers", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    drivers = response.json()
    assert isinstance(drivers, list)

    # Register driver
    import uuid
    uid = uuid.uuid4().hex[:8]
    rand_email = f"testdriver_{uid}@cityswap.io"
    new_driver = {
        "full_name": "Test Driver",
        "email": rand_email,
        "phone": f"9{uuid.uuid4().int % 1000000000:09d}",
        "employee_id": f"EMP-TEST-{uid}",
        "ward": "Ward 12",
        "password": "Password123!"
    }
    create_res = client.post("/api/admin/drivers", json=new_driver, headers={"Authorization": f"Bearer {token}"})
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["email"] == rand_email

    # Toggle status
    driver_id = created_data["id"]
    status_res = client.patch(
        f"/api/admin/drivers/{driver_id}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert status_res.status_code == 200
    assert status_res.json()["is_active"] is False


def test_admin_bins_telemetry():
    token = get_admin_token()
    response = client.get("/api/admin/bins", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "total_bins" in data
    assert "bins" in data
    assert len(data["bins"]) > 0

    # Update bin fill
    bin_id = data["bins"][0]["id"]
    patch_res = client.patch(
        f"/api/admin/bins/{bin_id}",
        json={"fill_level_pct": 50},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["fill_level_pct"] == 50


def test_admin_analytics():
    token = get_admin_token()
    response = client.get("/api/admin/analytics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "resolution_rate" in data
    assert "ward_breakdown" in data
    assert "monthly_trends" in data


def test_admin_notifications_and_broadcast():
    token = get_admin_token()
    # List notifications
    response = client.get("/api/admin/notifications", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    notifs = response.json()
    assert isinstance(notifs, list)

    # Send broadcast
    broadcast_data = {
        "title": "Emergency Weather Alert",
        "message": "Heavy rain expected in Ward 4, clear all drainage bins immediately.",
        "audience": "All Drivers (Active Shift)",
        "priority": "Emergency (Override Silent Mode)"
    }
    b_res = client.post("/api/admin/notifications/broadcast", json=broadcast_data, headers={"Authorization": f"Bearer {token}"})
    assert b_res.status_code == 201
    assert b_res.json()["title"] == "Emergency Weather Alert"
