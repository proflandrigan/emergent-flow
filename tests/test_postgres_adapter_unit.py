"""Unit tests for PostgresAdapter credential handling (implicit auth support)."""

from __future__ import annotations

import pytest


def test_postgres_implicit_auth_engine_creation() -> None:
    """PostgresAdapter._engine() succeeds with only host/port/database (no user/password)."""
    pytest.importorskip("sqlalchemy")
    from emergentflow.data.warehouse.adapters.postgres_adapter import PostgresAdapter

    adapter = PostgresAdapter()
    engine = adapter._engine({"host": "localhost", "port": "5432", "database": "testdb"})
    url_str = str(engine.url)
    assert "postgresql+psycopg" in url_str
    assert "testdb" in url_str
    assert "@" not in url_str


def test_postgres_explicit_auth_engine_creation() -> None:
    """PostgresAdapter._engine() builds correct URL with all credentials."""
    pytest.importorskip("sqlalchemy")
    from emergentflow.data.warehouse.adapters.postgres_adapter import PostgresAdapter

    adapter = PostgresAdapter()
    engine = adapter._engine({
        "host": "db.internal",
        "port": "5432",
        "database": "mydb",
        "user": "admin",
        "password": "secret",
    })
    url_str = str(engine.url)
    assert "admin" in url_str
    assert "db.internal" in url_str
    assert "mydb" in url_str
