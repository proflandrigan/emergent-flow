"""
emergentflow.nodes.examples.group_by_aggregate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.group_by_aggregate`` — a *transform* node (1 in, 1 out).

Real, pandas-backed split-apply-combine (Epic 12, Story 11). ``execute`` calls
``emergentflow.stats.group_by_aggregate`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import group_by_aggregate

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class GroupByAggregate(NodeDefinition):
    """Split-apply-combine: group by column(s) and aggregate."""

    type = "stats.group_by_aggregate"
    version = 2
    family = "stats"
    label = "Group By Aggregate"
    category = "Statistics"
    description = "Split-apply-combine: group by column(s) and aggregate."

    column_effect = ColumnEffect(kind=ColumnEffectKind.AGGREGATE)

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to group and aggregate.",
        ),
        PortSpec(
            name="summary",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Aggregated result as a tidy DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="by",
            type_token="list[str]",
            required=True,
            label="Group by",
            help="Grouping column(s).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="aggs",
            type_token="list[str]",
            default=None,
            label="Aggregations",
            help="One or more aggregation functions applied to every value column.",
            hints=ValidationHints(
                choices=["mean", "sum", "min", "max", "median", "count", "std", "var"],
                widget="multiselect",
            ),
        ),
        ParamSpec(
            name="custom_aggs",
            type_token="list[str]",
            default=None,
            label="Custom aggregations",
            help=(
                "Names of callables registered via ef.stats.register_aggregation, "
                "applied alongside the builtin aggregations."
            ),
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="agg",
            type_token="str",
            default="mean",
            label="Aggregation (single, legacy)",
            help="Single aggregation function. Ignored when `aggs`/`custom_aggs` are set.",
            hints=ValidationHints(
                choices=["mean", "sum", "min", "max", "median", "count", "std"],
                widget="select",
            ),
        ),
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Value columns",
            help="Columns to aggregate; unset aggregates all numeric non-group columns.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str], str | list[str], list[str] | None]:
        values = {p.name: p.value for p in node.params}
        by = values.get("by")
        columns = values.get("columns")
        raw_aggs = values.get("aggs")
        raw_custom = values.get("custom_aggs")
        multi: list[str] = []
        if isinstance(raw_aggs, list):
            multi.extend(cast("list[str]", raw_aggs))
        if isinstance(raw_custom, list):
            multi.extend(cast("list[str]", raw_custom))
        agg: str | list[str] = multi if multi else (cast("str", values.get("agg") or "mean"))
        return (
            cast("list[str]", by),
            agg,
            cast("list[str] | None", columns),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        by, agg, columns = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('summary')} = ef.stats.group_by_aggregate("
                f"{ctx.in_var('frame')}, by={by!r}, agg={agg!r}, columns={columns!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        by, agg, columns = self._args(node)
        return {"summary": group_by_aggregate(inputs["frame"], by=by, agg=agg, columns=columns)}
