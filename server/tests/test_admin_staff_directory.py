import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from server.database.db import SessionLocal
from server.models.account_invitation import AccountInvitation
from server.models.user import User
from server.schemas.admin import AdminProvisionRequest
from server.routes.admin import create_collector
from server.services.admin_service import AdminService


@pytest.mark.parametrize("expected_state", ["pending", "expired", "used", "revoked"])
def test_staff_directory_includes_invitation_state_without_token_hash(expected_state):
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:12]
    collector = User(
        full_name="Directory Test Collector",
        email=f"directory-{suffix}@example.test",
        employee_id=f"DIR-{suffix}",
        role="collector",
        ward="Ward Directory Test",
        is_active=False,
        is_verified=False,
        account_status="pending",
        hashed_password=None,
    )
    db.add(collector)
    db.flush()
    now = datetime.now(timezone.utc)
    expires_at = now - timedelta(hours=1) if expected_state == "expired" else now + timedelta(hours=24)
    invitation = AccountInvitation(
        user_id=collector.id,
        role="collector",
        token_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        expires_at=expires_at,
        consumed_at=now if expected_state == "used" else None,
        revoked_at=now if expected_state == "revoked" else None,
    )
    db.add(invitation)
    db.commit()
    try:
        directory = AdminService.get_all_drivers(db)
        item = next(row for row in directory if row.id == collector.id)
        assert item.role == "collector"
        assert item.ward == "Ward Directory Test"
        assert item.account_status == "pending"
        assert item.invitation_status == expected_state
        assert item.invitation_expires_at is not None
        assert item.activated_at is None
        assert "token_hash" not in item.model_dump()
    finally:
        db.delete(invitation)
        db.delete(collector)
        db.commit()
        db.close()


def test_collector_provisioning_api_is_disabled_for_all_payloads():
    db = SessionLocal()
    admin = db.query(User).filter(User.email == "admin@cityswap.io").one()
    try:
        for ward in (None, "   ", "Ward 1"):
            with pytest.raises(HTTPException) as error:
                create_collector(
                    AdminProvisionRequest(
                        full_name="Wardless Collector",
                        employee_id=f"NOWARD-{uuid.uuid4().hex[:10]}",
                        ward=ward,
                    ),
                    db,
                    admin,
                )
            assert error.value.status_code == 410
        assert db.query(User).filter(User.employee_id.like("NOWARD-%")).count() == 0
    finally:
        db.close()
