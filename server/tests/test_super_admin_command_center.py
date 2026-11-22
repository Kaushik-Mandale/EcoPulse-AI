import inspect
import uuid

import pytest
from fastapi import HTTPException

from server.database.db import SessionLocal
from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.models.user import User
from server.models.whatsapp_session import WhatsAppCitizen
from server.routes.admin import (
    list_governance_citizen_complaints,
    list_governance_citizens,
    list_governance_tasks,
)
from server.routes.auth import get_me
from server.utils.security import hash_password
from server.utils.security import get_current_super_admin_user


def _assert_super_admin_dependency(endpoint):
    dependency = inspect.signature(endpoint).parameters["current_admin"].default
    assert dependency.dependency is get_current_super_admin_user


@pytest.fixture
def command_center_context():
    db = SessionLocal()
    super_admin = db.query(User).filter(User.is_super_admin.is_(True)).first()
    assert super_admin is not None, "test session fixture must provide a Super Admin account"
    user_ids = []

    def create_user(role, **overrides):
        uid = uuid.uuid4().hex[:12]
        user = User(
            full_name=f"Governance {role.title()}",
            email=f"{role}-{uid}@command-center.test",
            phone=f"9{int(uid[:9], 16) % 1_000_000_000:09d}",
            employee_id=f"CC-{role[:3].upper()}-{uid}",
            hashed_password=hash_password("ValidPassword123!"),
            role=role,
            ward=overrides.pop("ward", "Test Ward"),
            is_active=True,
            is_verified=True,
            account_status="active",
            **overrides,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_ids.append(user.id)
        return user

    try:
        yield db, create_user, super_admin
    finally:
        task_ids = [row[0] for row in db.query(DriverTask.id).filter(DriverTask.driver_id.in_(user_ids)).all()] if user_ids else []
        complaint_ids = [row[0] for row in db.query(DriverTask.complaint_id).filter(DriverTask.id.in_(task_ids)).all()] if task_ids else []
        if task_ids:
            db.query(DriverTask).filter(DriverTask.id.in_(task_ids)).delete(synchronize_session=False)
        if user_ids:
            db.query(WhatsAppCitizen).filter(WhatsAppCitizen.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(Complaint).filter(Complaint.citizen_id.in_(user_ids)).delete(synchronize_session=False)
        if complaint_ids:
            db.query(Complaint).filter(Complaint.id.in_(complaint_ids)).delete(synchronize_session=False)
        if user_ids:
            db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_governance_citizen_directory_and_history_are_super_admin_only(command_center_context):
    db, create_user, super_admin = command_center_context
    municipal_admin = create_user("admin")
    citizen = create_user("citizen", ward="Ward Audit")
    citizen.hashed_password = "must-never-be-returned"
    db.add(WhatsAppCitizen(
        phone_number=f"+1555{uuid.uuid4().int % 10**7:07d}",
        user_id=citizen.id,
        is_authorized=True,
    ))
    complaint = Complaint(
        tracking_number=f"EP-TEST-{uuid.uuid4().hex[:10]}",
        tracking_secret="private-tracking-secret",
        citizen_id=citizen.id,
        ward="Ward Audit",
        location_address="Test location",
        waste_type="Mixed Waste",
        status="Pending",
    )
    db.add(complaint)
    db.commit()

    _assert_super_admin_dependency(list_governance_citizens)
    _assert_super_admin_dependency(list_governance_citizen_complaints)
    super_admin.mfa_enabled = True
    profile = get_me(super_admin)
    assert profile.is_super_admin is True
    assert profile.mfa_enabled is True
    assert profile.login_id == super_admin.login_id
    rows = list_governance_citizens(db, super_admin)
    row = next(item for item in rows if item["id"] == citizen.id)
    assert row["whatsapp_linked"] is True
    assert row["complaint_count"] == 1
    assert row["account_status"] == citizen.account_status
    assert "hashed_password" not in row
    assert "tracking_secret" not in row
    with pytest.raises(HTTPException) as admin_denied:
        get_current_super_admin_user(municipal_admin)
    assert admin_denied.value.status_code == 403
    with pytest.raises(HTTPException) as citizen_denied:
        get_current_super_admin_user(citizen)
    assert citizen_denied.value.status_code == 403

    history = list_governance_citizen_complaints(citizen.id, db, super_admin)
    assert len(history) == 1
    assert history[0].id == complaint.tracking_number
    assert "tracking_token" not in history[0].model_dump_json()
    assert "private-tracking-secret" not in history[0].model_dump_json()

    db.delete(complaint)
    db.query(WhatsAppCitizen).filter(WhatsAppCitizen.user_id == citizen.id).delete(synchronize_session=False)
    db.commit()


def test_governance_task_monitor_reports_real_counts_without_lifecycle_mutation(command_center_context):
    db, create_user, super_admin = command_center_context
    municipal_admin = create_user("admin")
    driver = create_user("driver", ward="Ward Tasks")
    complaint = Complaint(
        tracking_number=f"EP-TASK-{uuid.uuid4().hex[:10]}",
        tracking_secret="task-tracking-secret",
        ward="Ward Tasks",
        location_address="Task location",
        waste_type="Mixed Waste",
        status="In Progress",
    )
    db.add(complaint)
    db.flush()
    task = DriverTask(
        complaint_id=complaint.id,
        driver_id=driver.id,
        location_name="Task location",
        status="Requires Rework",
    )
    db.add(task)
    db.commit()

    _assert_super_admin_dependency(list_governance_tasks)
    result = list_governance_tasks(db=db, current_admin=super_admin)
    assert result["total"] >= 1
    assert result["counts"]["Requires Rework"] >= 1
    row = next(item for item in result["tasks"] if item["id"] == task.id)
    assert row["status"] == "Requires Rework"
    assert row["driver_name"] == driver.full_name
    assert "task-tracking-secret" not in str(result)
    with pytest.raises(HTTPException) as admin_denied:
        get_current_super_admin_user(municipal_admin)
    assert admin_denied.value.status_code == 403
    with pytest.raises(HTTPException) as invalid_filter:
        list_governance_tasks(status_filter="bogus", db=db, current_admin=super_admin)
    assert invalid_filter.value.status_code == 422

    assert db.query(DriverTask).filter(DriverTask.id == task.id).one().status == "Requires Rework"
    db.delete(task)
    db.delete(complaint)
    db.commit()
