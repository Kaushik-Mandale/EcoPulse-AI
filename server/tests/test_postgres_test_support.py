import pytest

from server.tests.postgres_test_support import validate_postgres_test_target


def test_postgres_test_target_requires_explicit_url_and_disposable_designation():
    with pytest.raises(Exception):
        validate_postgres_test_target("", "DISPOSABLE")
    with pytest.raises(Exception):
        validate_postgres_test_target("not-a-database-url", "DISPOSABLE")
    with pytest.raises(Exception):
        validate_postgres_test_target(
            "postgresql://tester:secret@127.0.0.1:5432/ecopulse_test", None
        )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://tester:secret@db.example.com:5432/ecopulse_test",
        "postgresql://tester:secret@ep.example.neon.tech:5432/ecopulse_test",
        "postgresql://tester:secret@127.0.0.1:5432/ecopulse_production",
        "postgresql://tester:secret@127.0.0.1:5432/ecopulse_prod_test",
    ],
)
def test_postgres_test_target_rejects_remote_hosted_and_production_names(url):
    with pytest.raises(Exception):
        validate_postgres_test_target(url, "DISPOSABLE")


def test_postgres_test_target_accepts_explicit_loopback_disposable_database():
    assert validate_postgres_test_target(
        "postgresql://tester:secret@127.0.0.1:5432/ecopulse_test", "DISPOSABLE"
    ) == "postgresql://tester:secret@127.0.0.1:5432/ecopulse_test"
