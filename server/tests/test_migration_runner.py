"""Explicit migration runner: ordering, history, adoption, and safety guards."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

import server.models  # noqa: F401  # register every table on Base.metadata
from server.database.db import Base
from server.database.migrations_runner import (
    APPLYING_METHOD,
    BASE_SCHEMA_TABLES,
    HISTORY_TABLE,
    MigrationError,
    PrerequisiteError,
    adopt_existing,
    apply_pending,
    diagnose,
    discover_migrations,
    ensure_history_table,
    migration_lock,
    plan,
    reconcile,
    status,
    _normalize_predicate,
)
from server.scripts import migrate


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'runner.db').as_posix()}")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def migrations_dir(tmp_path):
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "001_create_widgets.sql").write_text(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY, name VARCHAR(50));\n",
        encoding="utf-8",
    )
    (directory / "002_add_size.sql").write_text(
        "ALTER TABLE widgets ADD COLUMN size INTEGER;\n", encoding="utf-8"
    )
    (directory / "003_add_color.sql").write_text(
        "ALTER TABLE widgets ADD COLUMN color VARCHAR(20);\n", encoding="utf-8"
    )
    return directory


def _tables(engine):
    return set(inspect(engine).get_table_names()) - {HISTORY_TABLE}


def _history(engine):
    ensure_history_table(engine)
    with engine.connect() as connection:
        rows = connection.execute(
            text(f"SELECT version, name, checksum, method FROM {HISTORY_TABLE} ORDER BY version")
        ).mappings().all()
    return [dict(row) for row in rows]


def test_discover_migrations_is_ordered_and_excludes_rollbacks(migrations_dir):
    (migrations_dir / "002_down.sql").write_text("DROP TABLE widgets;\n", encoding="utf-8")
    (migrations_dir / "000_legacy_verification.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (migrations_dir / "notes.sql").write_text("SELECT 1;\n", encoding="utf-8")

    migrations = discover_migrations(migrations_dir)

    assert [m.version for m in migrations] == ["001", "002", "003"]


def test_discover_migrations_rejects_duplicate_versions(migrations_dir):
    (migrations_dir / "003_another_change.sql").write_text("SELECT 1;\n", encoding="utf-8")

    with pytest.raises(PrerequisiteError):
        discover_migrations(migrations_dir)


def test_repository_migrations_are_discovered_in_order():
    migrations = discover_migrations()

    assert [m.version for m in migrations] == [
        "001", "002", "003", "004", "005", "006", "007", "008", "009", "010", "011", "012"
    ]
    assert all(m.checksum for m in migrations)


def test_apply_requires_adoption_for_existing_schema(engine, migrations_dir):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE widgets (id INTEGER PRIMARY KEY)"))

    with pytest.raises(PrerequisiteError) as excinfo:
        apply_pending(engine, discover_migrations(migrations_dir))

    assert "adopt" in str(excinfo.value)
    assert _history(engine) == []


def test_apply_records_history_and_rerun_is_noop(engine, migrations_dir):
    migrations = discover_migrations(migrations_dir)

    applied = apply_pending(engine, migrations)

    assert applied == ["001", "002", "003"]
    assert _tables(engine) == {"widgets"}
    records = _history(engine)
    assert [r["version"] for r in records] == ["001", "002", "003"]
    assert {r["method"] for r in records} == {"applied"}
    assert all(len(r["checksum"]) == 64 for r in records)

    assert apply_pending(engine, migrations) == []
    assert len(_history(engine)) == 3


def test_dry_run_does_not_execute_or_record(engine, migrations_dir):
    migrations = discover_migrations(migrations_dir)

    planned = apply_pending(engine, migrations, dry_run=True)

    assert planned == ["001", "002", "003"]
    assert _tables(engine) == set()
    assert _history(engine) == []


def test_checksum_mismatch_is_rejected(engine, migrations_dir):
    apply_pending(engine, discover_migrations(migrations_dir))
    (migrations_dir / "001_create_widgets.sql").write_text(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT, extra TEXT);\n",
        encoding="utf-8",
    )
    edited = discover_migrations(migrations_dir)

    with pytest.raises(MigrationError) as excinfo:
        plan(engine, edited)

    assert "Checksum mismatch" in str(excinfo.value)


def test_out_of_order_pending_migration_is_rejected(engine, migrations_dir):
    all_migrations = discover_migrations(migrations_dir)
    first, _, third = all_migrations
    apply_pending(engine, [first, third])

    with pytest.raises(MigrationError) as excinfo:
        plan(engine, all_migrations)

    assert "Out-of-order" in str(excinfo.value)


def test_adopt_refuses_database_without_base_schema(engine):
    with pytest.raises(PrerequisiteError):
        adopt_existing(engine, discover_migrations(), through_version="007")


def test_adopt_records_existing_schema_without_ddl(engine):
    Base.metadata.create_all(bind=engine)
    before = _tables(engine)
    assert BASE_SCHEMA_TABLES <= before

    recorded = adopt_existing(engine, discover_migrations(), through_version="012")

    assert recorded[0] == "000"
    assert recorded[1:] == ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010", "011", "012"]
    assert _tables(engine) == before
    records = _history(engine)
    assert records[0]["version"] == "000"
    assert records[0]["method"] == "adopted"
    assert {r["method"] for r in records[1:]} == {"adopted"}

    state = status(engine)
    assert state["baseline"] is True
    assert state["pending"] == []


def test_adopt_verification_detects_missing_sentinel_objects(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE whatsapp_registration_challenges"))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(engine, discover_migrations(), through_version="007")

    assert "whatsapp_registration_challenges" in str(excinfo.value)


def test_adopt_without_verification_records_all_versions(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE whatsapp_registration_challenges"))

    recorded = adopt_existing(
        engine, discover_migrations(), through_version="007", verify=False
    )

    assert recorded[0] == "000"
    assert recorded[-1] == "007"


def test_migration_lock_is_a_noop_on_sqlite(engine):
    with migration_lock(engine):
        pass


def test_transaction_management_detection_per_migration():
    from server.database.migrations_runner import _TRANSACTION_START_RE

    migrations = {m.version: m for m in discover_migrations()}

    for version in ("001", "002", "003", "007"):
        assert _TRANSACTION_START_RE.search(migrations[version].sql), version
    for version in ("004", "005", "006"):
        assert not _TRANSACTION_START_RE.search(migrations[version].sql), version


def test_cli_status_and_unconfirmed_up_exit_codes(engine, migrations_dir):
    url = str(engine.url)
    directory = str(migrations_dir)

    assert migrate.main(["status", "--url", url, "--migrations-dir", directory]) == 0
    assert migrate.main(["up", "--url", url, "--migrations-dir", directory]) == 2
    assert _tables(engine) == set()


def test_cli_up_applies_pending_migrations(engine, migrations_dir):
    url = str(engine.url)
    directory = str(migrations_dir)

    assert migrate.main(["up", "--yes", "--authorize-disposable-target", "DISPOSABLE",
                         "--url", url, "--migrations-dir", directory]) == 0
    assert _tables(engine) == {"widgets"}
    assert [r["version"] for r in _history(engine)] == ["001", "002", "003"]


def test_cli_reports_prerequisite_failure_with_exit_code(engine, migrations_dir):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE widgets (id INTEGER PRIMARY KEY)"))

    result = migrate.main(
        [
            "up",
            "--yes",
            "--authorize-disposable-target",
            "DISPOSABLE",
            "--url",
            str(engine.url),
            "--migrations-dir",
            str(migrations_dir),
        ]
    )

    assert result == 2


def _seed(engine, migrations, versions, method="applied"):
    ensure_history_table(engine)
    by_version = {migration.version: migration for migration in migrations}
    with engine.begin() as connection:
        for version in versions:
            migration = by_version[version]
            connection.execute(
                text(
                    f"INSERT INTO {HISTORY_TABLE} (version, name, checksum, method) "
                    "VALUES (:version, :name, :checksum, :method)"
                ),
                {
                    "version": version,
                    "name": migration.name,
                    "checksum": migration.checksum,
                    "method": method,
                },
            )


def test_incomplete_marker_blocks_plan_and_apply(engine, migrations_dir):
    migrations = discover_migrations(migrations_dir)
    _seed(engine, migrations, ["001"], method=APPLYING_METHOD)

    with pytest.raises(MigrationError) as excinfo:
        plan(engine, migrations)
    assert "Incomplete migration state" in str(excinfo.value)

    with pytest.raises(MigrationError):
        apply_pending(engine, migrations)
    assert _tables(engine) == set()


def test_status_reports_in_progress_versions(engine, migrations_dir):
    migrations = discover_migrations(migrations_dir)
    _seed(engine, migrations, ["001"], method=APPLYING_METHOD)

    state = status(engine, migrations)

    assert state["initialized"] is True
    assert state["in_progress"] == ["001"]
    assert state["applied"] == []
    assert "001_create_widgets" in state["pending"]


def test_diagnose_reports_uninitialized_empty_database(engine):
    issues = diagnose(engine, discover_migrations())

    assert [issue.code for issue in issues] == ["uninitialized_empty_schema"]


def test_diagnose_reports_uninitialized_existing_schema(engine):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE widgets (id INTEGER PRIMARY KEY)"))

    issues = diagnose(engine, discover_migrations())

    assert [issue.code for issue in issues] == ["uninitialized_existing_schema"]


def test_diagnose_reports_incomplete_application(engine, migrations_dir):
    migrations = discover_migrations(migrations_dir)
    _seed(engine, migrations, ["001"], method=APPLYING_METHOD)

    codes = {issue.code for issue in diagnose(engine, migrations)}

    assert "incomplete_application" in codes


def test_diagnose_reports_unknown_version(engine, migrations_dir):
    _seed(engine, discover_migrations(migrations_dir), ["001"])
    with engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO {HISTORY_TABLE} (version, name, checksum, method) "
                "VALUES ('099', 'ghost', 'deadbeef', 'applied')"
            )
        )

    issues = diagnose(engine, discover_migrations(migrations_dir))

    assert any(issue.code == "unknown_version" and issue.version == "099" for issue in issues)


def test_diagnose_reports_checksum_mismatch(engine, migrations_dir):
    apply_pending(engine, discover_migrations(migrations_dir))
    (migrations_dir / "001_create_widgets.sql").write_text(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY, renamed TEXT);\n", encoding="utf-8"
    )

    issues = diagnose(engine, discover_migrations(migrations_dir))

    assert any(issue.code == "checksum_mismatch" and issue.version == "001" for issue in issues)


def test_diagnose_reports_out_of_order_pending_versions(engine, migrations_dir):
    migrations = discover_migrations(migrations_dir)
    _seed(engine, migrations, ["001", "003"])

    issues = diagnose(engine, migrations)

    assert any(issue.code == "out_of_order" and issue.version == "002" for issue in issues)


def test_diagnose_reports_missing_base_schema_for_pending_migrations(engine):
    ensure_history_table(engine)

    codes = {issue.code for issue in diagnose(engine, discover_migrations())}

    assert "missing_base_schema" in codes


def test_diagnose_reports_present_but_unrecorded_objects(engine):
    Base.metadata.create_all(bind=engine)
    _seed(engine, discover_migrations(), ["001", "002", "003", "004", "005", "006"])

    issues = diagnose(engine, discover_migrations())

    assert [(issue.code, issue.version) for issue in issues] == [
        ("present_but_unrecorded", "007"), ("present_but_unrecorded", "008"),
        ("present_but_unrecorded", "009"), ("present_but_unrecorded", "010"),
        ("present_but_unrecorded", "011"), ("present_but_unrecorded", "012")
    ]


def test_diagnose_reports_applied_but_missing_objects(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE mobile_otp_tokens"))
    _seed(engine, discover_migrations(), ["001", "002", "003", "004"])

    issues = diagnose(engine, discover_migrations())

    assert any(issue.code == "applied_but_missing" and issue.version == "004" for issue in issues)


def test_reconcile_record_requires_sentinel_objects(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE mobile_otp_tokens"))

    with pytest.raises(PrerequisiteError):
        reconcile(engine, record_version="004")

    assert _history(engine) == []


def test_reconcile_records_present_but_unrecorded_version(engine):
    Base.metadata.create_all(bind=engine)

    result = reconcile(engine, record_version="004")

    assert result == {"recorded": "004"}
    records = _history(engine)
    assert [(r["version"], r["method"]) for r in records] == [("004", "reconciled")]


def test_reconcile_finalizes_an_incomplete_marker(engine):
    Base.metadata.create_all(bind=engine)
    _seed(engine, discover_migrations(), ["007"], method=APPLYING_METHOD)

    assert reconcile(engine, record_version="007") == {"recorded": "007"}
    records = _history(engine)
    assert [(r["version"], r["method"]) for r in records] == [("007", "reconciled")]


def test_reconcile_clear_removes_marker_only_when_objects_absent(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE whatsapp_registration_challenges"))
    _seed(engine, discover_migrations(), ["006"], method=APPLYING_METHOD)

    assert reconcile(engine, clear_version="006") == {"cleared": "006"}
    assert all(record["version"] != "006" for record in _history(engine))


def test_reconcile_clear_refuses_when_objects_exist(engine):
    Base.metadata.create_all(bind=engine)
    _seed(engine, discover_migrations(), ["006"], method=APPLYING_METHOD)

    with pytest.raises(PrerequisiteError) as excinfo:
        reconcile(engine, clear_version="006")

    assert "record it instead" in str(excinfo.value)
    assert [(r["version"], r["method"]) for r in _history(engine)] == [("006", APPLYING_METHOD)]


def test_reconcile_clear_requires_incomplete_state(engine):
    with pytest.raises(PrerequisiteError):
        reconcile(engine, clear_version="007")


def test_reconcile_rejects_unknown_version(engine):
    with pytest.raises(PrerequisiteError):
        reconcile(engine, record_version="099")


def test_reconcile_rejects_already_recorded_version(engine, migrations_dir):
    migrations = discover_migrations(migrations_dir)
    apply_pending(engine, migrations)

    with pytest.raises(PrerequisiteError):
        reconcile(engine, migrations, record_version="001")


def test_reconcile_refuses_versions_without_verification_rules(engine, migrations_dir):
    (migrations_dir / "099_widget_flags.sql").write_text(
        "ALTER TABLE widgets ADD COLUMN flags INTEGER;\n", encoding="utf-8"
    )
    migrations = discover_migrations(migrations_dir)

    with pytest.raises(PrerequisiteError) as excinfo:
        reconcile(engine, migrations, record_version="099")

    assert "no verification rules" in str(excinfo.value)


def test_cli_check_passes_on_a_clean_adopted_schema(engine):
    Base.metadata.create_all(bind=engine)
    url = str(engine.url)

    assert migrate.main(["adopt", "--through", "012", "--yes", "--authorize-disposable-target",
                         "DISPOSABLE", "--url", url]) == 0
    assert migrate.main(["check", "--url", url]) == 0


def test_cli_check_fails_on_uninitialized_database(engine):
    assert migrate.main(["check", "--url", str(engine.url)]) == 1


def test_cli_up_fails_when_a_marker_is_incomplete(engine, migrations_dir):
    migrations = discover_migrations(migrations_dir)
    _seed(engine, migrations, ["001"], method=APPLYING_METHOD)

    result = migrate.main(
        [
            "up",
            "--yes",
            "--authorize-disposable-target",
            "DISPOSABLE",
            "--url",
            str(engine.url),
            "--migrations-dir",
            str(migrations_dir),
        ]
    )

    assert result == 1
    assert _tables(engine) == set()


def test_cli_reconcile_requires_confirmation(engine):
    Base.metadata.create_all(bind=engine)
    url = str(engine.url)

    assert migrate.main(["reconcile", "--record", "004", "--url", url]) == 2
    assert _history(engine) == []


def test_cli_reconcile_records_with_confirmation(engine):
    Base.metadata.create_all(bind=engine)
    url = str(engine.url)

    assert migrate.main(["reconcile", "--record", "004", "--yes", "--authorize-disposable-target",
                         "DISPOSABLE", "--url", url]) == 0
    assert [(r["version"], r["method"]) for r in _history(engine)] == [("004", "reconciled")]


def test_adopt_fails_when_foreign_key_missing(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE complaints"))
        conn.execute(text(
            "CREATE TABLE complaints ("
            "id INTEGER PRIMARY KEY, "
            "tracking_number VARCHAR(30) UNIQUE, "
            "tracking_secret VARCHAR(64), "
            "whatsapp_citizen_id INTEGER, "
            "ward VARCHAR(50), "
            "location_address VARCHAR(255), "
            "waste_type VARCHAR(50)"
            ")"
        ))
        conn.execute(text("CREATE INDEX ix_complaints_whatsapp_citizen_id ON complaints(whatsapp_citizen_id)"))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(engine, discover_migrations(), through_version="001")
    assert "foreign key" in str(excinfo.value).lower()
    assert "001" not in [r["version"] for r in _history(engine)]


def test_adopt_fails_when_index_missing(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_complaints_tracking_secret"))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(engine, discover_migrations(), through_version="002")
    assert "index on" in str(excinfo.value).lower()
    assert "tracking_secret" in str(excinfo.value)
    assert "002" not in [r["version"] for r in _history(engine)]


def test_adopt_fails_when_index_uniqueness_mismatch(engine):
    # Replace the partial unique index with a plain (non-partial) unique index;
    # the sentinel requires partial_predicate so adoption must reject it.
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX uq_whatsapp_citizens_user_id_notnull"))
        conn.execute(text(
            "CREATE UNIQUE INDEX uq_whatsapp_citizens_user_id_notnull "
            "ON whatsapp_citizens(user_id)"
        ))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(engine, discover_migrations(), through_version="003")
    assert "uq_whatsapp_citizens_user_id_notnull" in str(excinfo.value)
    assert status(engine)["applied"] == []


def test_adopt_rejects_incorrect_partial_index_predicate(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX uq_whatsapp_citizens_user_id_notnull"))
        conn.execute(text(
            "CREATE UNIQUE INDEX uq_whatsapp_citizens_user_id_notnull "
            "ON whatsapp_citizens(user_id) WHERE user_id IS NOT NULL AND user_id > 0"
        ))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(engine, discover_migrations(), through_version="003")
    assert "predicate mismatch" in str(excinfo.value)
    assert status(engine)["applied"] == []


def test_predicate_normalization_preserves_semantics():
    expected = "phone IS NOT NULL AND phone != ''"

    assert _normalize_predicate(
        "((phone IS NOT NULL) AND ((phone)::text <> ''::text))"
    ) == _normalize_predicate(expected)
    assert _normalize_predicate(
        "phone IS NOT NULL AND (phone != '' OR phone = 'test')"
    ) != _normalize_predicate(expected)
    assert _normalize_predicate(
        "phone IS NOT NULL AND phone::citext != ''"
    ) != _normalize_predicate(expected)
    assert _normalize_predicate("phone = 'A'") != _normalize_predicate("phone = 'a'")
    assert _normalize_predicate("phone = '::text'") != _normalize_predicate("phone = ''")
    assert _normalize_predicate("phone = 'x(y)'") != _normalize_predicate("phone = 'xy'")


def test_postgresql_catalog_inspection_errors_propagate():
    class BrokenPostgresEngine:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        def connect(self):
            raise RuntimeError("catalog unavailable")

    from server.database.migrations_runner import _inspect_index_definitions

    with pytest.raises(RuntimeError, match="catalog unavailable"):
        _inspect_index_definitions(BrokenPostgresEngine(), "users")


def test_adopt_fails_when_migration_005_observability_column_missing(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_mobile_otp_tokens_delivery_status"))
        conn.execute(text("ALTER TABLE mobile_otp_tokens DROP COLUMN delivery_status"))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(engine, discover_migrations(), through_version="005")
    assert "delivery_status" in str(excinfo.value)
    assert "005" not in [r["version"] for r in _history(engine)]


def test_adopt_fails_when_nullable_setting_incorrect(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE users"))
        conn.execute(text(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, "
            "full_name VARCHAR(120) NOT NULL, "
            "email VARCHAR(120) NOT NULL, "
            "role VARCHAR(20) NOT NULL, "
            "phone VARCHAR(20)"
            ")"
        ))
        conn.execute(text("CREATE UNIQUE INDEX uq_users_phone ON users(phone)"))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(engine, discover_migrations(), through_version="004")
    assert "nullability mismatch" in str(excinfo.value).lower()
    assert "004" not in [r["version"] for r in _history(engine)]


def test_adopt_fails_when_registration_challenge_index_missing(engine):
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_whatsapp_reg_challenges_user_id"))

    with pytest.raises(PrerequisiteError) as excinfo:
        adopt_existing(engine, discover_migrations(), through_version="006")
    assert "index on" in str(excinfo.value).lower()
    assert "user_id" in str(excinfo.value)
    assert "006" not in [r["version"] for r in _history(engine)]

