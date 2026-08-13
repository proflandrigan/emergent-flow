"""
emergentflow.nodes.examples.tune_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.tune_model`` — randomized hyperparameter search over a single curated,
``fit``-archetype (supervised) estimator (Epic 8, Story 8 / ADR 0016).

Restricted to ``fit``-archetype estimators (classifiers/regressors) -- clustering and
transformer archetypes are out of scope for this node (a distinct, deferred model-selection
problem). ``execute`` calls ``emergentflow.ml.tune_model`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.ml import tune_model
from emergentflow.ml.registry import keys_for_archetype

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TuneModel(NodeDefinition):
    """Randomized-search a hyperparameter space for a curated, fit-archetype sklearn estimator."""

    type = "ml.tune_model"
    version = 1
    family = "ml"
    label = "Tune Model"
    category = "Machine Learning"
    description = "Randomized hyperparameter search for a curated, fit-archetype sklearn estimator."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing features and the target column.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The best-scoring fitted model, refit on the full input frame.",
        ),
        PortSpec(
            name="cv_results",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One row per sampled parameter combination, sorted by rank.",
        ),
    ]
    params = [
        ParamSpec(
            name="estimator",
            type_token="str",
            required=True,
            label="Estimator",
            help="Which allow-listed sklearn classifier/regressor to search.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", keys_for_archetype("fit")), widget="select"
            ),
        ),
        ParamSpec(
            name="param_distributions",
            type_token="dict[str, list[any]]",
            required=True,
            label="Parameter distributions",
            help="Constructor kwarg name -> list of candidate values to sample from.",
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
            name="n_iter",
            type_token="int",
            default=10,
            label="Sampling iterations",
            help="Number of parameter-distribution samples to evaluate.",
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
    ) -> tuple[str, dict[str, list[Any]], str, list[str] | None, int, int, str | None]:
        values = {p.name: p.value for p in node.params}
        estimator = values.get("estimator")
        param_dists = values.get("param_distributions") or {}
        target = values.get("target")
        features = values.get("features")
        n_iter = values.get("n_iter", 10)
        cv = values.get("cv", 5)
        scoring = values.get("scoring")
        return (
            cast(str, estimator),
            cast("dict[str, list[Any]]", param_dists),
            cast(str, target),
            cast("list[str] | None", features),
            cast(int, n_iter),
            cast(int, cv),
            cast("str | None", scoring),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        estimator, param_dists, target, features, n_iter, cv, scoring = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')}, {ctx.out_var('cv_results')} = ef.ml.tune_model("
                f"{ctx.in_var('frame')}, estimator={estimator!r}, "
                f"param_distributions={param_dists!r}, "
                f"target={target!r}, features={features!r}, n_iter={n_iter!r}, cv={cv!r}, "
                f"scoring={scoring!r}, random_state=0)"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        estimator, param_dists, target, features, n_iter, cv, scoring = self._args(node)
        model, cv_results = tune_model(
            inputs["frame"],
            estimator=estimator,
            param_distributions=param_dists,
            target=target,
            features=features,
            n_iter=n_iter,
            cv=cv,
            scoring=scoring,
        )
        return {"model": model, "cv_results": cv_results}
