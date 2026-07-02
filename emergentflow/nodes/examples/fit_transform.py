"""
emergentflow.nodes.examples.fit_transform
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.fit_transform`` — the "fit_transform" archetype node (Epic 8, ADR 0016).

Fits a curated, allow-listed sklearn unsupervised transformer (any estimator registered with
``archetype="fit_transform"`` in ``emergentflow.ml.registry`` -- scalers, encoders,
decomposition/PCA, manifold, feature selection) and immediately transforms the SAME input
frame, returning both a fitted ``Transformer`` and the transformed ``DataFrame``. The
``estimator`` choice list is computed at import time from the live registry, so it grows
automatically as more estimators are curated into the allow-list (no edits needed here).
``execute`` calls ``emergentflow.ml.fit_transform`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002). Uses the single-step ``ef.ml.fit_transform`` adapter (not
``ef.ml.fit_estimator`` followed by ``ef.ml.apply_estimator``) because a few curated
transformers (e.g. ``TSNE``) implement ``.fit_transform()`` but have no separate
``.transform()`` at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.ml import fit_transform
from emergentflow.ml.registry import keys_for_archetype

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class FitTransform(NodeDefinition):
    """Fit a curated, allow-listed sklearn unsupervised transformer and transform the input."""

    type = "ml.fit_transform"
    version = 1
    family = "ml"
    label = "Fit Transform"
    category = "Machine Learning"
    description = "Fit a curated, allow-listed sklearn unsupervised transformer."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing features (and, for supervised feature "
            "selectors, the target column).",
        ),
        PortSpec(
            name="transformer",
            direction=Direction.OUT,
            data_type="Transformer",
            help="The fitted transformer.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input frame transformed by the fitted transformer.",
        ),
    ]
    params = [
        ParamSpec(
            name="estimator",
            type_token="str",
            required=True,
            label="Estimator",
            help="Which allow-listed sklearn transformer to fit.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", keys_for_archetype("fit_transform")),
                widget="select",
            ),
        ),
        ParamSpec(
            name="target",
            type_token="str",
            default=None,
            label="Target column",
            help="Only needed for supervised feature selectors (e.g. SelectKBest); "
            "leave unset for unsupervised transformers.",
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Columns to use as features; empty/unset uses every other column "
            "(excluding the target column, if given).",
        ),
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Estimator params",
            help="Constructor kwargs for the chosen estimator (allow-listed per estimator).",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str | None, list[str] | None, dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        estimator = values.get("estimator")
        target = values.get("target")
        features = values.get("features")
        params = values.get("params") or {}
        return (
            cast(str, estimator),
            cast("str | None", target),
            cast("list[str] | None", features),
            cast("dict[str, Any]", params),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        estimator, target, features, params = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('transformer')}, {ctx.out_var('result')} = ef.ml.fit_transform("
                f"{ctx.in_var('frame')}, estimator={estimator!r}, target={target!r}, "
                f"features={features!r}, params={params!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        estimator, target, features, params = self._args(node)
        transformer, result = fit_transform(
            inputs["frame"],
            estimator=estimator,
            target=target,
            features=features,
            params=params,
        )
        return {"transformer": transformer, "result": result}
