"""
emergentflow.data.warehouse.spec_compiler
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pure ``compile_spec(spec, dialect) -> str``: compiles a structured query spec
(the visual query builder's output) to dialect-specific SQL via sqlglot AST
building (Epic 13 Story 5, ADR 0002).

ONE function, ONE place — both ``codegen`` and ``execute`` route through
``ef.data.query(spec=...)`` which calls this, so the two paths can never build
the SQL differently. The UI's live SQL preview calls the same function.
"""

from __future__ import annotations

from typing import Any

from sqlglot import exp
from sqlglot.dialects.dialect import Dialect

__all__ = ["compile_spec", "SpecValidationError"]


class SpecValidationError(ValueError):
    """Raised when a structured query spec is invalid or incomplete."""


def _validate_dialect(dialect: str) -> None:
    try:
        Dialect.get_or_raise(dialect)
    except ValueError as exc:
        raise SpecValidationError(
            f"Unknown SQL dialect {dialect!r}. "
            f"Supported: 'duckdb', 'bigquery', 'redshift', 'postgres'."
        ) from exc


def _parse_column_ref(col: str) -> exp.Expression:
    """Parse a column reference like ``"revenue"`` or ``"t.revenue"`` into a sqlglot Column."""
    parts = col.split(".")
    if len(parts) == 2:
        return exp.Column(this=exp.to_identifier(parts[1]), table=exp.to_identifier(parts[0]))
    return exp.Column(this=exp.to_identifier(col))


def _build_select_expression(item: str | dict) -> exp.Expression:
    """Build a SELECT expression from a spec item.

    A string is a plain column reference. A dict can be:
    - {"column": "revenue", "alias": "total_rev"} — aliased column
    - {"agg": "SUM", "column": "revenue"} — aggregate
    - {"agg": "SUM", "column": "revenue", "alias": "total_rev"} — aliased aggregate
    - {"agg": "COUNT", "column": "*"} — COUNT(*)
    """
    if isinstance(item, str):
        return _parse_column_ref(item)

    if not isinstance(item, dict):
        raise SpecValidationError(
            f"select item must be a string or dict, got {type(item).__name__}"
        )

    agg = item.get("agg")
    column = item.get("column", "*")
    alias = item.get("alias")

    if agg:
        agg_upper = agg.upper()
        inner = exp.Star() if column == "*" else _parse_column_ref(column)

        agg_map = {
            "SUM": exp.Sum,
            "AVG": exp.Avg,
            "COUNT": exp.Count,
            "MIN": exp.Min,
            "MAX": exp.Max,
        }
        agg_cls = agg_map.get(agg_upper)
        if agg_cls is None:
            raise SpecValidationError(
                f"Unsupported aggregate function {agg!r}. Supported: {sorted(agg_map.keys())!r}"
            )
        node: exp.Expression = agg_cls(this=inner)
    else:
        node = _parse_column_ref(column)

    if alias:
        return exp.Alias(this=node, alias=exp.to_identifier(alias))
    return node


_OP_MAP = {
    "=": exp.EQ,
    "!=": exp.NEQ,
    "<>": exp.NEQ,
    "<": exp.LT,
    "<=": exp.LTE,
    ">": exp.GT,
    ">=": exp.GTE,
}


def _build_predicate(pred: dict) -> exp.Expression:
    """Build a WHERE/HAVING predicate from a spec dict.

    Format: {"column": "revenue", "op": ">", "value": 100}
    Also supports: {"column": "name", "op": "IS NULL"} and
    {"column": "name", "op": "IS NOT NULL"} and
    {"column": "name", "op": "IN", "value": [1, 2, 3]} and
    {"column": "name", "op": "LIKE", "value": "%foo%"} and
    {"column": "name", "op": "BETWEEN", "value": [10, 20]}
    """
    col = pred.get("column")
    op = pred.get("op", "=")
    value = pred.get("value")

    if not col:
        raise SpecValidationError("Predicate missing 'column' key.")

    col_expr = _parse_column_ref(col)
    op_upper = op.upper().strip()

    if op_upper == "IS NULL":
        return exp.Is(this=col_expr, expression=exp.Null())
    if op_upper == "IS NOT NULL":
        return exp.Not(this=exp.Is(this=col_expr, expression=exp.Null()))
    if op_upper == "IN":
        if not isinstance(value, list):
            raise SpecValidationError(
                f"IN predicate requires a list value, got {type(value).__name__}"
            )
        literals = [
            exp.Literal.number(v) if isinstance(v, (int, float)) else exp.Literal.string(str(v))
            for v in value
        ]
        return exp.In(this=col_expr, expressions=literals)
    if op_upper == "LIKE":
        return exp.Like(this=col_expr, expression=exp.Literal.string(str(value)))
    if op_upper == "BETWEEN":
        if not isinstance(value, list) or len(value) != 2:
            raise SpecValidationError("BETWEEN predicate requires a 2-element list value.")
        low = (
            exp.Literal.number(value[0])
            if isinstance(value[0], (int, float))
            else exp.Literal.string(str(value[0]))
        )
        high = (
            exp.Literal.number(value[1])
            if isinstance(value[1], (int, float))
            else exp.Literal.string(str(value[1]))
        )
        return exp.Between(this=col_expr, low=low, high=high)

    cmp_cls = _OP_MAP.get(op)
    if cmp_cls is None:
        raise SpecValidationError(
            f"Unsupported operator {op!r}. Supported: {sorted(_OP_MAP.keys())!r}"
        )

    val_expr: exp.Expression
    if isinstance(value, (int, float)):
        val_expr = exp.Literal.number(value)
    elif isinstance(value, str):
        val_expr = exp.Literal.string(value)
    elif value is None:
        val_expr = exp.Null()
    else:
        val_expr = exp.Literal.string(str(value))

    return cmp_cls(this=col_expr, expression=val_expr)


def _build_join(
    join_spec: dict, *, join_type: str = "INNER"
) -> tuple[exp.Expression, exp.Expression | None]:
    """Build a JOIN clause from a spec dict.

    Format: {"relation": "regions", "on": [{"left": "sales.region_id", "right": "regions.id"}],
             "type": "LEFT"}
    Returns (table_expr, on_condition). ``on_condition`` is ``None`` for a CROSS join
    (which has no join key -- an ``on`` list is optional and never emitted as SQL).
    """
    relation = join_spec.get("relation")
    if not relation:
        raise SpecValidationError("Join spec missing 'relation' key.")
    table_expr = exp.Table(this=exp.to_identifier(relation))

    if join_type == "CROSS":
        return table_expr, None

    on_keys = join_spec.get("on", [])
    if not on_keys:
        raise SpecValidationError(f"Join on {relation!r} missing 'on' key conditions.")

    conditions = []
    for pair in on_keys:
        left = _parse_column_ref(pair["left"])
        right = _parse_column_ref(pair["right"])
        conditions.append(exp.EQ(this=left, expression=right))

    on_cond: exp.Expression = conditions[0]
    for c in conditions[1:]:
        on_cond = exp.And(this=on_cond, expression=c)

    return table_expr, on_cond


def compile_spec(spec: dict[str, Any], dialect: str) -> str:
    """Compile a structured query spec to dialect-specific SQL.

    Parameters
    ----------
    spec:
        The structured query spec with keys: ``source``, ``select``, ``where``,
        ``join``, ``group_by``, ``having``, ``order_by``, ``limit``, ``distinct``.
    dialect:
        A sqlglot dialect key (e.g. ``"duckdb"``, ``"bigquery"``).

    Returns
    -------
    str
        The compiled SQL string in the target dialect.

    Raises
    ------
    SpecValidationError
        If the spec is invalid or incomplete.
    """
    _validate_dialect(dialect)

    source = spec.get("source")
    if not source:
        raise SpecValidationError("Query spec missing 'source' (the base relation).")

    # FROM
    from_expr = exp.Table(this=exp.to_identifier(source))
    select_node = exp.Select().from_(from_expr)

    # SELECT
    select_items = spec.get("select", [])
    if not select_items:
        select_node = select_node.select(exp.Star())
    else:
        for item in select_items:
            select_node = select_node.select(_build_select_expression(item))

    # DISTINCT
    if spec.get("distinct"):
        select_node.args["distinct"] = exp.Distinct()

    # JOINs
    for join_spec in spec.get("join", []):
        join_type = join_spec.get("type", "INNER").upper()
        table_expr, on_cond = _build_join(join_spec, join_type=join_type)

        # Map join type strings to sqlglot join kwargs. A CROSS JOIN cannot carry an
        # ON clause (invalid SQL in every dialect) -- the spec's `on` conditions are
        # dropped for it rather than emitted. LEFT/RIGHT/FULL and the INNER default
        # keep the ON condition.
        join_kwargs: dict[str, Any] = {}
        if join_type == "CROSS":
            join_kwargs["join_type"] = "CROSS"
        elif join_type in ("LEFT", "RIGHT", "FULL"):
            join_kwargs["join_type"] = join_type
            if on_cond is None:
                raise RuntimeError(
                    f"Internal error: _build_join returned None on_cond for {join_type} join"
                )
            join_kwargs["on"] = on_cond
        else:
            # INNER is the default (no join_type kwarg needed).
            if on_cond is None:
                raise RuntimeError(
                    f"Internal error: _build_join returned None on_cond for {join_type} join"
                )
            join_kwargs["on"] = on_cond

        select_node = select_node.join(table_expr, **join_kwargs)

    # WHERE
    where_preds = spec.get("where", [])
    for pred in where_preds:
        select_node = select_node.where(_build_predicate(pred))

    # GROUP BY
    group_by_cols = spec.get("group_by", [])
    for col in group_by_cols:
        select_node = select_node.group_by(_parse_column_ref(col))

    # HAVING
    having_preds = spec.get("having", [])
    for pred in having_preds:
        select_node = select_node.having(_build_predicate(pred))

    # ORDER BY
    order_by_items = spec.get("order_by", [])
    for item in order_by_items:
        if isinstance(item, str):
            select_node = select_node.order_by(_parse_column_ref(item))
        elif isinstance(item, dict):
            col_expr = _parse_column_ref(item["column"])
            desc = item.get("desc", False)
            if desc:
                col_expr = exp.Ordered(this=col_expr, desc=True)
            select_node = select_node.order_by(col_expr)

    # LIMIT
    limit_val = spec.get("limit")
    if limit_val is not None:
        select_node = select_node.limit(limit_val)

    return select_node.sql(dialect=dialect)
