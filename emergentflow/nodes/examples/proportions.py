"""
emergentflow.nodes.examples.proportions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.test_proportions`` — a *transform* node (1 in, 1 out).

Real, statsmodels-backed two-proportion z-test (Epic 6). ``execute`` calls
``emergentflow.stats.test_proportions`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import test_proportions

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TestProportions(NodeDefinition):
    """Perform a two-proportion z-test between two groups in a binary column."""

    type = "stats.test_proportions"
    version = 1
    family = "stats"
    label = "Test Proportions"
    category = "Statistics"
    description = "Two-proportion z-test comparing a binary outcome across two groups."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the group and success columns.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Inspectable two-proportion z-test metrics.",
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
            name="success_col",
            type_token="str",
            required=True,
            label="Success column",
            help="Binary outcome column (0/1/True/False).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="alpha",
            type_token="float",
            default=0.05,
            label="Alpha",
            help="Significance level used for the confidence interval.",
            hints=ValidationHints(min=0.0, max=1.0, widget="number"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, float]:
        values = {p.name: p.value for p in node.params}
        group_col = values.get("group_col")
        success_col = values.get("success_col")
        alpha = values.get("alpha", 0.05)
        if alpha is None:
            alpha = 0.05
        return cast(str, group_col), cast(str, success_col), cast(float, alpha)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        group_col, success_col, alpha = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.test_proportions({ctx.in_var('frame')}, "
                f"group_col={group_col!r}, success_col={success_col!r}, alpha={alpha!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        group_col, success_col, alpha = self._args(node)
        return {
            "result": test_proportions(
                inputs["frame"],
                group_col=group_col,
                success_col=success_col,
                alpha=alpha,
            )
        }
