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
    engine = adapter._engine(
        {
            "host": "db.internal",
            "port": "5432",
            "database": "mydb",
            "user": "admin",
            "password": "secret",
        }
    )
    url_str = str(engine.url)
    assert "admin" in url_str
    assert "db.internal" in url_str
    assert "mydb" in url_str


def _sqlite_backed_adapter(tmp_path, monkeypatch):
    sa = pytest.importorskip("sqlalchemy")
    from emergentflow.data.warehouse.adapters.postgres_adapter import PostgresAdapter

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'pg.db'}")
    monkeypatch.setattr(PostgresAdapter, "_engine", lambda self, credentials: engine)
    return PostgresAdapter(), engine


def test_postgres_split_table():
    from emergentflow.data.warehouse.adapters.postgres_adapter import _split_table

    assert _split_table("mart.sales") == ("mart", "sales")
    assert _split_table("sales") == (None, "sales")


def test_postgres_write_append_and_transactional_truncate(tmp_path, monkeypatch):
    sa = pytest.importorskip("sqlalchemy")
    import pandas as pd

    from emergentflow.data.warehouse.protocol import WriteRequest

    adapter, engine = _sqlite_backed_adapter(tmp_path, monkeypatch)
    frame = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})

    def count():
        with engine.connect() as conn:
            return conn.execute(sa.text("SELECT count(*) FROM t1")).scalar()

    req = WriteRequest(table="t1", dialect="postgres", connection="pg")
    adapter.write(req, frame, {})
    adapter.write(req, frame, {})
    assert count() == 6
    trunc = WriteRequest(table="t1", dialect="postgres", connection="pg", mode="truncate")
    # A frame that cannot be inserted must roll the truncate back: the 6 old rows survive.
    with pytest.raises(Exception, match="zzz"):
        adapter.write(trunc, pd.DataFrame({"zzz": [1.0]}), {})
    assert count() == 6
    adapter.write(trunc, frame.iloc[:1], {})
    assert count() == 1
    with pytest.raises(ValueError, match="exists"):
        req_err = WriteRequest(table="t1", dialect="postgres", connection="pg", mode="error")
        adapter.write(req_err, frame, {})
