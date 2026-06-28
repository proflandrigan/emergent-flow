"""
emergentflow.nodes.examples.ttest
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.ttest`` — a *transform* node (1 in, 1 out).

Real, scipy-backed two-sample t-test (Epic 6). ``execute`` calls
``emergentflow.stats.ttest`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import ttest

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TTest(NodeDefinition):
    """Perform a two-sample t-test between two groups in a column."""

    type = "stats.ttest"
    version = 1
    family = "stats"
    label = "T-Test"
    category = "Statistics"
    description = "Two-sample t-test between two groups."

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
            data_type="TTestResult",
            help="Inspectable two-sample t-test metrics.",
        ),
    ]
    params = [
        ParamSpec(
            name="group_col",
            type_token="str",
            required=True,
            label="Group column",
            help="Column with exactly two groups.",
        ),
        ParamSpec(
            name="value_col",
            type_token="str",
            required=True,
            label="Value column",
            help="Numeric column to compare.",
        ),
        ParamSpec(
            name="equal_var",
            type_token="bool",
            default=True,
            label="Equal variance",
            help="Assume equal variance (Student's); off = Welch's.",
            hints=ValidationHints(widget="checkbox"),
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

    def _args(self, node: Node) -> tuple[str, str, bool, float]:
        values = {p.name: p.value for p in node.params}
        group_col = values.get("group_col")
        value_col = values.get("value_col")
        equal_var = values.get("equal_var", True)
        if equal_var is None:
            equal_var = True
        alpha = values.get("alpha", 0.05)
        if alpha is None:
            alpha = 0.05
        return cast(str, group_col), cast(str, value_col), cast(bool, equal_var), cast(float, alpha)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        group_col, value_col, equal_var, alpha = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.ttest({ctx.in_var('frame')}, "
                f"group_col={group_col!r}, value_col={value_col!r}, "
                f"equal_var={equal_var!r}, alpha={alpha!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        group_col, value_col, equal_var, alpha = self._args(node)
        return {
            "result": ttest(
                inputs["frame"],
                group_col=group_col,
                value_col=value_col,
                equal_var=equal_var,
                alpha=alpha,
            )
        }
