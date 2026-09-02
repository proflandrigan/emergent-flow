"""
emergentflow.nodes.examples.cluster_metrics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.cluster_metrics`` — a *transform* node (1 in, 1 out).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import cluster_metrics

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ClusterMetrics(NodeDefinition):
    """Internal cluster-validation metrics for an already-labelled frame."""

    type = "stats.cluster_metrics"
    version = 1
    family = "stats"
    label = "Cluster Metrics"
    category = "Statistics"
    description = "Silhouette, Calinski-Harabasz, and Davies-Bouldin scores for a clustering."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help=(
                "A DataFrame with a label column (from a clustering node) "
                "and numeric feature columns."
            ),
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="ClusterMetrics",
            help="Inspectable cluster-validation metrics.",
        ),
    ]
    params = [
        ParamSpec(
            name="label_col",
            type_token="str",
            default="label",
            label="Label column",
            help=(
                "Name of the column containing cluster labels. Noise rows (label==-1) are excluded."
            ),
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Features",
            help="Columns to score on; empty uses all numeric columns except label_col.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="sample_size",
            type_token="int",
            default=None,
            label="Sample size",
            help="Subsample for silhouette (O(n^2)); None scores all.",
            hints=ValidationHints(widget="number", min=1),
        ),
        ParamSpec(
            name="random_state",
            type_token="int",
            default=0,
            label="Random state",
            help="Seed for deterministic subsampling.",
            hints=ValidationHints(widget="number"),
        ),
    ]

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        values = {p.name: p.value for p in node.params}
        label_col = values.get("label_col") or "label"
        features = values.get("features")
        sample_size = values.get("sample_size")
        random_state = values.get("random_state") or 0
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.cluster_metrics("
                f"{ctx.in_var('frame')}, label_col={label_col!r}, "
                f"features={features!r}, sample_size={sample_size!r}, "
                f"random_state={random_state!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        label_col = cast(str, values.get("label_col") or "label")
        features = cast("list[str] | None", values.get("features"))
        sample_size = cast("int | None", values.get("sample_size"))
        random_state = cast(int, values.get("random_state") or 0)
        return {
            "result": cluster_metrics(
                inputs["frame"],
                label_col=label_col,
                features=features,
                sample_size=sample_size,
                random_state=random_state,
            )
        }
