"""
emergentflow.nodes.examples.pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.pipeline`` — chains fit_transform steps into a final fit/cluster_detect
step as one fitted sklearn ``Pipeline`` (Epic 8, Story 8 / ADR 0016).

Unlike the other archetype nodes, this node's ``estimator`` identity is not a single choice --
it is an ordered ``steps`` list, each step itself an ``{"estimator": key, "params": {...}}``
dict validated against the same curated allow-list every other archetype node uses. The fitted
``sklearn.pipeline.Pipeline`` rides inside a plain ``Model`` output port: because a fitted
``Pipeline`` duck-types ``.predict()``/``.transform()``/``.score_samples()`` exactly like any
single fitted estimator, the EXISTING ``ml.apply_estimator`` node applies it to new data with
no changes needed there -- this node only needs to produce the fitted ``Model``, not also a
transformed/labeled frame. ``execute`` calls ``emergentflow.ml.fit_pipeline`` directly and the
code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import fit_pipeline

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Pipeline(NodeDefinition):
    """Fit an ordered chain of curated estimators as one sklearn Pipeline."""

    type = "ml.pipeline"
    version = 2
    family = "ml"
    label = "Pipeline"
    category = "Machine Learning"
    description = "Fit an ordered chain of curated estimators as one sklearn Pipeline."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing features and (if the final step is "
            "supervised) the target column.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The fitted pipeline, wrapping every step as one Model.",
        ),
    ]
    params = [
        ParamSpec(
            name="steps",
            type_token="list[dict[str, any]]",
            required=True,
            label="Pipeline steps",
            help="Ordered list of {estimator, params} dicts. Every step but the last must be "
            "a fit_transform-archetype estimator; the last must be a fit or "
            "cluster_detect-archetype estimator.",
        ),
        ParamSpec(
            name="target",
            type_token="str",
            default=None,
            label="Target column",
            help="Column to predict; required only when the final step is a "
            "fit-archetype (supervised) estimator.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Columns to use as features; empty/unset uses every other column.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="weight_col",
            type_token="str",
            default=None,
            label="Weights column",
            help="Optional column of per-row sample weights forwarded to the final step's fit.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(
        self, node: Node
    ) -> tuple[list[dict[str, Any]], str | None, list[str] | None, str | None]:
        values = {p.name: p.value for p in node.params}
        steps = values.get("steps") or []
        target = values.get("target")
        features = values.get("features")
        weight_col = values.get("weight_col") or None
        return (
            cast("list[dict[str, Any]]", steps),
            cast("str | None", target),
            cast("list[str] | None", features),
            cast("str | None", weight_col),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        steps, target, features, weight_col = self._args(node)
        codegen_weight = f", weight_col={weight_col!r}" if weight_col is not None else ""
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.ml.fit_pipeline("
                f"{ctx.in_var('frame')}, steps={steps!r}, target={target!r}, "
                f"features={features!r}{codegen_weight})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        steps, target, features, weight_col = self._args(node)
        return {
            "model": fit_pipeline(
                inputs["frame"],
                steps=steps,
                target=target,
                features=features,
                weight_col=weight_col,
            )
        }
