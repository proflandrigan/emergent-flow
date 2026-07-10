"""
emergentflow.nodes.examples.fit_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.fit_model`` — the "fit-model" archetype node (Epic 12).

Fits a curated, allow-listed statistical model (any model registered with
``archetype="fit_model"`` in ``emergentflow.stats.registry``) and returns a fitted
``FittedStatsModel``. The ``model`` choice list is computed at import time from the live
registry, so it grows automatically as more models are curated into the allow-list (no edits
needed here). ``execute`` calls ``emergentflow.stats.fit_model`` directly and the code emitted
by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).

Structured spec fields common across model families (``target``/``fixed_effects``/
``random_effects``/``linear_terms``/``groups``/``family``/``link``/``weights``) are lifted out
as explicit, canvas-configurable params (Epic 12 Story 1 Decision 4: structured params, not
formula strings). ``spec_extra`` is a catch-all for family-specific fields not covered above
(e.g. GAM's ``smooth_terms`` or a Bayesian model's ``seed``/``draws``) so this node never needs
editing again as new fit-model families are curated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.stats import fit_model
from emergentflow.stats.registry import keys_for_archetype

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class FitModel(NodeDefinition):
    """Fit a curated, allow-listed statistical model (OLS/WLS/GLS/GLM/... )."""

    type = "stats.fit_model"
    version = 1
    family = "stats"
    label = "Fit Statistical Model"
    category = "Statistics"
    advisor_persona = "researcher"
    description = "Fit a curated, allow-listed statistical model (regression/GLM/...)."

    ports = [
        PortSpec(
            name="frame",
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
            name="model",
            type_token="str",
            required=True,
            label="Model",
            help="Which allow-listed statistical model to fit.",
            hints=ValidationHints(
                choices=cast(
                    "list[ParamValue]",
                    sorted(keys_for_archetype("fit_model") + keys_for_archetype("bayesian_fit")),
                ),
                widget="select",
            ),
        ),
        ParamSpec(
            name="target",
            type_token="str",
            required=True,
            label="Target column",
            help="Column to predict.",
        ),
        ParamSpec(
            name="fixed_effects",
            type_token="list[str]",
            default=None,
            label="Fixed effects",
            help="Predictor columns (fixed effects).",
        ),
        ParamSpec(
            name="random_effects",
            type_token="list[str]",
            default=None,
            label="Random effects",
            help="Random-effect columns (mixed-effects models only).",
        ),
        ParamSpec(
            name="linear_terms",
            type_token="list[str]",
            default=None,
            label="Linear terms",
            help="Unpenalized linear predictor columns (GAM only; smooth terms are configured "
            "via 'Additional spec fields').",
        ),
        ParamSpec(
            name="groups",
            type_token="str",
            default=None,
            label="Grouping factor",
            help="Grouping-factor column (mixed-effects models only).",
        ),
        ParamSpec(
            name="family",
            type_token="str",
            default=None,
            label="Family",
            help="GLM family (gaussian/binomial/poisson/negativebinomial/gamma).",
        ),
        ParamSpec(
            name="link",
            type_token="str",
            default=None,
            label="Link",
            help="GLM link function; defaults to the family's canonical link if unset.",
        ),
        ParamSpec(
            name="weights",
            type_token="str",
            default=None,
            label="Weights column",
            help="Column of observation weights (WLS, or weighted GLM).",
        ),
        ParamSpec(
            name="spec_extra",
            type_token="dict[str, any]",
            default={},
            label="Additional spec fields",
            help="Any additional model-specific structured-spec fields not covered above.",
        ),
    ]

    def _spec(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        spec: dict[str, Any] = cast("dict[str, Any]", values.get("spec_extra") or {})
        for key in (
            "target",
            "fixed_effects",
            "random_effects",
            "linear_terms",
            "groups",
            "family",
            "link",
            "weights",
        ):
            value = values.get(key)
            if value not in (None, "", [], ()):
                spec[key] = value
        return spec

    def _args(self, node: Node) -> tuple[str, dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        return cast(str, values.get("model")), self._spec(node)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        model, spec = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.stats.fit_model("
                f"{ctx.in_var('frame')}, model={model!r}, spec={spec!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        model, spec = self._args(node)
        return {"model": fit_model(inputs["frame"], model=model, spec=spec)}
