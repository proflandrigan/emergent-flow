"""
emergentflow.nodes.examples.fit_estimator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.fit_estimator`` — the "fit" archetype node (Epic 8, ADR 0016).

Fits a curated, allow-listed sklearn classifier or regressor (any estimator registered with
``archetype="fit"`` in ``emergentflow.ml.registry``) and returns a fitted ``Model``. The
``estimator`` choice list is computed at import time from the live registry, so it grows
automatically as more estimators are curated into the allow-list (no edits needed here).
``execute`` calls ``emergentflow.ml.fit_estimator`` directly and the code emitted by ``codegen``
calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.ml import fit_estimator
from emergentflow.ml.registry import keys_for_archetype

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class FitEstimator(NodeDefinition):
    """Fit a curated, allow-listed sklearn classifier or regressor."""

    type = "ml.fit_estimator"
    version = 1
    family = "ml"
    label = "Fit Estimator"
    category = "Machine Learning"
    description = "Fit a curated, allow-listed sklearn classifier or regressor."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing features and the target column.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The fitted model.",
        ),
    ]
    params = [
        ParamSpec(
            name="estimator",
            type_token="str",
            required=True,
            label="Estimator",
            help="Which allow-listed sklearn classifier/regressor to fit.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", keys_for_archetype("fit")), widget="select"
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
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Columns to use as features; empty/unset uses every other column.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="params",
            type_token="dict[str, any]",
            default={},
            label="Estimator params",
            help="Constructor kwargs for the chosen estimator (allow-listed per estimator).",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, list[str] | None, dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        estimator = values.get("estimator")
        target = values.get("target")
        features = values.get("features")
        params = values.get("params") or {}
        return (
            cast(str, estimator),
            cast(str, target),
            cast("list[str] | None", features),
            cast("dict[str, Any]", params),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        estimator, target, features, params = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.ml.fit_estimator("
                f"{ctx.in_var('frame')}, estimator={estimator!r}, target={target!r}, "
                f"features={features!r}, params={params!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        estimator, target, features, params = self._args(node)
        return {
            "model": fit_estimator(
                inputs["frame"],
                estimator=estimator,
                target=target,
                features=features,
                params=params,
            )
        }
