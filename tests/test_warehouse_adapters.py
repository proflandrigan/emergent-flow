"""Tests for warehouse adapters (Epic 13 Story 6).

DuckDB: real integration tests (hard dep, in-process).
Cloud adapters (BigQuery, Redshift, Postgres): missing-driver guard tests
(the ``[bayes]`` discipline — base install raises ``MissingDriverError``,
never an opaque ``ImportError``).
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.data.warehouse.protocol import (
    ColumnSchema,
    MissingDriverError,
    QueryRequest,
    QueryResult,
)

# ---- DuckDB integration tests ----


class TestDuckDBAdapter:
    """Real integration tests for the bundled DuckDB adapter."""

    def test_dialect(self):
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        assert DuckDBAdapter.dialect == "duckdb"

    def test_execute_in_memory(self):
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        request = QueryRequest(
            sql="SELECT 1 AS id, 'hello' AS name",
            dialect="duckdb",
            connection="test",
        )
        result = adapter.execute(request, {})
        assert isinstance(result, QueryResult)
        assert result.row_count == 1
        assert result.dialect == "duckdb"
        assert list(result.df.columns) == ["id", "name"]
        assert result.df["id"].iloc[0] == 1
        assert result.df["name"].iloc[0] == "hello"

    def test_execute_with_max_rows(self):
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        request = QueryRequest(
            sql="SELECT * FROM range(100) t(id)",
            dialect="duckdb",
            connection="test",
            max_rows=10,
        )
        result = adapter.execute(request, {})
        assert result.row_count == 10
        assert result.truncated is True

    def test_execute_not_truncated(self):
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        request = QueryRequest(
            sql="SELECT 1 AS id",
            dialect="duckdb",
            connection="test",
            max_rows=100,
        )
        result = adapter.execute(request, {})
        assert result.row_count == 1
        assert result.truncated is False

    def test_dry_run(self):
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        request = QueryRequest(
            sql="SELECT 1 AS id",
            dialect="duckdb",
            connection="test",
        )
        estimate = adapter.dry_run(request, {})
        assert estimate.dialect == "duckdb"

    def test_list_relations(self):
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        df = adapter.list_relations({})
        assert isinstance(df, pd.DataFrame)
        expected_cols = ["database", "schema", "table", "column", "data_type", "nullable"]
        assert list(df.columns) == expected_cols

    def test_describe_relation(self, tmp_path):
        """Create a real DuckDB file with a table and describe it."""
        import duckdb

        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        conn.execute("CREATE TABLE users (id INTEGER NOT NULL, name VARCHAR, age INTEGER)")
        conn.close()

        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        df = adapter.describe_relation({"path": db_path}, "users")
        assert isinstance(df, pd.DataFrame)
        expected_cols = ["database", "schema", "table", "column", "data_type", "nullable"]
        assert list(df.columns) == expected_cols
        assert len(df) == 3
        assert list(df["column"]) == ["id", "name", "age"]
        assert df["table"].iloc[0] == "users"

    def test_columns_schema(self):
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        request = QueryRequest(
            sql="SELECT 1 AS id, 'hello' AS name, 3.14 AS value",
            dialect="duckdb",
            connection="test",
        )
        result = adapter.execute(request, {})
        assert len(result.columns) == 3
        assert all(isinstance(c, ColumnSchema) for c in result.columns)
        col_names = [c.name for c in result.columns]
        assert col_names == ["id", "name", "value"]


# ---- Cloud adapter missing-driver guard tests ----


class TestBigQueryMissingDriver:
    """BigQuery adapter raises MissingDriverError when driver absent."""

    def test_dialect(self):
        from emergentflow.data.warehouse.adapters.bigquery_adapter import BigQueryAdapter

        assert BigQueryAdapter.dialect == "bigquery"

    def test_execute_raises(self):
        from emergentflow.data.warehouse.adapters.bigquery_adapter import BigQueryAdapter

        adapter = BigQueryAdapter()
        request = QueryRequest(sql="SELECT 1", dialect="bigquery", connection="test")
        with pytest.raises(MissingDriverError, match="emergentflow\\[bigquery\\]"):
            adapter.execute(request, {"project": "test"})

    def test_dry_run_raises(self):
        from emergentflow.data.warehouse.adapters.bigquery_adapter import BigQueryAdapter

        adapter = BigQueryAdapter()
        request = QueryRequest(sql="SELECT 1", dialect="bigquery", connection="test")
        with pytest.raises(MissingDriverError, match="emergentflow\\[bigquery\\]"):
            adapter.dry_run(request, {"project": "test"})

    def test_list_relations_raises(self):
        from emergentflow.data.warehouse.adapters.bigquery_adapter import BigQueryAdapter

        adapter = BigQueryAdapter()
        with pytest.raises(MissingDriverError, match="emergentflow\\[bigquery\\]"):
            adapter.list_relations({"project": "test"})

    def test_describe_relation_raises(self):
        from emergentflow.data.warehouse.adapters.bigquery_adapter import BigQueryAdapter

        adapter = BigQueryAdapter()
        with pytest.raises(MissingDriverError, match="emergentflow\\[bigquery\\]"):
            adapter.describe_relation({"project": "test"}, "some_table")


class TestRedshiftMissingDriver:
    """Redshift adapter raises MissingDriverError when driver absent."""

    def test_dialect(self):
        from emergentflow.data.warehouse.adapters.redshift_adapter import RedshiftAdapter

        assert RedshiftAdapter.dialect == "redshift"

    def test_execute_raises(self):
        from emergentflow.data.warehouse.adapters.redshift_adapter import RedshiftAdapter

        adapter = RedshiftAdapter()
        request = QueryRequest(sql="SELECT 1", dialect="redshift", connection="test")
        with pytest.raises(MissingDriverError, match="emergentflow\\[redshift\\]"):
            adapter.execute(request, {"host": "x", "database": "x", "user": "x", "password": "x"})

    def test_dry_run_raises(self):
        from emergentflow.data.warehouse.adapters.redshift_adapter import RedshiftAdapter

        adapter = RedshiftAdapter()
        request = QueryRequest(sql="SELECT 1", dialect="redshift", connection="test")
        with pytest.raises(MissingDriverError, match="emergentflow\\[redshift\\]"):
            adapter.dry_run(request, {"host": "x", "database": "x", "user": "x", "password": "x"})


class TestPostgresMissingDriver:
    """Postgres adapter raises MissingDriverError when driver absent."""

    def test_dialect(self):
        from emergentflow.data.warehouse.adapters.postgres_adapter import PostgresAdapter

        assert PostgresAdapter.dialect == "postgres"

    def test_execute_raises(self):
        from emergentflow.data.warehouse.adapters.postgres_adapter import PostgresAdapter

        adapter = PostgresAdapter()
        request = QueryRequest(sql="SELECT 1", dialect="postgres", connection="test")
        with pytest.raises(MissingDriverError, match="emergentflow\\[postgres\\]"):
            adapter.execute(request, {"host": "x", "database": "x", "user": "x", "password": "x"})

    def test_dry_run_raises(self):
        from emergentflow.data.warehouse.adapters.postgres_adapter import PostgresAdapter

        adapter = PostgresAdapter()
        request = QueryRequest(sql="SELECT 1", dialect="postgres", connection="test")
        with pytest.raises(MissingDriverError, match="emergentflow\\[postgres\\]"):
            adapter.dry_run(request, {"host": "x", "database": "x", "user": "x", "password": "x"})


# ---- Connector catalog tests ----


class TestConnectorCatalog:
    """Tests for the generated connector catalog (Epic 13 Story 6)."""

    def test_known_dialects(self):
        from emergentflow.data.warehouse.generator import known_connector_dialects

        assert known_connector_dialects() == ["bigquery", "duckdb", "postgres", "redshift"]

    def test_catalog_entries_count(self):
        from emergentflow.data.warehouse.generator import generate_connector_catalog_entries

        entries = generate_connector_catalog_entries()
        assert len(entries) == 4

    def test_catalog_entries_sorted_by_dialect(self):
        from emergentflow.data.warehouse.generator import generate_connector_catalog_entries

        entries = generate_connector_catalog_entries()
        dialects = [e["dialect"] for e in entries]
        assert dialects == sorted(dialects)

    def test_each_entry_has_required_keys(self):
        from emergentflow.data.warehouse.generator import generate_connector_catalog_entries

        required_keys = {"dialect", "label", "extra", "adapter", "description", "auth_schema"}
        entries = generate_connector_catalog_entries()
        for entry in entries:
            assert set(entry) >= required_keys, f"Entry {entry['dialect']} missing keys"

    def test_duckdb_is_bundled(self):
        from emergentflow.data.warehouse.generator import generate_connector_catalog_entries

        entries = generate_connector_catalog_entries()
        duckdb_entry = [e for e in entries if e["dialect"] == "duckdb"][0]
        assert duckdb_entry["extra"] is None  # bundled, no extra needed

    def test_cloud_connectors_have_extras(self):
        from emergentflow.data.warehouse.generator import generate_connector_catalog_entries

        entries = generate_connector_catalog_entries()
        for entry in entries:
            if entry["dialect"] != "duckdb":
                assert entry["extra"] is not None
                assert entry["extra"].startswith("emergentflow[")

    def test_deterministic(self):
        from emergentflow.data.warehouse.generator import generate_connector_catalog_entries

        assert generate_connector_catalog_entries() == generate_connector_catalog_entries()
