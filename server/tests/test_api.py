from fastapi.testclient import TestClient
from server.main import app
from server.database.db import SessionLocal
from server.models.user import User
from server.services.auth_service import AuthService
from server.tests.iam_test_helpers import citizen_access_token

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome" in response.json()["message"]

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_get_complaints():
    response = client.get("/api/complaints")
    assert response.status_code == 401

def test_create_complaint():
    payload = {
        "location": "Test Area, Ward 12",
        "type": "Plastic Waste",
        "ward": "Ward 12",
        "description": "Scattered plastic bottles near green bin",
        "image_url": "https://example.com/waste.jpg"
    }
    response = client.post("/api/complaints", json=payload)
    assert response.status_code == 201
    assert response.json()["location"] == "Test Area, Ward 12"
    assert response.json()["type"] == "Plastic Waste"
    assert response.json()["ward"] == "Ward 12"

def test_driver_endpoints_security():
    # 1. Unauthenticated test
    for url in ["/api/driver/tasks", "/api/driver/performance", "/api/driver/fuel-logs", "/api/driver/messages"]:
        response = client.get(url)
        assert response.status_code == 401

    # 2. Authenticate as Citizen
    db = SessionLocal()
    try:
        AuthService.seed_demo_users(db)
        citizen = db.query(User).filter(User.email == "priya@cityswap.io").first()
        assert citizen is not None
        citizen_token = citizen_access_token(citizen)
    finally:
        db.close()
    citizen_headers = {"Authorization": f"Bearer {citizen_token}"}

    for url in ["/api/driver/tasks", "/api/driver/performance", "/api/driver/fuel-logs", "/api/driver/messages"]:
        response = client.get(url, headers=citizen_headers)
        assert response.status_code == 403

    # 3. Authenticate as Driver
    login_response2 = client.post("/api/auth/login", json={
        "email": "EMP-DRIVER-01",
        "password": "Password123!",
        "role": "driver"
    })
    assert login_response2.status_code == 200
    driver_token = login_response2.json()["access_token"]
    driver_headers = {"Authorization": f"Bearer {driver_token}"}

    # Test GET Tasks
    response = client.get("/api/driver/tasks", headers=driver_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # Test GET Performance
    response = client.get("/api/driver/performance", headers=driver_headers)
    assert response.status_code == 200
    assert "weekly_trends" in response.json()

    # Test GET Fuel Logs
    response = client.get("/api/driver/fuel-logs", headers=driver_headers)
    assert response.status_code == 200
    assert "logs" in response.json()

    # Test POST Fuel Log
    fuel_payload = {
        "odometer": 45400,
        "liters": 40.0,
        "cost": 3800.0
    }
    response = client.post("/api/driver/fuel-logs", json=fuel_payload, headers=driver_headers)
    assert response.status_code == 201
    assert response.json()["odometer"] == 45400

    # Test GET Messages
    response = client.get("/api/driver/messages", headers=driver_headers)
    assert response.status_code == 200
    assert "conversations" in response.json()

    # Test POST Message
    msg_payload = {
        "body": "Test message from driver"
    }
    response = client.post("/api/driver/messages", json=msg_payload, headers=driver_headers)
    assert response.status_code == 201
    assert response.json()["body"] == "Test message from driver"

def test_track_complaint():
    create_response = client.post("/api/complaints", json={
        "location": "Secure Tracking Test Site",
        "type": "Plastic Waste",
        "ward": "Test Ward",
        "description": "Private tracking test",
        "latitude": 20.9,
        "longitude": 74.7,
    })
    assert create_response.status_code == 201
    created = create_response.json()
    tracking_id = created["id"]
    token = created["tracking_token"]

    res_track = client.get(
        f"/api/complaints/track/{tracking_id}",
        headers={"X-Tracking-Token": token},
    )
    assert res_track.status_code == 200
    assert res_track.json()["id"] == tracking_id
    assert "db_id" not in res_track.json()
    assert "tracking_token" not in res_track.json()

def test_forgot_password():
    res = client.post(
        "/api/auth/forgot-password",
        json={"identifier": "priya@cityswap.io", "role": "citizen"}
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

def test_otp_flow():
    from server.database.db import SessionLocal
    from server.models.mobile_otp import MobileOtpToken
    _db = SessionLocal()
    _db.query(MobileOtpToken).filter(MobileOtpToken.phone == "9876543210").delete()
    _db.commit()
    _db.close()

    # Send OTP to registered user
    res_send = client.post("/api/auth/send-otp", json={"phone": "9876543210"})
    assert res_send.status_code == 200
    assert res_send.json()["success"] is True

    # Verify invalid OTP - must return 400 and not issue access_token
    res_verify = client.post(
        "/api/auth/verify-otp",
        json={"phone": "9876543210", "otp": "999999", "role": "citizen"}
    )
    assert res_verify.status_code in (400, 422)
    assert "access_token" not in res_verify.json()

def test_public_notifications():
    res = client.get("/api/notifications")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

