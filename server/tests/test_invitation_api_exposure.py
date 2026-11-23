from pathlib import Path

from fastapi.testclient import TestClient

from server.main import app
from server.tests.iam_test_helpers import admin_access_token
from server.tests.test_municipal_iam import _create_invited_user, iam_context
from server.models.user import User

client = TestClient(app)


def test_all_ordinary_invitation_issue_and_reset_apis_are_disabled_without_serializing_tokens(iam_context, caplog):
    db, create_user, _ = iam_context
    municipal = create_user("admin")
    super_admin = create_user("admin", is_super_admin=True)
    target_admin, _ = _create_invited_user(db, super_admin, "admin", "Synthetic Admin", "API-INVITE-ADMIN")
    target_driver, _ = _create_invited_user(
        db, municipal, "driver", "Synthetic Driver", "API-INVITE-DRIVER",
        phone="9876507654", ward="Test Ward",
    )
    municipal_headers = {"Authorization": f"Bearer {admin_access_token(municipal)}"}
    super_headers = {"Authorization": f"Bearer {admin_access_token(super_admin)}"}
    operations = [
        ("/api/admin/admins/invitations", super_headers, {"full_name": "New Admin", "employee_id": "NEW-API-ADMIN"}),
        ("/api/admin/drivers", municipal_headers, {"full_name": "New Driver", "employee_id": "NEW-API-DRIVER", "phone": "9876500001", "ward": "Ward 1"}),
        ("/api/admin/collectors", municipal_headers, {"full_name": "New Collector", "employee_id": "NEW-API-COLLECTOR", "ward": "Ward 1"}),
    ]
    responses = [client.post(path, headers=headers, json=payload) for path, headers, payload in operations]
    responses += [
        client.post(f"/api/admin/admins/{target_admin.id}/reset-invitation", headers=super_headers),
        client.post(f"/api/admin/drivers/{target_driver.id}/reset-invitation", headers=municipal_headers),
    ]
    for response in responses:
        assert response.status_code == 410
        assert "activation_token" not in response.json()
        assert "activation_url" not in response.json()
        assert "#token=" not in response.text
    assert "#token=" not in caplog.text
    assert db.query(User).filter(User.employee_id.in_({"NEW-API-ADMIN", "NEW-API-DRIVER", "NEW-API-COLLECTOR"})).count() == 0
    directory_responses = [
        client.get("/api/admin/admins", headers=super_headers),
        client.get("/api/admin/drivers", headers=municipal_headers),
    ]
    for response in directory_responses:
        assert response.status_code == 200
        assert "activation_token" not in response.text
        assert "activation_url" not in response.text
        assert "token_hash" not in response.text
        assert "#token=" not in response.text


def test_dashboard_sources_never_retain_or_render_invitation_tokens():
    root = Path(__file__).resolve().parents[2]
    for relative in (
        "client/src/pages/AdminDashboardPage.jsx",
        "client/src/pages/SuperAdminDashboardPage.jsx",
        "client/src/services/adminService.js",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "activation_token" not in source
        assert "activate#token=" not in source
        assert "activation_url" not in source
