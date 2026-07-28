"""
emergentflow.nodes.examples.wilcoxon
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.wilcoxon`` — a *transform* node (1 in, 1 out).

Real, scipy-backed Wilcoxon signed-rank test for paired samples (Epic 1, Story 8).
``execute`` calls ``emergentflow.stats.wilcoxon`` directly and the code emitted by ``codegen``
calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import wilcoxon

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Wilcoxon(NodeDefinition):
    """Wilcoxon signed-rank test for paired samples in two columns."""

    type = "stats.wilcoxon"
    version = 1
    family = "stats"
    label = "Wilcoxon Signed-Rank"
    category = "Statistics"
    description = "Wilcoxon signed-rank test for paired samples in two columns."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the two paired columns.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Wilcoxon signed-rank test results as a one-row DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="col_a",
            type_token="str",
            required=True,
            label="Column A",
            help="First paired column.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="col_b",
            type_token="str",
            required=True,
            label="Column B",
            help="Second paired column.",
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
        col_a = values.get("col_a")
        col_b = values.get("col_b")
        alternative = values.get("alternative", "two-sided") or "two-sided"
        return cast(str, col_a), cast(str, col_b), cast(str, alternative)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        col_a, col_b, alternative = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.wilcoxon({ctx.in_var('frame')}, "
                f"col_a={col_a!r}, col_b={col_b!r}, "
                f"alternative={alternative!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        col_a, col_b, alternative = self._args(node)
        return {
            "result": wilcoxon(
                inputs["frame"],
                col_a=col_a,
                col_b=col_b,
                alternative=alternative,
            )
        }
