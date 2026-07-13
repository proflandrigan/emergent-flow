"""
emergentflow.nodes.examples.fit_glm
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.fit_glm`` — the GLM-dedicated node.

Fits a generalized linear model via ``ef.stats.fit_model`` (GLM family:
Gaussian/Binomial/Poisson/NegativeBinomial/Gamma). A more discoverable,
param-specific front door to the GLM subset of the ``stats.fit_model``
archetype: replaces the catch-all ``model``/``spec_extra`` params with
explicit ``target``/``fixed_effects``/``family``/``link``/``weights``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.stats import fit_model

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class FitGLM(NodeDefinition):
    """Fit a generalized linear model (statsmodels)."""

    type = "stats.fit_glm"
    version = 1
    family = "stats"
    label = "Fit GLM"
    category = "Statistics"
    advisor_persona = "researcher"
    description = (
        "Fit a generalized linear model"
        " (Gaussian/Binomial/Poisson/NegativeBinomial/Gamma, statsmodels)."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the target and predictor columns.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="StatsModel",
            help="The fitted statistical model.",
        ),
    ]
    params = [
        ParamSpec(
            name="target",
            type_token="str",
            required=True,
            label="Target column",
            help="Column to predict.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="fixed_effects",
            type_token="list[str]",
            default=None,
            label="Predictor columns",
            help="Predictor columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="family",
            type_token="str",
            required=True,
            label="Family",
            help="GLM family.",
            hints=ValidationHints(
                choices=cast(
                    "list[ParamValue]",
                    ["binomial", "gamma", "gaussian", "negativebinomial", "poisson"],
                ),
                widget="select",
            ),
        ),
        ParamSpec(
            name="link",
            type_token="str",
            default=None,
            label="Link",
            help=(
                "GLM link function; defaults to the family's canonical link if unset. "
                "Valid per family: gaussian=identity/log/inverse, "
                "binomial=logit/probit/cloglog, poisson=log/identity/sqrt, "
                "negativebinomial=log/identity, gamma=inverse/log/identity."
            ),
        ),
        ParamSpec(
            name="weights",
            type_token="str",
            default=None,
            label="Weights column",
            help="Column of observation weights (for weighted GLM).",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _spec(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        spec: dict[str, Any] = {}
        for key in ("target", "fixed_effects", "family", "link", "weights"):
            value = values.get(key)
            if value not in (None, "", [], ()):
                spec[key] = value
        return spec

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        spec = self._spec(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.stats.fit_model("
                f"{ctx.in_var('frame')}, model='GLM', spec={spec!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        spec = self._spec(node)
        return {"model": fit_model(inputs["frame"], model="GLM", spec=spec)}
