"""
emergentflow.nodes.examples.mann_whitney
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.mann_whitney`` — a *transform* node (1 in, 1 out).

Real, scipy-backed Mann-Whitney U rank-sum test (Epic 1, Story 8).  ``execute`` calls
``emergentflow.stats.mann_whitney`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import mann_whitney

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class MannWhitney(NodeDefinition):
    """Mann-Whitney U rank-sum test between two groups."""

    type = "stats.mann_whitney"
    version = 1
    family = "stats"
    label = "Mann-Whitney U"
    category = "Statistics"
    description = "Mann-Whitney U rank-sum test between two groups."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the group and value columns.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Mann-Whitney U test results as a one-row DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="group_col",
            type_token="str",
            required=True,
            label="Group column",
            help="Column with exactly two groups.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="value_col",
            type_token="str",
            required=True,
            label="Value column",
            help="Numeric column to compare.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="alternative",
            type_token="str",
            default="two-sided",
            label="Alternative",
            help="Direction of the alternative hypothesis.",
            hints=ValidationHints(choices=["two-sided", "less", "greater"], widget="select"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, str]:
        values = {p.name: p.value for p in node.params}
        group_col = values.get("group_col")
        value_col = values.get("value_col")
        alternative = values.get("alternative", "two-sided") or "two-sided"
        return cast(str, group_col), cast(str, value_col), cast(str, alternative)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        group_col, value_col, alternative = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.mann_whitney({ctx.in_var('frame')}, "
                f"group_col={group_col!r}, value_col={value_col!r}, "
                f"alternative={alternative!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        group_col, value_col, alternative = self._args(node)
        return {
            "result": mann_whitney(
                inputs["frame"],
                group_col=group_col,
                value_col=value_col,
                alternative=alternative,
            )
        }
