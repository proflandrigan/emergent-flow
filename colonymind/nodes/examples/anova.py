"""
colonymind.nodes.examples.anova
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.anova`` — a *transform* node (1 in, 1 out).

Real, statsmodels-backed one-way ANOVA (Epic 1, Story 8). ``execute`` calls
``colonymind.stats.anova`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``cm.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from colonymind.ir.common import Direction
from colonymind.ir.node import Node
from colonymind.stats import anova

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from colonymind.codegen.context import CodegenContext


@register
class Anova(NodeDefinition):
    """Perform a one-way ANOVA of a value column across groups."""

    type = "stats.anova"
    version = 2
    family = "stats"
    label = "ANOVA"
    category = "Statistics"
    description = "One-way ANOVA testing a numeric column across groups."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the group and value columns.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="AnovaResult",
            help="The structured ANOVA result.",
        ),
    ]
    params = [
        ParamSpec(
            name="group_col",
            type_token="str",
            required=True,
            label="Group column",
            help="Column whose distinct values define the groups.",
        ),
        ParamSpec(
            name="value_col",
            type_token="str",
            required=True,
            label="Value column",
            help="Column whose values are compared across groups.",
        ),
        ParamSpec(
            name="alpha",
            type_token="float",
            default=0.05,
            label="Alpha",
            help="Significance level recorded alongside the result.",
            hints=ValidationHints(min=0.0, max=1.0, widget="number"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, float]:
        values = {p.name: p.value for p in node.params}
        group_col = values.get("group_col")
        value_col = values.get("value_col")
        alpha = values.get("alpha", 0.05)
        if alpha is None:
            alpha = 0.05
        return cast(str, group_col), cast(str, value_col), cast(float, alpha)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        group_col, value_col, alpha = self._args(node)
        return CodeFragment(
            imports=["import colonymind as cm"],
            body=(
                f"{ctx.out_var('result')} = cm.stats.anova({ctx.in_var('frame')}, "
                f"group_col={group_col!r}, value_col={value_col!r}, alpha={alpha!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        group_col, value_col, alpha = self._args(node)
        return {
            "result": anova(
                inputs["frame"],
                group_col=group_col,
                value_col=value_col,
                alpha=alpha,
            )
        }
