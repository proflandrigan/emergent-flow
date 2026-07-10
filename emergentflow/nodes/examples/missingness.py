"""
emergentflow.nodes.examples.missingness
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.missingness`` — a *transform* node (1 in, 1 out).

Real, pandas-backed per-column null analysis (Epic 12, Story 11). ``execute``
calls ``emergentflow.stats.missingness`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import missingness

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Missingness(NodeDefinition):
    """Per-column null counts and percentages."""

    type = "stats.missingness"
    version = 1
    family = "stats"
    label = "Missingness"
    category = "Statistics"
    description = "Per-column null counts and percentages."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame whose columns should be analyzed for nulls.",
        ),
        PortSpec(
            name="summary",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Per-column null analysis as a tidy DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Columns to analyze; empty/unset analyzes all columns.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str] | None]:
        values = {p.name: p.value for p in node.params}
        columns = values.get("columns")
        return (cast("list[str] | None", columns),)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        (columns,) = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('summary')} = ef.stats.missingness("
                f"{ctx.in_var('frame')}, columns={columns!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        (columns,) = self._args(node)
        return {"summary": missingness(inputs["frame"], columns=columns)}
