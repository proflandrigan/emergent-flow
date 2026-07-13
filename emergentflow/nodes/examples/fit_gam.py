"""
emergentflow.nodes.examples.fit_gam
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.fit_gam`` — the GAM-dedicated node.

Fits a generalized additive model via ``ef.stats.fit_model`` (GAM family: linear
terms + B-spline smooth terms, GLMGam unpenalized). A more discoverable,
param-specific front door to the GAM subset of the ``stats.fit_model`` archetype:
replaces the catch-all ``model``/``spec_extra`` params with explicit
``target``/``linear_terms``/``smooth_terms``/``family``/``link`` — in particular,
``smooth_terms`` is now a first-class structured param (``list[dict[str, any]]``),
not buried in ``spec_extra``.
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
class FitGAM(NodeDefinition):
    """Fit a generalized additive model (statsmodels GLMGam, unpenalized)."""

    type = "stats.fit_gam"
    version = 1
    family = "stats"
    label = "Fit GAM"
    category = "Statistics"
    advisor_persona = "researcher"
    description = (
        "Fit a generalized additive model: linear terms + B-spline smooth terms"
        " (statsmodels GLMGam, unpenalized)."
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
            name="linear_terms",
            type_token="list[str]",
            default=None,
            label="Linear terms",
            help="Unpenalized linear predictor columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="smooth_terms",
            type_token="list[dict[str, any]]",
            required=True,
            label="Smooth terms",
            help=(
                "Spline smooth terms: a list of {'column': str, 'df': int (default 4),"
                " 'degree': int (default 3)} dicts, one per smoothed predictor column."
            ),
        ),
        ParamSpec(
            name="family",
            type_token="str",
            default=None,
            label="Family",
            help="GLM family for the additive model; defaults to gaussian if unset.",
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
            help="GLM link function; defaults to the family's canonical link if unset.",
        ),
    ]

    def _spec(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        spec: dict[str, Any] = {}
        for key in ("target", "linear_terms", "smooth_terms", "family", "link"):
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
                f"{ctx.in_var('frame')}, model='GAM', spec={spec!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        spec = self._spec(node)
        return {"model": fit_model(inputs["frame"], model="GAM", spec=spec)}
