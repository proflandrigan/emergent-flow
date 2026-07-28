"""
emergentflow.nodes.examples.reduce_dimensions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.reduce_dimensions`` — a *transform* node (1 in, 1 out).

Real, sklearn/umap-backed dimensionality reduction (Epic 16). ``execute`` calls
``emergentflow.ml.reduce_dimensions`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import reduce_dimensions

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ReduceDimensions(NodeDefinition):
    """Reduce numeric columns to N coordinate columns via PCA/t-SNE/UMAP."""

    type = "ml.reduce_dimensions"
    version = 1
    family = "ml"
    label = "Reduce Dimensions"
    category = "Machine Learning"
    description = "Reduce numeric columns to N coordinate columns via PCA/t-SNE/UMAP."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the numeric feature columns.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DimensionReductionResult",
            help="Reduced coordinates plus metadata.",
        ),
    ]
    params = [
        ParamSpec(
            name="feature_cols",
            type_token="list[str]",
            required=True,
            label="Feature columns",
            help="Numeric columns to reduce.",
            hints=ValidationHints(),
        ),
        ParamSpec(
            name="method",
            type_token="str",
            default="pca",
            label="Method",
            help="Dimensionality reduction algorithm.",
            hints=ValidationHints(choices=["pca", "tsne", "umap"], widget="select"),
        ),
        ParamSpec(
            name="n_components",
            type_token="int",
            default=2,
            label="Components",
            help="Number of reduced dimensions.",
            hints=ValidationHints(min=1, widget="number"),
        ),
        ParamSpec(
            name="seed",
            type_token="int",
            default=0,
            label="Seed",
            help="Random seed for reproducibility.",
            hints=ValidationHints(widget="number"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str], str, int, int]:
        values = {p.name: p.value for p in node.params}
        feature_cols = cast(list[str], values.get("feature_cols", []))
        method = cast(str, values.get("method", "pca"))
        n_components = cast(int, values.get("n_components", 2))
        seed = cast(int, values.get("seed", 0))
        return feature_cols, method, n_components, seed

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        feature_cols, method, n_components, seed = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.ml.reduce_dimensions({ctx.in_var('frame')}, "
                f"feature_cols={feature_cols!r}, method={method!r}, "
                f"n_components={n_components!r}, seed={seed!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        feature_cols, method, n_components, seed = self._args(node)
        return {
            "result": reduce_dimensions(
                inputs["frame"],
                feature_cols=feature_cols,
                method=method,
                n_components=n_components,
                seed=seed,
            )
        }
