"""
emergentflow.nodes.examples.fit_bayesian_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.fit_bayesian_model`` — the BayesianGLM-dedicated node.

Fits a Bayesian GLM (optionally hierarchical) via ``ef.stats.fit_model`` (BayesianGLM:
Gaussian/Binomial/Poisson/NegativeBinomial/Gamma families, with optional random effects and
grouping via bambi/PyMC, summarized with ArviZ). A more discoverable, param-specific front
door to the BayesianGLM subset of the ``stats.fit_model`` archetype: ``seed``/``draws``/
``tune``/``chains`` are now explicit required params (not buried in ``spec_extra``), and the
underlying fitter lazily imports the optional ``emergentflow[bayes]`` extra —
``ef.stats.fit_model`` raises a ``MissingOptionalDependencyError`` if it is absent.
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
class FitBayesianModel(NodeDefinition):
    """Fit a Bayesian GLM (optionally hierarchical), via bambi/PyMC, summarized with ArviZ."""

    type = "stats.fit_bayesian_model"
    version = 1
    family = "stats"
    label = "Fit Bayesian Model"
    category = "Statistics"
    advisor_persona = "researcher"
    description = (
        "Fit a Bayesian GLM (optionally hierarchical), via bambi/PyMC, summarized with ArviZ."
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
            help="Random-effect columns (random slopes, hierarchical models only).",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="groups",
            type_token="str",
            default=None,
            label="Grouping factor",
            help=(
                "Grouping-factor column; setting this fits a"
                " hierarchical (random-intercept/slope) model."
            ),
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="family",
            type_token="str",
            default=None,
            label="Family",
            help="GLM family; defaults to gaussian if unset.",
            hints=ValidationHints(
                choices=cast(
                    "list[ParamValue]",
                    ["binomial", "gamma", "gaussian", "negativebinomial", "poisson"],
                ),
                widget="select",
            ),
        ),
        ParamSpec(
            name="seed",
            type_token="int",
            required=True,
            label="Random seed",
            help="Random seed for MCMC sampling (required for reproducibility).",
        ),
        ParamSpec(
            name="draws",
            type_token="int",
            required=True,
            label="Draws",
            help="Number of MCMC posterior samples to draw per chain.",
        ),
        ParamSpec(
            name="tune",
            type_token="int",
            required=True,
            label="Tune steps",
            help="Number of MCMC tuning (warm-up) steps per chain.",
        ),
        ParamSpec(
            name="chains",
            type_token="int",
            required=True,
            label="Chains",
            help="Number of independent MCMC chains to run.",
        ),
    ]

    def _spec(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        spec: dict[str, Any] = {}
        for key in (
            "target",
            "fixed_effects",
            "random_effects",
            "groups",
            "family",
            "seed",
            "draws",
            "tune",
            "chains",
        ):
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
                f"{ctx.in_var('frame')}, model='BayesianGLM', spec={spec!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        spec = self._spec(node)
        return {"model": fit_model(inputs["frame"], model="BayesianGLM", spec=spec)}
