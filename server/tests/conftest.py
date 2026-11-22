import gc
import os
import sys
import tempfile
import warnings
from pathlib import Path
import httpx
import pytest

# Keep all tests on a disposable SQLite database, never on a developer or production database.
_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"ecopulse-test-{os.getpid()}.db"
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["ENV"] = "test"
os.environ["MEDIA_STORAGE_BACKEND"] = "local"


def pytest_unconfigure(config):
    database_module = sys.modules.get("server.database.db")
    if database_module:
        database_module.engine.dispose(close=True)
    gc.collect()
    for path in (
        _TEST_DB_PATH,
        Path(f"{_TEST_DB_PATH}-wal"),
        Path(f"{_TEST_DB_PATH}-shm"),
    ):
        if path.exists():
            try:
                path.unlink()
            except PermissionError as exc:
                warnings.warn(
                    f"Could not remove disposable test database file {path}: {exc}",
                    RuntimeWarning,
                )


@pytest.fixture(scope="session", autouse=True)
def explicit_auth_test_accounts():
    import server.models
    from server.database.db import Base, SessionLocal, engine
    from server.models.user import User
    from server.models.municipality import Municipality
    from server.models.ward import Ward
    from server.tests.iam_test_helpers import prepare_admin_mfa
    from server.utils.security import hash_password

    Base.metadata.create_all(bind=engine)
    accounts = (
        {
            "email": "priya@cityswap.io",
            "employee_id": None,
            "full_name": "Test Citizen",
            "phone": "9876543210",
            "role": "citizen",
        },
        {
            "email": "ramesh@cityswap.io",
            "employee_id": "EMP-DRIVER-01",
            "full_name": "Test Driver",
            "phone": "9876543211",
            "role": "driver",
        },
        {
            "email": "collector@cityswap.io",
            "employee_id": "EMP-COLLECTOR-01",
            "full_name": "Test Collector",
            "phone": "9876543212",
            "role": "collector",
        },
        {
            "email": "admin@cityswap.io",
            "employee_id": "EMP-ADMIN-01",
            "full_name": "Test Administrator",
            "phone": "9876543213",
            "role": "admin",
        },
        {
            "email": "super-admin@example.test",
            "employee_id": "MUNI-SUPER-TEST-01",
            "full_name": "Test Super Administrator",
            "phone": "9876543214",
            "role": "admin",
            "is_super_admin": True,
        },
    )
    db = SessionLocal()
    try:
        municipality = db.query(Municipality).filter(Municipality.code == "DHULE").first()
        if municipality is None:
            municipality = Municipality(code="DHULE", name="Dhule", is_active=True)
            db.add(municipality)
            db.flush()
        if not db.query(Ward).filter(Ward.municipality_id == municipality.id).first():
            db.add_all([Ward(municipality_id=municipality.id, ward_number=str(number),
                             display_name=f"Ward {number}", is_active=True) for number in range(1, 20)])
            db.flush()
        for account in accounts:
            user = db.query(User).filter(User.email == account["email"]).first()
            if user is None:
                user = User(
                    **account,
                    ward="Test Ward",
                    hashed_password=hash_password("Password123!"),
                    eco_coins=0,
                    is_active=True,
                    is_verified=True,
                    account_status="active",
                    municipality_id=municipality.id,
                )
                db.add(user)
                db.flush()
            if user.role in {"admin", "collector"}:
                prepare_admin_mfa(user)
            else:
                user.is_active = True
                user.is_verified = True
                user.account_status = "active"
        db.commit()
        yield
    finally:
        db.close()


@pytest.fixture(autouse=True)
def prevent_live_meta_api_requests(monkeypatch):
    """Keep the test suite from sending credentials or requests to Meta."""
    original_handle_request = httpx.HTTPTransport.handle_request

    def is_meta_request(request):
        hostname = (request.url.host or "").lower()
        return hostname == "facebook.com" or hostname.endswith(
            (".facebook.com", ".fbcdn.net", ".fbsbx.com")
        )

    def mocked_handle_request(self, request):
        if is_meta_request(request):
            if request.method == "GET":
                return httpx.Response(
                    503,
                    request=request,
                    json={"error": {"message": "Meta API is mocked in tests"}},
                )
            return httpx.Response(
                200,
                request=request,
                json={"messages": [{"id": "wamid.mocked-test-send"}]},
            )
        return original_handle_request(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", mocked_handle_request)
