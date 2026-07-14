"""
emergentflow.nodes.examples.select_features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.select_features`` — a dedicated, discoverable feature-selection node
(ADR 0016), thin wrapper over ``ef.ml.select_features``.

Restricted to curated estimators registered with ``EstimatorSpec.is_feature_selector=True``
(``SelectKBest``, ``VarianceThreshold``, ``RFE``, ``SelectFromModel``). Unlike the generic
``ml.fit_transform`` node (which can fit ANY fit_transform-archetype estimator, selectors
included, and always names its output columns generically), this node's ``selector`` dropdown
is pre-filtered to just the curated feature selectors, and its output frame keeps real,
selected column names. ``execute`` calls ``emergentflow.ml.select_features`` directly and the
code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.ml import select_features
from emergentflow.ml.registry import feature_selector_keys

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class SelectFeatures(NodeDefinition):
    """Fit a curated feature-selector estimator and keep only the features it selected."""

    type = "ml.select_features"
    version = 1
    family = "ml"
    label = "Select Features"
    category = "Machine Learning"
    description = "Fit a curated feature-selector estimator and keep only the selected features."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing candidate feature columns (and, for "
            "supervised selectors, the target column).",
        ),
        PortSpec(
            name="transformer",
            direction=Direction.OUT,
            data_type="Transformer",
            help="The fitted feature-selector.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input frame with unselected feature columns dropped.",
        ),
        PortSpec(
            name="summary",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One row per candidate feature, with selected (bool) and, when available, "
            "score/ranking.",
        ),
    ]
    params = [
        ParamSpec(
            name="selector",
            type_token="str",
            required=True,
            label="Selector",
            help="Which curated feature-selector estimator to fit.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", feature_selector_keys()), widget="select"
            ),
        ),
        ParamSpec(
            name="target",
            type_token="str",
            default=None,
            label="Target column",
            help="Only needed for supervised selectors (SelectKBest, RFE, SelectFromModel); "
            "leave unset for VarianceThreshold.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Candidate columns to select among; empty/unset uses every other column.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Selector params",
            help="Constructor kwargs for the chosen selector (allow-listed per selector).",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str | None, list[str] | None, dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        selector = values.get("selector")
        target = values.get("target")
        features = values.get("features")
        params = values.get("params") or {}
        return (
            cast(str, selector),
            cast("str | None", target),
            cast("list[str] | None", features),
            cast("dict[str, Any]", params),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        selector, target, features, params = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('transformer')}, {ctx.out_var('result')}, "
                f"{ctx.out_var('summary')} = ef.ml.select_features("
                f"{ctx.in_var('frame')}, selector={selector!r}, target={target!r}, "
                f"features={features!r}, params={params!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        selector, target, features, params = self._args(node)
        transformer, result, summary = select_features(
            inputs["frame"],
            selector=selector,
            target=target,
            features=features,
            params=params,
        )
        return {"transformer": transformer, "result": result, "summary": summary}
