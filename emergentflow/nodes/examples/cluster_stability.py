"""
emergentflow.nodes.examples.cluster_stability
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.cluster_stability`` — a *transform* node (1 in, 1 out).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import cluster_stability

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ClusterStability(NodeDefinition):
    """Bootstrap-resample, refit, and score partition agreement (mean ARI)."""

    type = "stats.cluster_stability"
    version = 1
    family = "stats"
    label = "Cluster Stability"
    category = "Statistics"
    description = (
        "Bootstrap-resample, refit, and score partition agreement via adjusted Rand index."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="DataFrame with features and optional group column.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One row per resample (resample, ari, n_clusters, ok).",
        ),
    ]
    params = [
        ParamSpec(
            name="estimator",
            type_token="str",
            default="KMeans",
            label="Estimator",
            help="Clustering estimator key from the ml catalog.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Features",
            help="Columns to cluster on; None uses all numeric columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="n_resamples",
            type_token="int",
            default=50,
            label="Resamples",
            help="Number of bootstrap resamples.",
            hints=ValidationHints(widget="number", min=2),
        ),
        ParamSpec(
            name="group_col",
            type_token="str",
            default=None,
            label="Group column",
            help="Column to group-resample (cluster bootstrap); None resamples rows.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="random_state",
            type_token="int",
            default=0,
            label="Random state",
            help="Seed for deterministic resampling.",
            hints=ValidationHints(widget="number"),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        values = {p.name: p.value for p in node.params}
        estimator = values.get("estimator") or "KMeans"
        features = values.get("features")
        n_resamples = values.get("n_resamples") or 50
        group_col = values.get("group_col")
        random_state = values.get("random_state") or 0
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.cluster_stability("
                f"{ctx.in_var('frame')}, estimator={estimator!r}, "
                f"features={features!r}, n_resamples={n_resamples!r}, "
                f"group_col={group_col!r}, random_state={random_state!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        estimator = cast(str, values.get("estimator") or "KMeans")
        features = cast("list[str] | None", values.get("features"))
        n_resamples = cast(int, values.get("n_resamples") or 50)
        group_col = cast("str | None", values.get("group_col"))
        random_state = cast(int, values.get("random_state") or 0)
        return {
            "result": cluster_stability(
                inputs["frame"],
                estimator=estimator,
                features=features,
                n_resamples=n_resamples,
                group_col=group_col,
                random_state=random_state,
            )
        }
