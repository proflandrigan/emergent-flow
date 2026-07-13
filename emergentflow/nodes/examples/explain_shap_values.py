"""
emergentflow.nodes.examples.explain_shap_values
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``explain.shap_values`` — the entry point of the Model Explainability family
(ADR 0020).

Computes per-feature SHAP attributions for a fitted, supervised ``ml.FittedModel`` over a
DataFrame, as a tidy long-format DataFrame. ``execute`` calls ``emergentflow.explain.shap_values``
directly and the code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the
two paths are equivalent by construction (ADR 0002). Requires the optional
``emergentflow[explain]`` dependency group (shap); raises a typed
``MissingOptionalDependencyError`` if absent, never an opaque ``ImportError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.explain import shap_values
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ExplainShapValues(NodeDefinition):
    """Compute per-feature SHAP attributions for a fitted model, as a tidy DataFrame."""

    type = "explain.shap_values"
    version = 1
    family = "explain"
    label = "SHAP Values"
    category = "Model Explainability"
    description = "Compute per-feature SHAP attributions for a fitted model."

    ports = [
        PortSpec(
            name="model",
            direction=Direction.IN,
            data_type="Model",
            help="The fitted, supervised model to explain.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The data to compute SHAP attributions over.",
        ),
        PortSpec(
            name="shap_values",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Tidy, long-format SHAP attributions: one row per (row_index, feature[, class]).",
        ),
    ]
    params = [
        ParamSpec(
            name="seed",
            type_token="int",
            required=True,
            label="Random seed",
            help="Random seed for background sampling (required for reproducibility).",
        ),
        ParamSpec(
            name="background_samples",
            type_token="int",
            default=100,
            label="Background samples",
            help="Maximum number of rows to sample as the SHAP background dataset.",
        ),
    ]

    def _args(self, node: Node) -> tuple[int, int]:
        values = {p.name: p.value for p in node.params}
        seed = cast(int, values.get("seed"))
        background_samples = cast(int, values.get("background_samples"))
        return seed, background_samples

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        seed, background_samples = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('shap_values')} = ef.explain.shap_values("
                f"{ctx.in_var('model')}, {ctx.in_var('frame')}, "
                f"seed={seed!r}, background_samples={background_samples!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        seed, background_samples = self._args(node)
        return {
            "shap_values": shap_values(
                inputs["model"], inputs["frame"], seed=seed, background_samples=background_samples
            )
        }
