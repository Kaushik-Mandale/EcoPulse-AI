import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import server.models
from server.database.db import Base
from server.models.municipality import Municipality
from server.models.complaint import Complaint
from server.models.security_audit_event import SecurityAuditEvent
from server.models.task import DriverTask
from server.models.task_evidence import TaskEvidence
from server.models.task_event import TaskEvent
from server.models.user import User
from server.models.ward import Ward
from server.routes.admin import (
    assign_staff_ward,
    create_ward,
    list_wards,
    update_ward,
)
from server.schemas.admin import StaffProvisionRequest, StaffWardAssignmentRequest, WardCreateRequest, WardUpdateRequest
from server.services.admin_service import AdminService
from server.database.migrations_runner import _missing_objects
from server.services.staff_provisioning_service import provision_staff_account
from server.utils.security import hash_password


@pytest.fixture
def registry_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'ward-registry.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    muni_a = Municipality(code="MUNI-A", name="Municipality A", is_active=True)
    muni_b = Municipality(code="MUNI-B", name="Municipality B", is_active=True)
    db.add_all([muni_a, muni_b]); db.flush()
    ward_a1 = Ward(municipality_id=muni_a.id, ward_number="1", display_name="Ward 1", is_active=True)
    ward_a2 = Ward(municipality_id=muni_a.id, ward_number="2", display_name="Ward 2", is_active=False)
    ward_a3 = Ward(municipality_id=muni_a.id, ward_number="3", display_name="Ward 3", is_active=True)
    ward_b1 = Ward(municipality_id=muni_b.id, ward_number="1", display_name="Ward 1", is_active=True)
    db.add_all([ward_a1, ward_a2, ward_a3, ward_b1]); db.flush()
    super_admin = User(full_name="Super Admin", role="admin", is_super_admin=True, is_active=True,
                       is_verified=True, account_status="active", hashed_password=hash_password("SafePass123!"))
    municipal_admin = User(full_name="Municipal Admin", role="admin", municipality_id=muni_a.id,
                           is_active=True, is_verified=True, account_status="active",
                           hashed_password=hash_password("SafePass123!"))
    db.add_all([super_admin, municipal_admin]); db.commit()
    try:
        yield db, {"a": muni_a, "b": muni_b, "a1": ward_a1, "a2": ward_a2, "a3": ward_a3, "b1": ward_b1,
                   "super": super_admin, "admin": municipal_admin}
    finally:
        db.close(); engine.dispose()


def _staff_payload(role, ward_id, phone):
    return StaffProvisionRequest(full_name=f"New {role}", role=role, phone=phone,
                                 email=None, employee_id=None, ward_id=ward_id)


def test_super_admin_creates_ward_and_duplicate_number_is_rejected(registry_db):
    db, data = registry_db
    created = create_ward(WardCreateRequest(municipality_id=data["a"].id, ward_number="4",
                                            display_name="Ward 4", locality_description=None), db, data["super"])
    assert created["display_name"] == "Ward 4"
    assert created["staff_counts"] == {"admin": 0, "driver": 0, "collector": 0}
    with pytest.raises(HTTPException) as duplicate:
        create_ward(WardCreateRequest(municipality_id=data["a"].id, ward_number="4",
                                      display_name="Duplicate", locality_description=None), db, data["super"])
    assert duplicate.value.status_code == 409
    assert db.query(SecurityAuditEvent).filter(SecurityAuditEvent.action == "ward_created").count() == 1


def test_fresh_orm_schema_satisfies_ward_registry_migration_contract(registry_db):
    db, _ = registry_db
    assert _missing_objects(db.get_bind(), "011") == []


def test_wards_are_isolated_by_municipality_and_active_filter(registry_db):
    db, data = registry_db
    result = list_wards(data["a"].id, True, "ward 1", db, data["admin"])
    assert [item["id"] for item in result] == [data["a1"].id]
    with pytest.raises(HTTPException) as denied:
        list_wards(data["b"].id, None, "", db, data["admin"])
    assert denied.value.status_code == 403
    all_for_super = list_wards(None, None, "", db, data["super"])
    assert len(all_for_super) == 4


@pytest.mark.parametrize("role,phone", [("driver", "9876500001"), ("collector", "9876500002")])
def test_driver_and_collector_assignment_persists_registry_id(registry_db, role, phone):
    db, data = registry_db
    created = provision_staff_account(db, data["admin"], _staff_payload(role, data["a1"].id, phone))
    account = db.query(User).filter(User.id == created["id"]).one()
    assert account.ward_id == data["a1"].id
    assert account.municipality_id == data["a"].id
    assert account.ward == "Ward 1"


def test_provision_rejects_missing_inactive_and_foreign_municipality_wards(registry_db):
    db, data = registry_db
    for index, ward_id in enumerate((999999, data["a2"].id, data["b1"].id), start=1):
        with pytest.raises(HTTPException) as rejected:
            provision_staff_account(db, data["admin"], _staff_payload("driver", ward_id, f"98765000{index}0"))
        assert rejected.value.status_code in {403, 422}


def test_super_admin_only_ward_management_and_ward_status_audit(registry_db):
    db, data = registry_db
    payload = WardCreateRequest(municipality_id=data["a"].id, ward_number="4", display_name="Ward 4")
    with pytest.raises(HTTPException) as denied:
        create_ward(payload, db, data["admin"])
    assert denied.value.status_code == 403
    changed = update_ward(data["a1"].id, WardUpdateRequest(
        ward_number="1", display_name="Central Ward", locality_description="Verified later", is_active=False,
    ), db, data["super"])
    assert changed["is_active"] is False
    assert db.query(SecurityAuditEvent).filter(SecurityAuditEvent.action == "ward_deactivated").count() == 1


def test_reassignment_preserves_history_and_directory_filters_by_registry_scope(registry_db):
    db, data = registry_db
    created = provision_staff_account(db, data["admin"], _staff_payload("driver", data["a1"].id, "9876500044"))
    account = db.query(User).filter(User.id == created["id"]).one()
    complaint = Complaint(tracking_number="WARD-HISTORY-01", ward="Ward 1", location_address="Test location",
                          waste_type="Mixed Waste", assigned_driver_id=account.id)
    db.add(complaint); db.flush()
    task = DriverTask(complaint_id=complaint.id, driver_id=account.id, location_name="Test location")
    db.add(task); db.flush()
    evidence = TaskEvidence(task_id=task.id, complaint_id=complaint.id, driver_id=account.id,
                            after_image_ref="retained-evidence-reference", status="approved")
    event = TaskEvent(task_id=task.id, actor_user_id=data["admin"].id, actor_role="admin",
                      event_type="approved", to_status="Completed")
    db.add_all([evidence, event]); db.commit()
    with pytest.raises(HTTPException) as denied:
        assign_staff_ward(account.id, StaffWardAssignmentRequest(ward_id=data["b1"].id), db, data["admin"])
    assert denied.value.status_code == 403

    changed = assign_staff_ward(account.id, StaffWardAssignmentRequest(ward_id=data["a1"].id), db, data["super"])
    assert changed["ward_id"] == data["a1"].id
    records = AdminService.get_all_drivers(db, include_collectors=True, municipality_id=data["a"].id)
    assert any(item.id == account.id and item.ward_id == data["a1"].id for item in records)
    other = provision_staff_account(db, data["admin"], _staff_payload("driver", data["a3"].id, "9876500045"))
    ward_a_records = AdminService.get_all_drivers(db, include_collectors=True, municipality_id=data["a"].id,
                                                  ward_id=data["a1"].id)
    assert {item.id for item in ward_a_records} == {account.id}
    account = db.query(User).filter(User.id == account.id).one()
    assign_staff_ward(account.id, StaffWardAssignmentRequest(ward_id=data["a3"].id), db, data["super"])
    assert db.query(User).filter(User.id == account.id).one().ward_id == data["a3"].id
    assert db.query(User).filter(User.id == other["id"]).one().ward_id == data["a3"].id
    assert db.query(Complaint).filter(Complaint.id == complaint.id).one().ward == "Ward 1"
    assert db.query(DriverTask).filter(DriverTask.id == task.id).one().driver_id == account.id
    assert db.query(TaskEvidence).filter(TaskEvidence.id == evidence.id).one().after_image_ref == "retained-evidence-reference"
    assert db.query(TaskEvent).filter(TaskEvent.id == event.id).one().to_status == "Completed"
