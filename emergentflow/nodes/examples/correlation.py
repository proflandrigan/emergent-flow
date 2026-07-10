"""
emergentflow.nodes.examples.correlation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.correlation`` — a *transform* node (1 in, 1 out).

Real, pandas-backed correlation analysis (Epic 6, Story 4). ``execute`` calls
``emergentflow.stats.correlation`` directly and the code emitted by ``codegen``
calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent
by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import CORR_METHODS, correlation

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Correlation(NodeDefinition):
    """Compute a pairwise correlation matrix."""

    type = "stats.correlation"
    version = 1
    family = "stats"
    label = "Correlation"
    category = "Statistics"
    description = "Compute a pairwise correlation matrix."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame whose columns should be correlated.",
        ),
        PortSpec(
            name="matrix",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Correlation matrix as a tidy DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="method",
            type_token="str",
            default="pearson",
            label="Method",
            help="Correlation method to use.",
            hints=ValidationHints(choices=list(CORR_METHODS), widget="select"),
        ),
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Columns to correlate; empty/unset correlates all numeric columns.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, list[str] | None]:
        values = {p.name: p.value for p in node.params}
        method = values.get("method", "pearson") or "pearson"
        columns = values.get("columns")
        return cast(str, method), cast("list[str] | None", columns)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        method, columns = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('matrix')} = ef.stats.correlation("
                f"{ctx.in_var('frame')}, method={method!r}, columns={columns!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        method, columns = self._args(node)
        return {"matrix": correlation(inputs["frame"], method=method, columns=columns)}
