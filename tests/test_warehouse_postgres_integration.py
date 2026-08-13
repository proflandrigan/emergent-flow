"""Real-Postgres driver integration tests (Epic 13 Story 9).

Run only in the dedicated CI job — not part of the default ``pytest`` run.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("sqlalchemy")

from emergentflow.data.warehouse.protocol import QueryRequest  # noqa: E402


def _credentials() -> dict[str, str]:
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": os.environ.get("PGPORT", "5432"),
        "database": os.environ.get("PGDATABASE", "postgres"),
        "user": os.environ.get("PGUSER", "postgres"),
        "password": os.environ.get("PGPASSWORD", "postgres"),
    }


@pytest.fixture(scope="module")
def adapter():
    import sqlalchemy as sa

    from emergentflow.data.warehouse.adapters.postgres_adapter import PostgresAdapter

    creds = _credentials()
    instance = PostgresAdapter()

    url = f"postgresql+psycopg://{creds['user']}:{creds['password']}@{creds['host']}:{creds['port']}/{creds['database']}"
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS ef_test_widgets"))
        conn.execute(
            sa.text("CREATE TABLE ef_test_widgets (id INTEGER, name TEXT, price DOUBLE PRECISION)")
        )
        conn.execute(
            sa.text(
                "INSERT INTO ef_test_widgets (id, name, price) VALUES "
                "(1, 'foo', 1.99), "
                "(2, 'bar', 5.49), "
                "(3, 'baz', 12.99)"
            )
        )

    yield (instance, creds)

    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS ef_test_widgets"))
    engine.dispose()


@pytest.mark.driver_integration
class TestPostgresIntegration:
    """Real Postgres integration tests."""

    def test_execute_select(self, adapter):
        inst, creds = adapter
        request = QueryRequest(
            sql="SELECT id, name, price FROM ef_test_widgets ORDER BY id",
            dialect="postgres",
            connection="test",
        )
        result = inst.execute(request, creds)
        assert result.row_count == 3
        assert result.dialect == "postgres"
        assert list(result.df.columns) == ["id", "name", "price"]
        assert result.df["id"].tolist() == [1, 2, 3]
        assert result.df["name"].tolist() == ["foo", "bar", "baz"]

    def test_execute_respects_max_rows(self, adapter):
        inst, creds = adapter
        request = QueryRequest(
            sql="SELECT id, name, price FROM ef_test_widgets ORDER BY id",
            dialect="postgres",
            connection="test",
            max_rows=2,
        )
        result = inst.execute(request, creds)
        assert result.row_count == 2
        assert result.truncated is True

    def test_dry_run(self, adapter):
        inst, creds = adapter
        request = QueryRequest(
            sql="SELECT id, name, price FROM ef_test_widgets ORDER BY id",
            dialect="postgres",
            connection="test",
        )
        estimate = inst.dry_run(request, creds)
        assert estimate.dialect == "postgres"
        # dry_run reports no row estimate (EXPLAIN gives plan lines, not a row count).
        assert estimate.estimated_rows is None

    def test_list_relations(self, adapter):
        inst, creds = adapter
        df = inst.list_relations(creds, schema="public")
        assert "ef_test_widgets" in df["table"].values

    def test_describe_relation(self, adapter):
        inst, creds = adapter
        df = inst.describe_relation(creds, "ef_test_widgets")
        assert len(df) == 3
        assert list(df["column"]) == ["id", "name", "price"]
