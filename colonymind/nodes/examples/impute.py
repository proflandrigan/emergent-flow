"""
colonymind.nodes.examples.impute
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.impute_missing`` — a *transform* node (1 in, 1 out).

Exercises the richer shape of the contract: an IN port, an enum param with a
``choices`` validation hint, an optional list param, and a non-trivial executor.
A table is a ``list[dict[str, str]]`` (matching ``data.load_csv``); the real
pandas-backed cleaner is Story 8.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from colonymind.ir.common import Direction
from colonymind.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

STRATEGIES = ["mean", "median", "most_frequent"]


def _is_missing(value: Any) -> bool:
    """A cell is missing if it is None or an empty/whitespace string."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def _fill_value(values: list[Any], strategy: str) -> Any:
    """Compute the imputation fill value for *values* under *strategy*."""
    if strategy == "most_frequent":
        return Counter(values).most_common(1)[0][0]
    numbers = sorted(float(v) for v in values)
    if strategy == "mean":
        return sum(numbers) / len(numbers)
    if strategy == "median":
        mid = len(numbers) // 2
        if len(numbers) % 2:
            return numbers[mid]
        return (numbers[mid - 1] + numbers[mid]) / 2
    raise ValueError(f"unknown impute strategy {strategy!r}; expected one of {STRATEGIES!r}.")


def impute_missing(
    table: list[dict[str, Any]],
    strategy: str = "mean",
    columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fill missing cells in *table* per *strategy* (the shared runtime helper).

    Both ``ImputeMissing.execute`` and the code emitted by
    ``ImputeMissing.codegen`` call this, so the two paths are equivalent by
    construction (ADR 0002).  ``columns=None`` (or empty) imputes every column.
    """
    if not table:
        return []
    cols = columns if columns else list(table[0].keys())
    result = [dict(row) for row in table]
    for col in cols:
        present = [r[col] for r in result if col in r and not _is_missing(r[col])]
        if not present:
            continue
        fill = _fill_value(present, strategy)
        for row in result:
            if col not in row or _is_missing(row[col]):
                row[col] = fill
    return result


@register
class ImputeMissing(NodeDefinition):
    """Impute missing values in a table column-wise."""

    type = "clean.impute_missing"
    version = 1
    family = "clean"
    label = "Impute Missing"

    ports = [
        PortSpec(
            name="table",
            direction=Direction.IN,
            data_type="Table",
            help="The input table whose missing cells should be filled.",
        ),
        PortSpec(
            name="table",
            direction=Direction.OUT,
            data_type="Table",
            help="The table with missing cells imputed.",
        ),
    ]
    params = [
        ParamSpec(
            name="strategy",
            type_token="str",
            default="mean",
            label="Strategy",
            help="How to compute each column's fill value.",
            hints=ValidationHints(choices=list(STRATEGIES), widget="select"),
        ),
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Columns to impute; empty/unset imputes every column.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, list[str] | None]:
        values = {p.name: p.value for p in node.params}
        strategy = values.get("strategy", "mean") or "mean"
        columns = values.get("columns")
        return strategy, columns

    def codegen(self, node: Node) -> CodeFragment:
        strategy, columns = self._args(node)
        return CodeFragment(
            imports=["from colonymind.nodes.examples.impute import impute_missing"],
            body=(
                f"table = impute_missing(table, strategy={strategy!r}, "
                f"columns={columns!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        strategy, columns = self._args(node)
        table = inputs["table"]
        return {"table": impute_missing(table, strategy=strategy, columns=columns)}
