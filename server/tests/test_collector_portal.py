import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from server.database.db import SessionLocal
from server.models.complaint import Complaint
from server.models.task import DriverTask
from server.models.task_evidence import TaskEvidence
from server.models.task_event import TaskEvent
from server.models.user import User
from server.routes.collector import list_ward_collection_tasks
from server.services.task_lifecycle_service import (
    add_evidence,
    review_evidence,
    submit_for_verification,
    transition_driver_task,
)
from server.utils.security import get_current_driver_user


def test_collector_task_board_is_ward_scoped_and_reports_rework_history():
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:10]
    ward = f"Collector-Ward-{suffix}"
    collector = User(
        full_name="Ward Collector",
        email=f"collector-{suffix}@example.test",
        employee_id=f"COL-{suffix}",
        role="collector",
        ward=ward,
        is_active=True,
        is_verified=True,
        account_status="active",
        mfa_enabled=True,
    )
    driver = User(
        full_name="Ward Driver",
        email=f"driver-{suffix}@example.test",
        employee_id=f"DRV-{suffix}",
        role="driver",
        ward=ward,
        is_active=True,
        is_verified=True,
        account_status="active",
    )
    other_driver = User(
        full_name="Other Ward Driver",
        email=f"other-{suffix}@example.test",
        employee_id=f"OTH-{suffix}",
        role="driver",
        ward=f"Other-{suffix}",
        is_active=True,
        is_verified=True,
        account_status="active",
    )
    db.add_all([collector, driver, other_driver])
    db.flush()
    inside = Complaint(
        tracking_number=f"CP-{suffix}-IN", ward=ward, location_address="Ward site",
        waste_type="Mixed Waste", description="Within ward", status="In Progress",
    )
    outside = Complaint(
        tracking_number=f"CP-{suffix}-OUT", ward=f"Other-{suffix}", location_address="Other site",
        waste_type="Plastic Waste", description="Outside ward", status="In Progress",
    )
    db.add_all([inside, outside])
    db.flush()
    inside_task = DriverTask(
        complaint_id=inside.id, driver_id=driver.id, location_name=inside.location_address,
        status="Requires Rework",
    )
    outside_task = DriverTask(
        complaint_id=outside.id, driver_id=other_driver.id, location_name=outside.location_address,
        status="In Progress",
    )
    db.add_all([inside_task, outside_task])
    db.flush()
    rejection = TaskEvidence(
        task_id=inside_task.id, complaint_id=inside.id, driver_id=driver.id,
        after_image_ref="private-test-evidence-ref", status="rejected",
        rejection_reason="Photo does not show the full collection area.",
        collected_at=datetime.now(timezone.utc),
    )
    db.add(rejection)
    db.commit()
    try:
        result = list_ward_collection_tasks(db, collector)
        assert [row["id"] for row in result] == [inside_task.id]
        assert result[0]["complaint"]["ward"] == ward
        assert result[0]["driver_name"] == driver.full_name
        assert result[0]["evidence_status"] == "rejected"
        assert result[0]["rejection_reason"] == rejection.rejection_reason
        assert "private-test-evidence-ref" not in str(result)

        collector.ward = None
        db.commit()
        with pytest.raises(HTTPException) as unassigned:
            list_ward_collection_tasks(db, collector)
        assert unassigned.value.status_code == 403

        with pytest.raises(HTTPException) as wrong_role:
            list_ward_collection_tasks(db, driver)
        assert wrong_role.value.status_code == 403
    finally:
        db.query(TaskEvidence).filter(TaskEvidence.task_id.in_([inside_task.id, outside_task.id])).delete(synchronize_session=False)
        db.query(DriverTask).filter(DriverTask.id.in_([inside_task.id, outside_task.id])).delete(synchronize_session=False)
        db.query(Complaint).filter(Complaint.id.in_([inside.id, outside.id])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([collector.id, driver.id, other_driver.id])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_driver_lifecycle_remains_authorized_and_collector_cannot_use_driver_guard():
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:10]
    ward = f"Lifecycle-Ward-{suffix}"
    collector = User(
        full_name="Lifecycle Collector", email=f"collector-life-{suffix}@example.test",
        employee_id=f"COL-LIFE-{suffix}", role="collector", ward=ward,
        is_active=True, is_verified=True, account_status="active", mfa_enabled=True,
    )
    driver = User(
        full_name="Lifecycle Driver", email=f"driver-life-{suffix}@example.test",
        employee_id=f"DRV-LIFE-{suffix}", role="driver", ward=ward,
        is_active=True, is_verified=True, account_status="active",
    )
    admin = User(
        full_name="Lifecycle Admin", email=f"admin-life-{suffix}@example.test",
        employee_id=f"ADM-LIFE-{suffix}", role="admin", ward=ward,
        is_active=True, is_verified=True, account_status="active", mfa_enabled=True,
    )
    db.add_all([collector, driver, admin])
    db.flush()
    complaint = Complaint(
        tracking_number=f"LC-{suffix}", ward=ward, location_address="Lifecycle site",
        waste_type="Mixed Waste", description="Lifecycle regression", status="Pending",
    )
    db.add(complaint)
    db.flush()
    task = DriverTask(
        complaint_id=complaint.id, driver_id=driver.id,
        location_name=complaint.location_address, status="Pending",
    )
    db.add(task)
    db.commit()
    try:
        with pytest.raises(HTTPException) as denied:
            get_current_driver_user(collector)
        assert denied.value.status_code == 403

        transition_driver_task(db, task.id, driver, "accept")
        transition_driver_task(db, task.id, driver, "start")
        add_evidence(db, task.id, driver, None, "test-after-image", "First collection attempt")
        submit_for_verification(db, task.id, driver)
        review_evidence(db, task.id, admin, False, "The pickup area is not fully visible.")
        db.refresh(task)
        assert task.status == "Requires Rework"
        assert db.query(TaskEvidence).filter(TaskEvidence.task_id == task.id).order_by(TaskEvidence.id.desc()).first().rejection_reason == "The pickup area is not fully visible."

        add_evidence(db, task.id, driver, None, "test-after-image-retry", "Resubmitted after rework")
        submit_for_verification(db, task.id, driver)
        review_evidence(db, task.id, admin, True)
        db.refresh(task)
        db.refresh(complaint)
        assert task.status == complaint.status == "Completed"
    finally:
        db.query(TaskEvent).filter(TaskEvent.task_id == task.id).delete(synchronize_session=False)
        db.query(TaskEvidence).filter(TaskEvidence.task_id == task.id).delete(synchronize_session=False)
        db.query(DriverTask).filter(DriverTask.id == task.id).delete(synchronize_session=False)
        db.query(Complaint).filter(Complaint.id == complaint.id).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([collector.id, driver.id, admin.id])).delete(synchronize_session=False)
        db.commit()
        db.close()
