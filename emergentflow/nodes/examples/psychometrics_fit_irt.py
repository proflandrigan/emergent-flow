"""
emergentflow.nodes.examples.psychometrics_fit_irt
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``psychometrics.fit_irt`` — IRT ability estimation (issue #164 Gap 3a).

Fits a Rasch/2PL/3PL model to long-format item responses and returns per-subject abilities,
per-item parameters, and per-item fit statistics. Requires the optional
``emergentflow[psychometrics]`` extra. ``execute`` calls ``emergentflow.psychometrics.fit_irt``
directly and ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.psychometrics import IRTResult, fit_irt

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class PsychometricsFitIrt(NodeDefinition):
    """Fit an IRT model (Rasch/2PL/3PL) to long-format item responses."""

    type = "psychometrics.fit_irt"
    version = 1
    family = "psychometrics"
    label = "Fit IRT"
    category = "Psychometrics"
    description = "IRT ability estimation (Rasch/2PL/3PL) from item responses."
    requires_extra = "emergentflow[psychometrics]"

    ports = [
        PortSpec(
            name="responses",
            label="Responses",
            direction=Direction.IN,
            data_type="DataFrame",
            help="Long-format responses: one row per subject-item with a binary score.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="IRTResult",
            help="Per-subject abilities, per-item parameters, and fit statistics.",
        ),
    ]
    params = [
        ParamSpec(
            name="subject_col",
            type_token="str",
            required=True,
            label="Subject column",
            help="Column naming the subject.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="item_col",
            type_token="str",
            required=True,
            label="Item column",
            help="Column naming the item.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="score_col",
            type_token="str",
            required=True,
            label="Score column",
            help="Binary (0/1 or True/False) item score column.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="model",
            type_token="str",
            default="rasch",
            label="Model",
            help="rasch (discrimination=1), 2pl, or 3pl.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["rasch", "2pl", "3pl"]), widget="select"
            ),
        ),
        ParamSpec(
            name="ability_method",
            type_token="str",
            default="eap",
            label="Ability method",
            help="EAP (default, robust for extreme scores), MAP, or MLE.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["eap", "map", "mle"]), widget="select"
            ),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "subject_col": cast(str, values.get("subject_col")),
            "item_col": cast(str, values.get("item_col")),
            "score_col": cast(str, values.get("score_col")),
            "model": cast(str, values.get("model", "rasch")),
            "ability_method": cast(str, values.get("ability_method", "eap")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        codegen_model = f", model={args['model']!r}" if args["model"] != "rasch" else ""
        codegen_method = (
            f", ability_method={args['ability_method']!r}"
            if args["ability_method"] != "eap"
            else ""
        )
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.psychometrics.fit_irt("
                f"{ctx.in_var('responses')}, subject_col={args['subject_col']!r}, "
                f"item_col={args['item_col']!r}, score_col={args['score_col']!r}"
                f"{codegen_model}{codegen_method})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        result: IRTResult = fit_irt(
            inputs["responses"],
            subject_col=args["subject_col"],
            item_col=args["item_col"],
            score_col=args["score_col"],
            model=args["model"],
            ability_method=args["ability_method"],
        )
        return {"result": result}
