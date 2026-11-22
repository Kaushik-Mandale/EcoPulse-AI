"""Cross-portal HTTP workflows using the disposable SQLite test database."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from server.database.db import SessionLocal
from server.main import app
from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.models.task_evidence import TaskEvidence
from server.models.task_event import TaskEvent
from server.models.user import User
from server.tests.iam_test_helpers import admin_access_token, citizen_access_token


client = TestClient(app)
JPEG = b"\xff\xd8\xff" + (b"\x00" * 16)


def _auth(user, *, admin=False):
    token = admin_access_token(user) if admin else citizen_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def test_web_complaint_to_admin_verified_completion_and_secure_tracking(monkeypatch):
    """Exercise citizen submission, municipal assignment, Driver lifecycle, and tracking."""
    class MemoryStorage:
        def save_image(self, content, extension, mime_type, media_id=None):
            return f"e2e-test://{media_id}{extension}"

    monkeypatch.setattr("server.routes.driver.get_media_storage", lambda: MemoryStorage())
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:10]
    ward = f"E2E Ward {suffix}"
    citizen = User(
        full_name="E2E Citizen", email=f"citizen-{suffix}@example.test", role="citizen",
        ward=ward, is_active=True, is_verified=True, account_status="active",
    )
    driver = User(
        full_name="E2E Driver", email=f"driver-{suffix}@example.test", employee_id=f"DRV-{suffix}",
        role="driver", ward=ward, is_active=True, is_verified=True, account_status="active",
    )
    admin = User(
        full_name="E2E Municipal Admin", email=f"admin-{suffix}@example.test", employee_id=f"ADM-{suffix}",
        role="admin", ward=ward, is_active=True, is_verified=True, account_status="active", mfa_enabled=True,
    )
    db.add_all([citizen, driver, admin])
    db.commit()
    complaint_id = None
    task_id = None
    try:
        submitted = client.post("/api/complaints", headers=_auth(citizen), json={
            "location": "Civic garden entrance",
            "type": "Mixed Waste",
            "ward": ward,
            "description": "Waste collection request from the web portal",
            "latitude": 20.9,
            "longitude": 74.7,
        })
        assert submitted.status_code == 201, submitted.text
        receipt = submitted.json()
        assert receipt["status"] == "Pending"
        assert receipt["tracking_token"]
        complaint = db.query(Complaint).filter(Complaint.tracking_number == receipt["id"]).one()
        complaint_id = complaint.id
        assert complaint.citizen_id == citizen.id

        assigned = client.post("/api/admin/assign-task", headers=_auth(admin, admin=True), json={
            "complaint_id": complaint.id,
            "driver_name": driver.employee_id,
        })
        assert assigned.status_code == 200, assigned.text
        task = db.query(DriverTask).filter(DriverTask.complaint_id == complaint.id).one()
        task_id = task.id
        assert task.driver_id == driver.id

        visible_tasks = client.get("/api/driver/tasks", headers=_auth(driver))
        assert visible_tasks.status_code == 200
        assert task.id in {row["id"] for row in visible_tasks.json()}
        assert client.post(f"/api/driver/tasks/{task.id}/accept", headers=_auth(driver)).status_code == 200
        assert client.post(f"/api/driver/tasks/{task.id}/start", headers=_auth(driver)).status_code == 200
        evidence = client.post(
            f"/api/driver/tasks/{task.id}/evidence",
            headers=_auth(driver),
            files={"after_photo": ("after.jpg", JPEG, "image/jpeg")},
            data={"notes": "Collection completed at the reported site."},
        )
        assert evidence.status_code == 200, evidence.text
        assert client.post(f"/api/driver/tasks/{task.id}/submit-for-verification", headers=_auth(driver)).status_code == 200
        approved = client.post(f"/api/admin/tasks/{task.id}/approve", headers=_auth(admin, admin=True))
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "Completed"

        history = client.get("/api/complaints/my", headers=_auth(citizen))
        assert history.status_code == 200
        assert next(row for row in history.json() if row["id"] == receipt["id"])["status"] == "Completed"
        tracked = client.get(
            f"/api/complaints/track/{receipt['id']}",
            headers={"X-Tracking-Token": receipt["tracking_token"]},
        )
        assert tracked.status_code == 200
        assert tracked.json()["status"] == "Completed"
        assert "tracking_token" not in tracked.json()
        db.refresh(complaint)
        db.refresh(task)
        assert complaint.status == task.status == "Completed"
    finally:
        if task_id:
            db.query(TaskEvent).filter(TaskEvent.task_id == task_id).delete(synchronize_session=False)
            db.query(TaskEvidence).filter(TaskEvidence.task_id == task_id).delete(synchronize_session=False)
            db.query(DriverTask).filter(DriverTask.id == task_id).delete(synchronize_session=False)
        if complaint_id:
            db.query(Complaint).filter(Complaint.id == complaint_id).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([citizen.id, driver.id, admin.id])).delete(synchronize_session=False)
        db.commit()
        db.close()
