"""Per-dialect compiled-SQL golden tests for ``compile_spec`` (Epic 13 Story 5).

One representative spec (join + filter + group_by + order + limit) compiled
to BigQuery, Redshift, Postgres, and DuckDB SQL — each pinned. These are
the highest-leverage tests in the epic: they catch dialect drift from
sqlglot bumps and regression in the spec compiler.
"""

from __future__ import annotations

import pytest

from emergentflow.data.warehouse.spec_compiler import (
    SpecValidationError,
    compile_spec,
)

# ---- The representative spec ----

REPRESENTATIVE_SPEC: dict = {
    "source": "sales",
    "select": [
        "region",
        {"agg": "SUM", "column": "revenue", "alias": "total_rev"},
    ],
    "join": [
        {
            "relation": "regions",
            "on": [{"left": "sales.region_id", "right": "regions.id"}],
            "type": "LEFT",
        },
    ],
    "where": [{"column": "revenue", "op": ">", "value": 100}],
    "group_by": ["region"],
    "order_by": [{"column": "total_rev", "desc": True}],
    "limit": 50,
}


# ---- Per-dialect golden SQL ----

GOLDEN_DUCKDB = (
    "SELECT region, SUM(revenue) AS total_rev "
    "FROM sales "
    "LEFT JOIN regions ON sales.region_id = regions.id "
    "WHERE revenue > 100 "
    "GROUP BY region "
    "ORDER BY total_rev DESC "
    "LIMIT 50"
)

GOLDEN_BIGQUERY = (
    "SELECT region, SUM(revenue) AS total_rev "
    "FROM sales "
    "LEFT JOIN regions ON sales.region_id = regions.id "
    "WHERE revenue > 100 "
    "GROUP BY region "
    "ORDER BY total_rev DESC "
    "LIMIT 50"
)

GOLDEN_REDSHIFT = (
    "SELECT region, SUM(revenue) AS total_rev "
    "FROM sales "
    "LEFT JOIN regions ON sales.region_id = regions.id "
    "WHERE revenue > 100 "
    "GROUP BY region "
    "ORDER BY total_rev DESC NULLS LAST "
    "LIMIT 50"
)

GOLDEN_POSTGRES = (
    "SELECT region, SUM(revenue) AS total_rev "
    "FROM sales "
    "LEFT JOIN regions ON sales.region_id = regions.id "
    "WHERE revenue > 100 "
    "GROUP BY region "
    "ORDER BY total_rev DESC NULLS LAST "
    "LIMIT 50"
)


@pytest.mark.parametrize(
    "dialect, expected",
    [
        ("duckdb", GOLDEN_DUCKDB),
        ("bigquery", GOLDEN_BIGQUERY),
        ("redshift", GOLDEN_REDSHIFT),
        ("postgres", GOLDEN_POSTGRES),
    ],
    ids=["duckdb", "bigquery", "redshift", "postgres"],
)
def test_representative_spec_golden(dialect: str, expected: str) -> None:
    """A representative spec compiles to the pinned golden SQL for each dialect."""
    result = compile_spec(REPRESENTATIVE_SPEC, dialect)
    assert result == expected, (
        f"Golden mismatch for {dialect}:\n  expected: {expected!r}\n  got:      {result!r}"
    )


# ---- Additional spec shape tests ----


def test_select_star_when_no_select() -> None:
    """An empty select list compiles to SELECT *."""
    result = compile_spec({"source": "t"}, "duckdb")
    assert result == "SELECT * FROM t"


def test_distinct() -> None:
    """distinct=True adds SELECT DISTINCT."""
    result = compile_spec({"source": "t", "select": ["a"], "distinct": True}, "duckdb")
    assert "DISTINCT" in result.upper()
    assert result == "SELECT DISTINCT a FROM t"


def test_count_star() -> None:
    """COUNT(*) aggregate compiles correctly."""
    result = compile_spec(
        {
            "source": "orders",
            "select": [{"agg": "COUNT", "column": "*", "alias": "n"}],
        },
        "duckdb",
    )
    assert result == "SELECT COUNT(*) AS n FROM orders"


def test_multiple_where_predicates() -> None:
    """Multiple WHERE predicates are ANDed."""
    result = compile_spec(
        {
            "source": "t",
            "where": [
                {"column": "a", "op": ">", "value": 1},
                {"column": "b", "op": "=", "value": "x"},
            ],
        },
        "duckdb",
    )
    assert "a > 1" in result
    assert "b = 'x'" in result
    assert "AND" in result.upper()


def test_in_predicate() -> None:
    """IN predicate compiles correctly."""
    result = compile_spec(
        {
            "source": "t",
            "where": [{"column": "status", "op": "IN", "value": [1, 2, 3]}],
        },
        "duckdb",
    )
    assert "IN (1, 2, 3)" in result


def test_empty_in_predicate_raises() -> None:
    """An empty IN member list would compile to invalid SQL (`IN ()`), so it must be rejected."""
    with pytest.raises(SpecValidationError):
        compile_spec(
            {"source": "t", "where": [{"column": "status", "op": "IN", "value": []}]},
            "duckdb",
        )


def test_is_null_predicate() -> None:
    """IS NULL predicate compiles correctly."""
    result = compile_spec(
        {
            "source": "t",
            "where": [{"column": "name", "op": "IS NULL"}],
        },
        "duckdb",
    )
    assert "IS NULL" in result.upper()


def test_having_clause() -> None:
    """HAVING clause compiles correctly."""
    result = compile_spec(
        {
            "source": "t",
            "select": [
                "region",
                {"agg": "SUM", "column": "amount", "alias": "total"},
            ],
            "group_by": ["region"],
            "having": [{"column": "total", "op": ">", "value": 1000}],
        },
        "duckdb",
    )
    assert "HAVING" in result.upper()
    assert "total > 1000" in result


# ---- Validation error tests ----


def test_missing_source_raises() -> None:
    """A spec without 'source' raises SpecValidationError."""
    with pytest.raises(SpecValidationError, match="source"):
        compile_spec({}, "duckdb")


def test_unknown_dialect_raises() -> None:
    """An unknown dialect raises SpecValidationError."""
    with pytest.raises(SpecValidationError, match="Unknown"):
        compile_spec({"source": "t"}, "not_a_dialect")


def test_unknown_aggregate_raises() -> None:
    """An unsupported aggregate function raises SpecValidationError."""
    with pytest.raises(SpecValidationError, match="Unsupported aggregate"):
        compile_spec(
            {
                "source": "t",
                "select": [{"agg": "STDDEV", "column": "x"}],
            },
            "duckdb",
        )


def test_missing_join_relation_raises() -> None:
    """A join spec without 'relation' raises SpecValidationError."""
    with pytest.raises(SpecValidationError, match="relation"):
        compile_spec(
            {
                "source": "t",
                "join": [{"on": [{"left": "a", "right": "b"}]}],
            },
            "duckdb",
        )


def test_cross_join_compiles_without_on() -> None:
    """A CROSS join drops its (invalid) ON clause instead of emitting it.

    CROSS JOIN cannot carry an ON condition in any SQL dialect -- before the fix,
    the spec compiler emitted ``CROSS JOIN regions ON sales.region_id = regions.id``,
    which DuckDB (and every other backend) rejects with a parser error.
    """
    result = compile_spec(
        {
            "source": "sales",
            "select": ["revenue"],
            "join": [
                {
                    "relation": "regions",
                    "on": [{"left": "sales.region_id", "right": "regions.id"}],
                    "type": "CROSS",
                },
            ],
        },
        "duckdb",
    )
    assert result == "SELECT revenue FROM sales CROSS JOIN regions"
    assert " ON " not in result

    # The compiled SQL is valid and runnable on the in-process backend.
    duckdb = pytest.importorskip("duckdb")
    conn = duckdb.connect()
    conn.execute("CREATE TABLE sales (region_id INT, revenue INT)")
    conn.execute("CREATE TABLE regions (id INT)")
    conn.execute(result)


def test_cross_join_without_on_compiles() -> None:
    """A CROSS join may omit the `on` list entirely (it has no join key).

    Before the fix, a CROSS spec without `on` raised ``missing 'on' key
    conditions`` even though CROSS joins never use a join key.
    """
    result = compile_spec(
        {
            "source": "sales",
            "select": ["revenue"],
            "join": [{"relation": "regions", "type": "CROSS"}],
        },
        "duckdb",
    )
    assert result == "SELECT revenue FROM sales CROSS JOIN regions"
    assert " ON " not in result


def test_other_join_types_keep_on() -> None:
    """LEFT/RIGHT/FULL/INNER joins still carry their ON condition."""
    for join_type in ("LEFT", "RIGHT", "FULL", "INNER"):
        result = compile_spec(
            {
                "source": "sales",
                "select": ["revenue"],
                "join": [
                    {
                        "relation": "regions",
                        "on": [{"left": "sales.region_id", "right": "regions.id"}],
                        "type": join_type,
                    },
                ],
            },
            "duckdb",
        )
        assert " ON sales.region_id = regions.id" in result, result
        assert "CROSS" not in result.upper(), result
