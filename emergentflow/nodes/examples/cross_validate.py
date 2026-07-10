"""
emergentflow.nodes.examples.cross_validate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.cross_validate`` — cross-validation scoring for a single curated,
``fit``-archetype (supervised) estimator (Epic 8, Story 8 / ADR 0016).

Unlike ``ml.grid_search``, this node produces no ``Model`` output: sklearn's
``cross_validate`` fits and discards its internal per-fold models by default and has no single
canonical "best" estimator to keep, so this is a pure evaluation step (one ``DataFrame``
output, per-fold scores). Restricted to ``fit``-archetype estimators (classifiers/regressors).
``execute`` calls ``emergentflow.ml.cross_validate`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.ml import cross_validate
from emergentflow.ml.registry import keys_for_archetype

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class CrossValidate(NodeDefinition):
    """Cross-validate a curated, fit-archetype sklearn estimator."""

    type = "ml.cross_validate"
    version = 1
    family = "ml"
    label = "Cross Validate"
    category = "Machine Learning"
    description = "Cross-validate a curated, fit-archetype sklearn estimator."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing features and the target column.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One row per cross-validation fold, with test_score/fit_time/score_time.",
        ),
    ]
    params = [
        ParamSpec(
            name="estimator",
            type_token="str",
            required=True,
            label="Estimator",
            help="Which allow-listed sklearn classifier/regressor to cross-validate.",
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
        ParamSpec(
            name="cv",
            type_token="int",
            default=5,
            label="CV folds",
            help="Number of cross-validation folds.",
        ),
        ParamSpec(
            name="scoring",
            type_token="str",
            default=None,
            label="Scoring metric",
            help="sklearn scoring string (e.g. 'accuracy', 'r2'); unset uses the estimator's "
            "default scorer.",
        ),
    ]

    def _args(
        self, node: Node
    ) -> tuple[str, str, list[str] | None, dict[str, Any], int, str | None]:
        values = {p.name: p.value for p in node.params}
        estimator = values.get("estimator")
        target = values.get("target")
        features = values.get("features")
        params = values.get("params") or {}
        cv = values.get("cv", 5)
        scoring = values.get("scoring")
        return (
            cast(str, estimator),
            cast(str, target),
            cast("list[str] | None", features),
            cast("dict[str, Any]", params),
            cast(int, cv),
            cast("str | None", scoring),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        estimator, target, features, params, cv, scoring = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.ml.cross_validate("
                f"{ctx.in_var('frame')}, estimator={estimator!r}, target={target!r}, "
                f"features={features!r}, params={params!r}, cv={cv!r}, scoring={scoring!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        estimator, target, features, params, cv, scoring = self._args(node)
        return {
            "result": cross_validate(
                inputs["frame"],
                estimator=estimator,
                target=target,
                features=features,
                params=params,
                cv=cv,
                scoring=scoring,
            )
        }
