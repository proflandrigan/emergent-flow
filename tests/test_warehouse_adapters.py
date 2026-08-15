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

    def test_columns_schema_nullable(self):
        """Nullability reflects actual nulls when the result has rows."""
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        request = QueryRequest(
            sql="SELECT 1 AS id, NULL AS nullable_col",
            dialect="duckdb",
            connection="test",
        )
        result = adapter.execute(request, {})
        by_name = {c.name: c for c in result.columns}
        assert by_name["id"].nullable is False
        assert by_name["nullable_col"].nullable is True

    def test_empty_result_reports_nullable_for_unknown(self):
        """An empty result set cannot prove nullability, so it must not claim `nullable=False`.

        Regression test: the adapter derived `nullable` as ``bool(df[col].isna().any())``,
        which on a 0-row frame is ``False`` for every column -- a [[NULLABLE]]-column query
        that returns no rows was mislabeled as non-nullable. Unknown nullability is reported
        conservatively as ``True`` instead.
        """
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        request = QueryRequest(
            sql="SELECT NULLABLE_COL_A, NULLABLE_COL_B FROM ("
            "SELECT 1 AS NULLABLE_COL_A, NULL AS NULLABLE_COL_B) WHERE 1 = 0",
            dialect="duckdb",
            connection="test",
        )
        result = adapter.execute(request, {})
        assert result.row_count == 0
        assert len(result.columns) == 2
        assert all(c.nullable is True for c in result.columns)

    def test_describe_relation_rejects_sql_injection_attempt(self):
        """A relation name containing a quote must not break out of the literal.

        Regression test: ``describe_relation`` used to interpolate ``relation``
        into the SQL string unescaped; a name containing ``'`` could inject
        arbitrary SQL into the introspection query. It must now either raise a
        (wrapped) parse/execution error or simply find no matching table --
        never silently execute injected SQL.
        """
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        malicious = "users' OR '1'='1"
        df = adapter.describe_relation({}, malicious)
        # No table can match this literal name once properly escaped.
        assert len(df) == 0

    def test_list_relations_rejects_sql_injection_attempt(self):
        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        malicious = "main' OR '1'='1"
        df = adapter.list_relations({}, schema=malicious)
        assert len(df) == 0

    def test_describe_relation_disambiguates_same_named_table_across_schemas(self, tmp_path):
        """A same-named table in two schemas must resolve to the right one when scoped.

        Regression test: describe_relation used to take only a bare relation name with
        no schema/database filter, so two same-named tables in different schemas were
        indistinguishable -- describing "users" would return whichever schema's columns
        the unfiltered query happened to match (or both, merged).
        """
        import duckdb

        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        conn.execute("CREATE SCHEMA s1")
        conn.execute("CREATE SCHEMA s2")
        conn.execute("CREATE TABLE s1.users (id INTEGER, name VARCHAR)")
        conn.execute("CREATE TABLE s2.users (id INTEGER, region VARCHAR, revenue DOUBLE)")
        conn.close()

        from emergentflow.data.warehouse.adapters.duckdb_adapter import DuckDBAdapter

        adapter = DuckDBAdapter()
        df_s1 = adapter.describe_relation({"path": db_path}, "users", schema="s1")
        df_s2 = adapter.describe_relation({"path": db_path}, "users", schema="s2")

        assert list(df_s1["column"]) == ["id", "name"]
        assert set(df_s1["schema"]) == {"s1"}
        assert list(df_s2["column"]) == ["id", "region", "revenue"]
        assert set(df_s2["schema"]) == {"s2"}


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


class TestBigQueryByteScanCap:
    """``byte_scan_cap`` must be wired to BigQuery's ``maximum_bytes_billed``.

    Regression test: ``execute`` used to gate ``maximum_bytes_billed`` on
    ``max_rows`` (setting it to ``None``, a no-op) instead of ``byte_scan_cap``,
    so the ADR-0018 scanned-bytes spend cap was silently never enforced.
    Fakes the ``google.cloud.bigquery`` module so the test runs without the
    optional driver installed.
    """

    def test_byte_scan_cap_sets_maximum_bytes_billed(self, monkeypatch):
        import emergentflow.data.warehouse.adapters.bigquery_adapter as mod

        seen_job_configs = []

        class _FakeJobConfig:
            def __init__(self, **kwargs):
                self.maximum_bytes_billed = None

        class _FakeQueryJob:
            total_bytes_processed = 42

            def to_dataframe(self):
                return pd.DataFrame({"x": [1]})

        class _FakeClient:
            def __init__(self, project=None):
                self.project = project

            def query(self, sql, job_config=None):
                seen_job_configs.append(job_config)
                return _FakeQueryJob()

        class _FakeBQ:
            QueryJobConfig = _FakeJobConfig
            Client = _FakeClient

        monkeypatch.setattr(mod, "_bq", _FakeBQ)

        adapter = mod.BigQueryAdapter()
        request = QueryRequest(
            sql="SELECT 1",
            dialect="bigquery",
            connection="test",
            max_rows=None,
            byte_scan_cap=1_000_000,
        )
        result = adapter.execute(request, {"project": "test"})

        assert result.bytes_scanned == 42
        assert len(seen_job_configs) == 1
        assert seen_job_configs[0].maximum_bytes_billed == 1_000_000

    def test_no_byte_scan_cap_leaves_maximum_bytes_billed_unset(self, monkeypatch):
        import emergentflow.data.warehouse.adapters.bigquery_adapter as mod

        seen_job_configs = []

        class _FakeJobConfig:
            def __init__(self, **kwargs):
                self.maximum_bytes_billed = None

        class _FakeQueryJob:
            total_bytes_processed = 7

            def to_dataframe(self):
                return pd.DataFrame({"x": [1]})

        class _FakeClient:
            def __init__(self, project=None):
                self.project = project

            def query(self, sql, job_config=None):
                seen_job_configs.append(job_config)
                return _FakeQueryJob()

        class _FakeBQ:
            QueryJobConfig = _FakeJobConfig
            Client = _FakeClient

        monkeypatch.setattr(mod, "_bq", _FakeBQ)

        adapter = mod.BigQueryAdapter()
        request = QueryRequest(
            sql="SELECT 1",
            dialect="bigquery",
            connection="test",
            max_rows=100,
            byte_scan_cap=None,
        )
        adapter.execute(request, {"project": "test"})

        assert len(seen_job_configs) == 1
        assert seen_job_configs[0].maximum_bytes_billed is None


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

    def test_list_relations_raises(self):
        from emergentflow.data.warehouse.adapters.redshift_adapter import RedshiftAdapter

        adapter = RedshiftAdapter()
        with pytest.raises(MissingDriverError, match="emergentflow\\[redshift\\]"):
            adapter.list_relations({"host": "x", "database": "x", "user": "x", "password": "x"})

    def test_describe_relation_raises(self):
        from emergentflow.data.warehouse.adapters.redshift_adapter import RedshiftAdapter

        adapter = RedshiftAdapter()
        with pytest.raises(MissingDriverError, match="emergentflow\\[redshift\\]"):
            adapter.describe_relation(
                {"host": "x", "database": "x", "user": "x", "password": "x"}, "some_table"
            )


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

    def test_list_relations_raises(self):
        from emergentflow.data.warehouse.adapters.postgres_adapter import PostgresAdapter

        adapter = PostgresAdapter()
        with pytest.raises(MissingDriverError, match="emergentflow\\[postgres\\]"):
            adapter.list_relations({"host": "x", "database": "x", "user": "x", "password": "x"})

    def test_describe_relation_raises(self):
        from emergentflow.data.warehouse.adapters.postgres_adapter import PostgresAdapter

        adapter = PostgresAdapter()
        with pytest.raises(MissingDriverError, match="emergentflow\\[postgres\\]"):
            adapter.describe_relation(
                {"host": "x", "database": "x", "user": "x", "password": "x"}, "some_table"
            )


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
