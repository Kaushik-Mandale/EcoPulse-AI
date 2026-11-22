import uuid

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

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


@pytest.fixture
def lifecycle_context(monkeypatch):
    class MemoryStorage:
        def save_image(self, content, extension, mime_type, media_id=None):
            return f"task-evidence-test://{media_id}{extension}"

    monkeypatch.setattr("server.routes.driver.get_media_storage", lambda: MemoryStorage())
    db = SessionLocal()
    driver = db.query(User).filter(User.email == "ramesh@cityswap.io").first()
    admin = db.query(User).filter(User.email == "admin@cityswap.io").first()
    collector = db.query(User).filter(User.email == "collector@cityswap.io").first()
    suffix = uuid.uuid4().hex[:10]
    complaint = Complaint(tracking_number=f"LIFE-{suffix}", ward="Test Ward", location_address="Test location",
                          waste_type="Mixed Waste", description="Task lifecycle test", image_url="original-complaint-image")
    db.add(complaint)
    db.flush()
    task = DriverTask(complaint_id=complaint.id, driver_id=driver.id, location_name="Test location", status="Pending")
    db.add(task)
    db.commit()
    ids = (task.id, complaint.id)
    try:
        yield db, driver, admin, collector, task
    finally:
        db.query(TaskEvent).filter(TaskEvent.task_id == ids[0]).delete(synchronize_session=False)
        db.query(TaskEvidence).filter(TaskEvidence.task_id == ids[0]).delete(synchronize_session=False)
        db.query(DriverTask).filter(DriverTask.id == ids[0]).delete(synchronize_session=False)
        db.query(Complaint).filter(Complaint.id == ids[1]).delete(synchronize_session=False)
        db.commit()
        db.close()


def headers(user, admin=False):
    token = admin_access_token(user) if admin else citizen_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def test_driver_lifecycle_requires_evidence_and_admin_review(lifecycle_context):
    db, driver, admin, collector, task = lifecycle_context
    own = headers(driver)

    assert client.post(f"/api/driver/tasks/{task.id}/start", headers=own).status_code == 409
    assert client.post(f"/api/driver/tasks/{task.id}/accept", headers=own).status_code == 200
    assert client.post(f"/api/driver/tasks/{task.id}/accept", headers=own).status_code == 409
    assert client.post(f"/api/driver/tasks/{task.id}/start", headers=own).status_code == 200
    direct_complete = client.patch(f"/api/driver/tasks/{task.id}/status", headers=own, json={"status": "Completed"})
    assert direct_complete.status_code == 409
    assert client.post(f"/api/driver/tasks/{task.id}/submit-for-verification", headers=own).status_code == 409

    upload = client.post(f"/api/driver/tasks/{task.id}/evidence", headers=own,
                         files={"after_photo": ("after.jpg", JPEG, "image/jpeg"),
                                "before_photo": ("before.jpg", JPEG, "image/jpeg")},
                         data={"notes": "Collected from the marked location"})
    assert upload.status_code == 200, upload.text
    assert client.post(f"/api/driver/tasks/{task.id}/submit-for-verification", headers=own).status_code == 200

    pending = client.get("/api/admin/tasks/verification", headers=headers(admin, admin=True))
    assert pending.status_code == 200
    assert any(item["id"] == task.id for item in pending.json())
    assert client.post(f"/api/admin/tasks/{task.id}/approve", headers=own).status_code == 403
    assert client.post(f"/api/admin/tasks/{task.id}/approve", headers=headers(collector, admin=True)).status_code == 403
    assert client.post(f"/api/admin/tasks/{task.id}/reject", headers=headers(admin, admin=True), json={"reason": " "}).status_code == 422
    approved = client.post(f"/api/admin/tasks/{task.id}/approve", headers=headers(admin, admin=True))
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "Completed"
    event_types = {event["event_type"] for event in approved.json()["history"]}
    assert {"task_accepted", "collection_started", "evidence_submitted",
            "submitted_for_verification", "completion_verified"} <= event_types
    db.refresh(task)
    complaint = db.query(Complaint).filter(Complaint.id == task.complaint_id).one()
    assert task.status == complaint.status == "Completed"
    assert complaint.image_url == "original-complaint-image"
    assert client.post(f"/api/admin/tasks/{task.id}/approve", headers=headers(admin, admin=True)).status_code == 409


def test_complaint_operations_detail_exposes_task_evidence_only_to_municipal_admin(lifecycle_context):
    db, driver, admin, collector, task = lifecycle_context
    complaint_id = task.complaint_id
    from server.routes.admin import get_complaint_operations

    municipal = get_complaint_operations(complaint_id, db, admin)
    assert municipal["complaint"]["description"] == "Task lifecycle test"
    assert municipal["task"]["id"] == task.id
    assert municipal["task"]["status"] == "Pending"
    assert municipal["task"]["evidence"] == []
    assert "token_hash" not in str(municipal)

    ward_collector = get_complaint_operations(complaint_id, db, collector)
    assert ward_collector["task"] == {
        "id": task.id,
        "status": "Pending",
        "location_name": "Test location",
    }

    original_ward = collector.ward
    collector.ward = "Other Ward"
    db.commit()
    with pytest.raises(HTTPException) as denied:
        get_complaint_operations(complaint_id, db, collector)
    assert denied.value.status_code == 404
    collector.ward = original_ward
    db.commit()


def test_task_assignment_evidence_validation_and_rework(lifecycle_context, monkeypatch):
    db, driver, admin, collector, task = lifecycle_context
    other = User(full_name="Other Driver", email=f"other-{uuid.uuid4().hex[:10]}@example.test", role="driver", is_active=True, is_verified=True, account_status="active")
    db.add(other)
    db.commit()
    assert client.post(f"/api/driver/tasks/{task.id}/accept", headers=headers(other)).status_code == 403
    db.delete(other)
    db.commit()

    own = headers(driver)
    client.post(f"/api/driver/tasks/{task.id}/accept", headers=own)
    client.post(f"/api/driver/tasks/{task.id}/start", headers=own)
    invalid = client.post(f"/api/driver/tasks/{task.id}/evidence", headers=own,
                          files={"after_photo": ("bad.jpg", b"not an image", "image/jpeg")})
    assert invalid.status_code == 400
    from server.utils.config import config
    original_limit = config.MAX_UPLOAD_SIZE
    monkeypatch.setattr(config, "MAX_UPLOAD_SIZE", 10)
    oversized = client.post(f"/api/driver/tasks/{task.id}/evidence", headers=own,
                            files={"after_photo": ("large.jpg", JPEG, "image/jpeg")})
    assert oversized.status_code == 413
    monkeypatch.setattr(config, "MAX_UPLOAD_SIZE", original_limit)
    upload = client.post(f"/api/driver/tasks/{task.id}/evidence", headers=own,
                         files={"after_photo": ("after.jpg", JPEG, "image/jpeg")}, data={"notes": "Initial attempt"})
    assert upload.status_code == 200
    client.post(f"/api/driver/tasks/{task.id}/submit-for-verification", headers=own)
    rejected = client.post(f"/api/admin/tasks/{task.id}/reject", headers=headers(admin, admin=True), json={"reason": "Photo does not show the full pickup area"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "Requires Rework"
    assert rejected.json()["evidence"][0]["rejection_reason"]
    second = client.post(f"/api/driver/tasks/{task.id}/evidence", headers=own,
                         files={"after_photo": ("after.jpg", JPEG, "image/jpeg")}, data={"notes": "Resubmitted"})
    assert second.status_code == 200
    assert client.post(f"/api/driver/tasks/{task.id}/submit-for-verification", headers=own).status_code == 200
    assert db.query(TaskEvidence).filter(TaskEvidence.task_id == task.id).count() == 2
