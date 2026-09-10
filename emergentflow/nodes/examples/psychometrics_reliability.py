"""
emergentflow.nodes.examples.psychometrics_reliability
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``psychometrics.reliability`` — internal-consistency reliability
(issue #164 Gap 3).

Computes Cronbach's alpha / KR-20 with per-item-dropped alpha from a wide item matrix or a
long-format pivot. ``execute`` calls ``emergentflow.psychometrics.reliability`` directly and
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.psychometrics import reliability

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class PsychometricsReliability(NodeDefinition):
    """Cronbach's alpha / KR-20 with per-item-dropped alpha."""

    type = "psychometrics.reliability"
    version = 1
    family = "psychometrics"
    label = "Reliability"
    category = "Psychometrics"
    description = "Internal-consistency reliability (Cronbach's alpha / KR-20)."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Wide item matrix (one column per item), or long responses with "
            "subject/item/score columns.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="alpha, kr20, n_items, n_subjects, and alpha_if_dropped per item.",
        ),
    ]
    params = [
        ParamSpec(
            name="item_cols",
            type_token="list[str]",
            default=None,
            label="Item columns",
            help="Wide-form item columns; leave unset to pivot long responses.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="subject_col",
            type_token="str",
            default=None,
            label="Subject column",
            help="Long-format subject column (requires score_col).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="item_col",
            type_token="str",
            default=None,
            label="Item column",
            help="Long-format item column (requires score_col).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="score_col",
            type_token="str",
            default=None,
            label="Score column",
            help="Long-format score column.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="method",
            type_token="str",
            default="cronbach_alpha",
            label="Method",
            help="cronbach_alpha or kr20.",
            hints=ValidationHints(choices=["cronbach_alpha", "kr20"], widget="select"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "item_cols": cast("list[str] | None", values.get("item_cols")),
            # `or None`: an empty string (a cleared canvas column) must be treated exactly like
            # no column, on BOTH the codegen and execute paths -- otherwise execute passes
            # score_col="" (raising "unknown column ''") while codegen omits it (raising a
            # different "requires score_col" error), a codegen/execute divergence (ADR 0002).
            "subject_col": cast("str | None", values.get("subject_col") or None),
            "item_col": cast("str | None", values.get("item_col") or None),
            "score_col": cast("str | None", values.get("score_col") or None),
            "method": cast(str, values.get("method", "cronbach_alpha")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        codegen_sub = f", subject_col={args['subject_col']!r}" if args["subject_col"] else ""
        codegen_item = f", item_col={args['item_col']!r}" if args["item_col"] else ""
        codegen_score = f", score_col={args['score_col']!r}" if args["score_col"] else ""
        codegen_method = (
            f", method={args['method']!r}" if args["method"] != "cronbach_alpha" else ""
        )
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.psychometrics.reliability("
                f"{ctx.in_var('frame')}, item_cols={args['item_cols']!r}"
                f"{codegen_sub}{codegen_item}{codegen_score}{codegen_method})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": reliability(
                inputs["frame"],
                item_cols=args["item_cols"],
                subject_col=args["subject_col"],
                item_col=args["item_col"],
                score_col=args["score_col"],
                method=args["method"],
            )
        }
