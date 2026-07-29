"""
emergentflow.nodes.examples.power_analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.power_analysis`` — a *source* node (0 inputs, 1 output).

Real, statsmodels-backed power analysis (Epic 6). ``execute`` calls
``emergentflow.stats.power_analysis`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import power_analysis

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class PowerAnalysis(NodeDefinition):
    """Solve a two-independent-sample t-test power equation for the one unset quantity."""

    type = "stats.power_analysis"
    version = 1
    family = "stats"
    label = "Power Analysis"
    category = "Statistics"
    description = "Solve a power equation for effect size, sample size, or power."

    ports = [
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Inspectable power-analysis results.",
        ),
    ]
    params = [
        ParamSpec(
            name="effect_size",
            type_token="float",
            default=None,
            required=False,
            label="Effect size (Cohen's d)",
            help="Minimum detectable effect size (MDE). Leave unset to solve for this.",
        ),
        ParamSpec(
            name="nobs",
            type_token="float",
            default=None,
            required=False,
            label="Sample size per group",
            help="Sample size per group. Leave unset to solve for this.",
        ),
        ParamSpec(
            name="power",
            type_token="float",
            default=None,
            required=False,
            label="Power",
            help="Desired statistical power. Leave unset to solve for this.",
        ),
        ParamSpec(
            name="alpha",
            type_token="float",
            default=0.05,
            label="Alpha",
            help="Significance level.",
            hints=ValidationHints(min=0.0, max=1.0, widget="number"),
        ),
        ParamSpec(
            name="ratio",
            type_token="float",
            default=1.0,
            label="Ratio",
            help="Ratio of sample sizes (n_b / n_a).",
        ),
        ParamSpec(
            name="alternative",
            type_token="str",
            default="two-sided",
            label="Alternative",
            help="Direction of the alternative hypothesis.",
            hints=ValidationHints(choices=["two-sided", "larger", "smaller"], widget="select"),
        ),
    ]

    def _args(
        self, node: Node
    ) -> tuple[float | None, float | None, float, float | None, float, str]:
        values = {p.name: p.value for p in node.params}
        effect_size = values.get("effect_size")
        nobs = values.get("nobs")
        alpha = values.get("alpha", 0.05)
        if alpha is None:
            alpha = 0.05
        power = values.get("power")
        ratio = values.get("ratio", 1.0)
        if ratio is None:
            ratio = 1.0
        alternative = values.get("alternative", "two-sided")
        if alternative is None:
            alternative = "two-sided"
        return (
            cast("float | None", effect_size),
            cast("float | None", nobs),
            cast(float, alpha),
            cast("float | None", power),
            cast(float, ratio),
            cast(str, alternative),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        effect_size, nobs, alpha, power, ratio, alternative = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.power_analysis("
                f"effect_size={effect_size!r}, nobs={nobs!r}, alpha={alpha!r}, "
                f"power={power!r}, ratio={ratio!r}, alternative={alternative!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        effect_size, nobs, alpha, power, ratio, alternative = self._args(node)
        return {
            "result": power_analysis(
                effect_size=effect_size,
                nobs=nobs,
                alpha=alpha,
                power=power,
                ratio=ratio,
                alternative=alternative,
            )
        }
