"""
emergentflow.nodes.examples.fit_mixed_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.fit_mixed_model`` — the MixedLM-dedicated node.

Fits a linear mixed-effects / hierarchical model via ``ef.stats.fit_model`` (MixedLM
family: linear mixed-effects with random intercepts and slopes, grouped by a factor
column). A more discoverable, param-specific front door to the MixedLM subset of the
``stats.fit_model`` archetype: replaces the catch-all ``model``/``spec_extra`` params
with explicit ``target``/``fixed_effects``/``random_effects``/``groups``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import fit_model

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class FitMixedModel(NodeDefinition):
    """Fit a linear mixed-effects / hierarchical model (statsmodels MixedLM)."""

    type = "stats.fit_mixed_model"
    version = 1
    family = "stats"
    label = "Fit Mixed Model"
    category = "Statistics"
    advisor_persona = "researcher"
    description = (
        "Fit a linear mixed-effects / hierarchical model"
        " with random intercepts and slopes, grouped (statsmodels MixedLM)."
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
            label="Fixed effects",
            help="Predictor columns (fixed effects).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="random_effects",
            type_token="list[str]",
            default=None,
            label="Random effects",
            help=(
                "Random-effect columns (random slopes);"
                " leave unset for a random-intercept-only model."
            ),
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="groups",
            type_token="str",
            required=True,
            label="Grouping factor",
            help="Grouping-factor column (e.g. subject/site/region).",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _spec(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        spec: dict[str, Any] = {}
        for key in ("target", "fixed_effects", "random_effects", "groups"):
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
                f"{ctx.in_var('frame')}, model='MixedLM', spec={spec!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        spec = self._spec(node)
        return {"model": fit_model(inputs["frame"], model="MixedLM", spec=spec)}
