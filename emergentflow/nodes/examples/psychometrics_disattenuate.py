"""
emergentflow.nodes.examples.psychometrics_disattenuate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``psychometrics.disattenuate`` — measurement-error correction (issue
#164 Gap 3b).

Corrects an observed correlation for attenuation and reports the attainable ceiling.
Takes scalar params (no frame port). ``execute`` calls
``emergentflow.psychometrics.disattenuate`` directly and ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.psychometrics import disattenuate

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class PsychometricsDisattenuate(NodeDefinition):
    """Correct an observed correlation for measurement error; report the attainable ceiling."""

    type = "psychometrics.disattenuate"
    version = 2
    family = "psychometrics"
    label = "Disattenuate"
    category = "Psychometrics"
    description = "Correct an observed correlation for measurement error (attenuation)."

    ports = [
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help=(
                "observed_r, corrected_r, max_attainable_r, attenuation_ratio, "
                "out_of_range[, ci_low/ci_high]."
            ),
        ),
    ]
    params = [
        ParamSpec(
            name="r",
            type_token="float",
            required=True,
            label="Observed correlation",
            help="Observed Pearson correlation between the two measured variables.",
            hints=ValidationHints(widget="number"),
        ),
        ParamSpec(
            name="reliability_x",
            type_token="float",
            required=True,
            label="Reliability of X",
            help="Reliability of the first variable (Cronbach's alpha, ...), in (0, 1].",
            # min=1e-9 (not 0.0): the op rejects reliability <= 0, so a 0 value must fail
            # graph validation rather than pass and crash at run time.
            hints=ValidationHints(min=1e-9, max=1.0, widget="number"),
        ),
        ParamSpec(
            name="reliability_y",
            type_token="float",
            default=1.0,
            label="Reliability of Y",
            help="Reliability of the second variable, in (0, 1] (default 1.0).",
            hints=ValidationHints(min=1e-9, max=1.0, widget="number"),
        ),
        ParamSpec(
            name="n",
            type_token="int",
            default=None,
            label="Sample size",
            help="If set, report a 95% CI on the corrected correlation.",
            hints=ValidationHints(min=4, widget="number"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "r": cast(float, values.get("r")),
            "reliability_x": cast(float, values.get("reliability_x")),
            "reliability_y": cast(float, values.get("reliability_y", 1.0)),
            "n": cast("int | None", values.get("n")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        codegen_n = f", n={args['n']!r}" if args["n"] is not None else ""
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.psychometrics.disattenuate("
                f"{args['r']!r}, reliability_x={args['reliability_x']!r}, "
                f"reliability_y={args['reliability_y']!r}{codegen_n})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": disattenuate(
                args["r"],
                reliability_x=args["reliability_x"],
                reliability_y=args["reliability_y"],
                n=args["n"],
            )
        }
