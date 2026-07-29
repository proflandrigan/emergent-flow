"""
emergentflow.nodes.examples.crosstab
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.crosstab`` — a *transform* node (1 in, 1 out).

Real, pandas/scipy-backed cross-tabulation (Epic 6). ``execute`` calls
``emergentflow.stats.crosstab`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import crosstab

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Crosstab(NodeDefinition):
    """Cross-tabulate two categorical columns into counts (or normalized proportions)."""

    type = "stats.crosstab"
    version = 1
    family = "stats"
    label = "Crosstab"
    category = "Statistics"
    description = "Cross-tabulation of two categorical columns with chi-square test."

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
            data_type="CrosstabResult",
            help="Inspectable cross-tabulation table and chi-square test results.",
        ),
    ]
    params = [
        ParamSpec(
            name="row_col",
            type_token="str",
            required=True,
            label="Row column",
            help="Categorical column for table rows.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="col_col",
            type_token="str",
            required=True,
            label="Column column",
            help="Categorical column for table columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="normalize",
            type_token="str",
            default="none",
            label="Normalize",
            help="Normalization mode for the table.",
            hints=ValidationHints(choices=["none", "index", "columns", "all"], widget="select"),
        ),
        ParamSpec(
            name="margins",
            type_token="bool",
            default=True,
            label="Show margins",
            help="Add a 'Total' row and column.",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, str, bool]:
        values = {p.name: p.value for p in node.params}
        row_col = values.get("row_col")
        col_col = values.get("col_col")
        normalize = values.get("normalize", "none")
        if normalize is None:
            normalize = "none"
        margins = values.get("margins", True)
        if margins is None:
            margins = True
        return cast(str, row_col), cast(str, col_col), cast(str, normalize), cast(bool, margins)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        row_col, col_col, normalize, margins = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.crosstab({ctx.in_var('frame')}, "
                f"row_col={row_col!r}, col_col={col_col!r}, "
                f"normalize={normalize!r}, margins={margins!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        row_col, col_col, normalize, margins = self._args(node)
        return {
            "result": crosstab(
                inputs["frame"],
                row_col=row_col,
                col_col=col_col,
                normalize=normalize,
                margins=margins,
            )
        }
