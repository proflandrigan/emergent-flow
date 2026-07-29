"""
emergentflow.nodes.examples.chi_square
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.chi_square`` — a *transform* node (1 in, 1 out).

Real, scipy-backed chi-square test of independence (Epic 1, Story 8).  ``execute`` calls
``emergentflow.stats.chi_square`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import chi_square

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ChiSquare(NodeDefinition):
    """Chi-square test of independence on a contingency table."""

    type = "stats.chi_square"
    version = 1
    family = "stats"
    label = "Chi-Square Test"
    category = "Statistics"
    description = "Chi-square test of independence on a contingency table."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the two categorical columns.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Chi-square test results as a one-row DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="row_col",
            type_token="str",
            required=True,
            label="Row column",
            help="Column whose values form the rows of the contingency table.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="col_col",
            type_token="str",
            required=True,
            label="Column column",
            help="Column whose values form the columns of the contingency table.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="correction",
            type_token="bool",
            default=True,
            label="Yates correction",
            help="Apply Yates's continuity correction.",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, bool]:
        values = {p.name: p.value for p in node.params}
        row_col = values.get("row_col")
        col_col = values.get("col_col")
        correction = values.get("correction", True)
        if correction is None:
            correction = True
        return cast(str, row_col), cast(str, col_col), cast(bool, correction)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        row_col, col_col, correction = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.chi_square({ctx.in_var('frame')}, "
                f"row_col={row_col!r}, col_col={col_col!r}, "
                f"correction={correction!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        row_col, col_col, correction = self._args(node)
        return {
            "result": chi_square(
                inputs["frame"],
                row_col=row_col,
                col_col=col_col,
                correction=correction,
            )
        }
