"""
emergentflow.nodes.examples.outlier_detect
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.outlier_detect`` — the "outlier_detect" archetype node (Epic 8, ADR 0016).

Fits a curated, allow-listed sklearn outlier/novelty-detection estimator (any estimator
registered with ``archetype="outlier_detect"`` in ``emergentflow.ml.registry``) and
immediately labels the SAME input frame, returning both a fitted ``Model`` and the labeled
``DataFrame`` (an ``outlier`` column added, with sklearn's ``-1``/``1`` convention).
The ``estimator`` choice list is computed at import time from the live registry, so it grows
automatically as more estimators are curated into the allow-list. ``execute`` calls
``emergentflow.ml.fit_and_detect`` directly and the code emitted by ``codegen`` calls the
same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002).

Unlike ``ml.fit_estimator`` (fit now, predict on new data later via a separate
``ml.apply_estimator`` node), this node produces its labeled frame in the SAME step as
fitting; a later ``ml.apply_estimator`` call on the resulting ``Model`` against a DIFFERENT
frame can predict outlier labels when the underlying estimator supports ``.predict``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.ml import fit_and_detect
from emergentflow.ml.registry import outlier_detector_keys

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class OutlierDetect(NodeDefinition):
    """Fit a curated, allow-listed sklearn outlier/novelty-detection estimator."""

    type = "ml.outlier_detect"
    version = 1
    family = "ml"
    label = "Outlier Detect"
    category = "Machine Learning"
    description = "Fit a curated, allow-listed sklearn outlier/novelty-detection estimator."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing features.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The fitted model.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The input frame with an added 'outlier' column (-1=outlier, 1=inlier).",
        ),
    ]
    params = [
        ParamSpec(
            name="estimator",
            type_token="str",
            required=True,
            label="Estimator",
            help="Which allow-listed sklearn outlier/novelty-detection estimator to fit.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", outlier_detector_keys()),
                widget="select",
            ),
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Columns to use as features; empty/unset uses every column.",
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

    def _args(self, node: Node) -> tuple[str, list[str] | None, dict[str, Any]]:
        values = {p.name: p.value for p in node.params}
        estimator = values.get("estimator")
        features = values.get("features")
        params = values.get("params") or {}
        return (
            cast(str, estimator),
            cast("list[str] | None", features),
            cast("dict[str, Any]", params),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        estimator, features, params = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')}, {ctx.out_var('result')} = ef.ml.fit_and_detect("
                f"{ctx.in_var('frame')}, estimator={estimator!r}, "
                f"features={features!r}, params={params!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        estimator, features, params = self._args(node)
        model, result = fit_and_detect(
            inputs["frame"],
            estimator=estimator,
            features=features,
            params=params,
        )
        return {"model": model, "result": result}
