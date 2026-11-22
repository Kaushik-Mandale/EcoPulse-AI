from fastapi.testclient import TestClient
from server.main import app
from server.services.auth_service import AuthService
from server.database.db import SessionLocal
from server.models.user import User
from server.tests.iam_test_helpers import login_admin

client = TestClient(app)


def get_admin_token():
    db = SessionLocal()
    try:
        AuthService.seed_demo_users(db)
        admin = db.query(User).filter(User.email == "admin@cityswap.io").first()
        assert admin is not None
        response = login_admin(client, admin, "Password123!")
        db.commit()
    finally:
        db.close()
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
    assert create_res.status_code == 410
    assert "activation_token" not in create_res.json()
    assert "#token=" not in create_res.text


def test_admin_bins_telemetry():
    token = get_admin_token()
    response = client.get("/api/admin/bins", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "total_bins" in data
    assert "bins" in data
    if data["bins"]:
        bin_id = data["bins"][0]["id"]
        patch_res = client.patch(
            f"/api/admin/bins/{bin_id}",
            json={"fill_level_pct": 50},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["fill_level_pct"] == 50
    else:
        assert data["total_bins"] == 0


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
        "title": "Municipal in-app notice",
        "message": "Heavy rain expected in Ward 4.",
        "audience": "In-app announcement feed",
        "priority": "Standard (in-app)"
    }
    b_res = client.post("/api/admin/notifications/broadcast", json=broadcast_data, headers={"Authorization": f"Bearer {token}"})
    assert b_res.status_code == 201
    assert b_res.json()["title"] == "Municipal in-app notice"
    assert b_res.json()["audience"] == "In-app announcement feed"
    assert b_res.json()["priority"] == "Standard (in-app)"
    assert b_res.json()["is_broadcast"] is True
    history = client.get("/api/admin/notifications", headers={"Authorization": f"Bearer {token}"})
    assert history.status_code == 200
    assert any(item["id"] == b_res.json()["id"] for item in history.json())
