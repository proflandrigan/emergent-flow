"""Tests for ``emergentflow.data.warehouse.query`` (``ef.data.query``)."""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from emergentflow.data.warehouse.protocol import ColumnSchema, QueryRequest, QueryResult
from emergentflow.data.warehouse.query import (
    MissingWarehouseClientError,
    QueryParseError,
    ReadOnlyViolationError,
    UnknownDialectError,
    query,
)
from emergentflow.data.warehouse.replay import ReplayWarehouseClient, write_fixture


class _RejectingClient:
    """A stub client whose ``run`` must never be reached in rejection tests."""

    def run(self, request: QueryRequest) -> QueryResult:
        raise AssertionError("run() should not be reached; validation must precede the effect")


class _SpyClient:
    """Records the ``QueryRequest`` it receives and returns a fixed ``QueryResult``."""

    def __init__(self) -> None:
        self.requests: list[QueryRequest] = []

    def run(self, request: QueryRequest) -> QueryResult:
        self.requests.append(request)
        df = pd.DataFrame({"x": [1]})
        return QueryResult(
            df=df,
            row_count=1,
            columns=(ColumnSchema(name="x", dtype="int64", nullable=False),),
            dialect=request.dialect,
        )


def _make_result() -> QueryResult:
    df = pd.DataFrame({"x": [1]})
    return QueryResult(
        df=df,
        row_count=1,
        columns=(ColumnSchema(name="x", dtype="int64", nullable=False),),
        dialect="duckdb",
    )


def test_query_requires_client() -> None:
    with pytest.raises(MissingWarehouseClientError):
        query(sql="SELECT 1", dialect="duckdb", connection="c", client=None)


def test_query_unknown_dialect_raises() -> None:
    with pytest.raises(UnknownDialectError):
        query(
            sql="SELECT 1",
            dialect="not_a_dialect",
            connection="c",
            client=_RejectingClient(),
        )


def test_query_rejects_delete_under_read_only() -> None:
    with pytest.raises(ReadOnlyViolationError):
        query(
            sql="DELETE FROM t",
            dialect="duckdb",
            connection="c",
            client=_RejectingClient(),
            read_only=True,
        )


def test_query_rejects_drop_under_read_only() -> None:
    with pytest.raises(ReadOnlyViolationError):
        query(
            sql="DROP TABLE t",
            dialect="duckdb",
            connection="c",
            client=_RejectingClient(),
            read_only=True,
        )


def test_query_allows_select_and_routes_through_run(tmp_path) -> None:
    expected_request = QueryRequest(
        sql="SELECT 1 AS x",
        dialect="duckdb",
        connection="c",
        params=(),
        max_rows=None,
        byte_scan_cap=None,
        read_only=True,
        dry_run=False,
    )
    result = _make_result()
    write_fixture(tmp_path, expected_request, result)

    returned = query(
        sql="SELECT 1 AS x",
        dialect="duckdb",
        connection="c",
        client=ReplayWarehouseClient(tmp_path),
    )

    assert_frame_equal(returned.df, result.df)
    assert returned.row_count == result.row_count
    assert returned.dialect == result.dialect


def test_query_allows_with_and_union(tmp_path) -> None:
    result = _make_result()

    with_sql = "WITH t AS (SELECT 1) SELECT * FROM t"
    with_request = QueryRequest(
        sql=with_sql,
        dialect="duckdb",
        connection="c",
        params=(),
        max_rows=None,
        byte_scan_cap=None,
        read_only=True,
        dry_run=False,
    )
    write_fixture(tmp_path, with_request, result)
    query(sql=with_sql, dialect="duckdb", connection="c", client=ReplayWarehouseClient(tmp_path))

    union_sql = "SELECT a FROM t UNION SELECT a FROM u"
    union_request = QueryRequest(
        sql=union_sql,
        dialect="duckdb",
        connection="c",
        params=(),
        max_rows=None,
        byte_scan_cap=None,
        read_only=True,
        dry_run=False,
    )
    write_fixture(tmp_path, union_request, result)
    query(sql=union_sql, dialect="duckdb", connection="c", client=ReplayWarehouseClient(tmp_path))


def test_query_bad_sql_raises_parse_error() -> None:
    with pytest.raises(QueryParseError):
        query(
            sql="SELECT FROM WHERE",
            dialect="duckdb",
            connection="c",
            client=_RejectingClient(),
        )


def test_query_spec_path_compiles_and_routes() -> None:
    spy = _SpyClient()
    query(
        spec={"source": "t", "select": ["a"]},
        dialect="duckdb",
        connection="c",
        client=spy,
    )
    assert len(spy.requests) == 1
    assert "SELECT a FROM t" in spy.requests[0].sql


def test_query_requires_exactly_one_of_sql_or_spec() -> None:
    with pytest.raises(ValueError):
        query(dialect="duckdb", connection="c", client=_RejectingClient())

    with pytest.raises(ValueError):
        query(
            sql="SELECT 1",
            spec={"source": "t"},
            dialect="duckdb",
            connection="c",
            client=_RejectingClient(),
        )


def test_query_content_hash_stable_across_calls() -> None:
    spy = _SpyClient()

    query(sql="SELECT 1 AS x", dialect="duckdb", connection="c", client=spy)
    query(sql="SELECT 1 AS x", dialect="duckdb", connection="c", client=spy)

    assert len(spy.requests) == 2
    first, second = spy.requests
    assert first.content_hash() == second.content_hash()
    assert first.sql == "SELECT 1 AS x"
    assert second.sql == "SELECT 1 AS x"


def test_ef_data_query_accessible() -> None:
    import emergentflow as ef

    assert callable(ef.data.query)


def test_query_injects_limit_when_absent() -> None:
    spy = _SpyClient()
    query(sql="SELECT x FROM t", dialect="duckdb", connection="c", client=spy, max_rows=100)
    assert len(spy.requests) == 1
    assert "LIMIT 100" in spy.requests[0].sql.upper()


def test_query_preserves_existing_limit() -> None:
    spy = _SpyClient()
    query(
        sql="SELECT x FROM t LIMIT 50",
        dialect="duckdb",
        connection="c",
        client=spy,
        max_rows=100,
    )
    assert len(spy.requests) == 1
    # The existing LIMIT 50 should be preserved, not replaced with 100
    req_sql_upper = spy.requests[0].sql.upper()
    assert "LIMIT 50" in req_sql_upper


def test_query_no_limit_injection_when_max_rows_none() -> None:
    spy = _SpyClient()
    query(sql="SELECT x FROM t", dialect="duckdb", connection="c", client=spy, max_rows=None)
    assert len(spy.requests) == 1
    assert "LIMIT" not in spy.requests[0].sql.upper()


def test_query_injects_limit_when_only_a_subquery_has_one() -> None:
    """A LIMIT nested in a subquery must not be mistaken for the outer query's own LIMIT.

    Regression test: ``_inject_limit`` used to call ``stmt.find(exp.Limit)``, which
    recurses into subqueries; a subquery LIMIT made the outer, unbounded statement
    look like it already had a cap, silently bypassing max_rows.
    """
    spy = _SpyClient()
    query(
        sql="SELECT * FROM (SELECT x FROM t LIMIT 5) sub",
        dialect="duckdb",
        connection="c",
        client=spy,
        max_rows=100,
    )
    assert len(spy.requests) == 1
    sql_upper = spy.requests[0].sql.upper()
    assert "LIMIT 100" in sql_upper
    assert "LIMIT 5" in sql_upper  # the subquery's own LIMIT is left untouched
