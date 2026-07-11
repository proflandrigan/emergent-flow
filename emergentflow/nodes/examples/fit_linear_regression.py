"""
emergentflow.nodes.examples.fit_linear_regression
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.fit_linear_regression`` — the OLS/WLS/GLS-dedicated node.

Fits OLS, WLS, or GLS linear regression via ``ef.stats.fit_model``. A more
discoverable, param-specific front door to the linear-regression subset of the
``stats.fit_model`` archetype: replaces the catch-all ``model``/``spec_extra``
params with explicit ``estimator``/``target``/``fixed_effects``/``weights``.
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
class FitLinearRegression(NodeDefinition):
    """Fit OLS/WLS/GLS linear regression (statsmodels)."""

    type = "stats.fit_linear_regression"
    version = 1
    family = "stats"
    label = "Fit Linear Regression"
    category = "Statistics"
    advisor_persona = "researcher"
    description = "Fit OLS/WLS/GLS linear regression (statsmodels)."

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
            name="estimator",
            type_token="str",
            required=True,
            label="Estimator",
            help="Which linear-regression estimator to fit.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["GLS", "OLS", "WLS"]),
                widget="select",
            ),
        ),
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
            name="weights",
            type_token="str",
            default=None,
            label="Weights column",
            help="Column of observation weights; only used when Estimator = WLS.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        spec: dict[str, Any] = {}
        for key in ("target", "fixed_effects", "weights"):
            value = values.get(key)
            if value not in (None, "", [], ()):
                spec[key] = value
        return cast(str, values.get("estimator")), spec

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        estimator, spec = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.stats.fit_model("
                f"{ctx.in_var('frame')}, model={estimator!r}, spec={spec!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        estimator, spec = self._args(node)
        return {"model": fit_model(inputs["frame"], model=estimator, spec=spec)}
