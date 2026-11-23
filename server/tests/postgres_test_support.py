"""Safety and schema isolation helpers for destructive PostgreSQL test fixtures."""
from __future__ import annotations

import ipaddress
import os
import re
import uuid

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url

from server.database.target_guard import DISPOSABLE_AUTHORIZATION, validate_target_url


def validate_postgres_test_target(url: str | None, authorization: str | None) -> str:
    """Accept only explicitly authorized, disposable, loopback PostgreSQL URLs."""
    validated = validate_target_url(
        url,
        disposable_authorization=authorization,
        require_disposable=True,
    )
    parsed = make_url(validated)
    if not parsed.drivername.startswith("postgresql"):
        raise ValueError("PostgreSQL integration tests require a PostgreSQL URL.")
    host = (parsed.host or "").lower()
    is_loopback = host in {"localhost", "localhost.localdomain"}
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise ValueError("PostgreSQL integration tests require a loopback host.")
    if authorization != DISPOSABLE_AUTHORIZATION:
        raise ValueError("Set ECOLPULSE_DISPOSABLE_POSTGRES_AUTHORIZATION=DISPOSABLE.")
    return validated


def isolated_schema_name(prefix: str = "ecopulse_test") -> str:
    safe_prefix = re.sub(r"[^a-z0-9_]", "_", prefix.lower()).strip("_") or "ecopulse_test"
    return f"{safe_prefix}_{os.getpid()}_{uuid.uuid4().hex[:12]}"


def create_isolated_postgres_engine(url: str, schema: str):
    """Create one owned schema and return an engine whose search_path is limited to it."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise ValueError("Invalid generated PostgreSQL test schema name.")
    admin_engine = create_engine(url, pool_pre_ping=True)
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    finally:
        admin_engine.dispose()

    engine = create_engine(url, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _set_test_search_path(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f'SET search_path TO "{schema}"')
            dbapi_connection.commit()
        finally:
            cursor.close()

    return engine


def drop_isolated_postgres_schema(url: str, schema: str) -> None:
    """Drop only the uniquely generated schema created by this fixture."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
        raise ValueError("Refusing to drop a non-generated PostgreSQL test schema name.")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    finally:
        engine.dispose()
