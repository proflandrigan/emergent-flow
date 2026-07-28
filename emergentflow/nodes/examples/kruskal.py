"""
emergentflow.nodes.examples.kruskal
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.kruskal`` — a *transform* node (1 in, 1 out).

Real, scipy-backed Kruskal-Wallis H-test (Epic 1, Story 8).  ``execute`` calls
``emergentflow.stats.kruskal`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import kruskal

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Kruskal(NodeDefinition):
    """Kruskal-Wallis H-test across two or more groups."""

    type = "stats.kruskal"
    version = 1
    family = "stats"
    label = "Kruskal-Wallis"
    category = "Statistics"
    description = "Kruskal-Wallis H-test across two or more groups."

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
            help="Kruskal-Wallis test results as a one-row DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="group_col",
            type_token="str",
            required=True,
            label="Group column",
            help="Column whose distinct values define the groups.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="value_col",
            type_token="str",
            required=True,
            label="Value column",
            help="Column whose values are compared across groups.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str]:
        values = {p.name: p.value for p in node.params}
        group_col = values.get("group_col")
        value_col = values.get("value_col")
        return cast(str, group_col), cast(str, value_col)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        group_col, value_col = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.kruskal({ctx.in_var('frame')}, "
                f"group_col={group_col!r}, value_col={value_col!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        group_col, value_col = self._args(node)
        return {
            "result": kruskal(
                inputs["frame"],
                group_col=group_col,
                value_col=value_col,
            )
        }
