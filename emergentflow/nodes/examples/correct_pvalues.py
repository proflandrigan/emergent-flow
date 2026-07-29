"""
emergentflow.nodes.examples.correct_pvalues
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.correct_pvalues`` — a *transform* node (1 in, 1 out).

Applies a multiple-comparison correction (Bonferroni / Benjamini-Hochberg) to a
DataFrame's p-value column. ``execute`` calls ``emergentflow.stats.correct_pvalues``
directly and the code emitted by ``codegen`` calls the same wrapper via the ``ef.``
alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import correct_pvalues

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class CorrectPvalues(NodeDefinition):
    """Apply a multiple-comparison correction to a DataFrame's p-value column."""

    type = "stats.correct_pvalues"
    version = 1
    family = "stats"
    label = "Correct P-Values"
    category = "Statistics"
    description = "Apply a multiple-comparison correction (Bonferroni / Benjamini-Hochberg)."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing a p-value column.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input DataFrame with p_adjusted and reject_null columns appended.",
        ),
    ]
    params = [
        ParamSpec(
            name="p_col",
            type_token="str",
            default="p_value",
            label="P-value column",
            help="Name of the column containing uncorrected p-values.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="method",
            type_token="str",
            default="bonferroni",
            label="Correction method",
            help="Bonferroni or Benjamini-Hochberg FDR control.",
            hints=ValidationHints(choices=["bonferroni", "benjamini_hochberg"], widget="select"),
        ),
        ParamSpec(
            name="alpha",
            type_token="float",
            default=0.05,
            label="Alpha",
            help="Significance threshold for the adjusted p-values.",
            hints=ValidationHints(min=0.0, max=1.0, widget="number"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        alpha = values.get("alpha", 0.05)
        if alpha is None:
            alpha = 0.05
        return {
            "p_col": values.get("p_col") or "p_value",
            "method": values.get("method") or "bonferroni",
            "alpha": alpha,
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.stats.correct_pvalues("
                f"{ctx.in_var('frame')}, "
                f"p_col={args['p_col']!r}, method={args['method']!r}, "
                f"alpha={args['alpha']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": correct_pvalues(
                inputs["frame"],
                p_col=args["p_col"],
                method=args["method"],
                alpha=args["alpha"],
            )
        }
