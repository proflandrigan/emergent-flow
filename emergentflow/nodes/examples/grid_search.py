"""
emergentflow.nodes.examples.grid_search
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.grid_search`` — hyperparameter search over a single curated,
``fit``-archetype (supervised) estimator (Epic 8, Story 8 / ADR 0016).

Restricted to ``fit``-archetype estimators (classifiers/regressors) -- clustering and
transformer archetypes are out of scope for this node (a distinct, deferred model-selection
problem). ``execute`` calls ``emergentflow.ml.grid_search`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.ml import grid_search
from emergentflow.ml.registry import keys_for_archetype

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class GridSearch(NodeDefinition):
    """Search a hyperparameter grid for a curated, fit-archetype sklearn estimator."""

    type = "ml.grid_search"
    version = 1
    family = "ml"
    label = "Grid Search"
    category = "Machine Learning"
    description = "Search a hyperparameter grid for a curated, fit-archetype sklearn estimator."

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
            help="The best-scoring fitted model, refit on the full input frame.",
        ),
        PortSpec(
            name="cv_results",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One row per searched parameter combination, sorted by rank.",
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
            name="param_grid",
            type_token="dict[str, list[any]]",
            required=True,
            label="Parameter grid",
            help="Constructor kwarg name -> list of candidate values to search.",
        ),
        ParamSpec(
            name="target",
            type_token="str",
            required=True,
            label="Target column",
            help="Column to predict.",
        ),
        ParamSpec(
            name="features",
            type_token="list[str]",
            default=None,
            label="Feature columns",
            help="Columns to use as features; empty/unset uses every other column.",
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
    ) -> tuple[str, dict[str, list[Any]], str, list[str] | None, int, str | None]:
        values = {p.name: p.value for p in node.params}
        estimator = values.get("estimator")
        param_grid = values.get("param_grid") or {}
        target = values.get("target")
        features = values.get("features")
        cv = values.get("cv", 5)
        scoring = values.get("scoring")
        return (
            cast(str, estimator),
            cast("dict[str, list[Any]]", param_grid),
            cast(str, target),
            cast("list[str] | None", features),
            cast(int, cv),
            cast("str | None", scoring),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        estimator, param_grid, target, features, cv, scoring = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')}, {ctx.out_var('cv_results')} = ef.ml.grid_search("
                f"{ctx.in_var('frame')}, estimator={estimator!r}, param_grid={param_grid!r}, "
                f"target={target!r}, features={features!r}, cv={cv!r}, scoring={scoring!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        estimator, param_grid, target, features, cv, scoring = self._args(node)
        model, cv_results = grid_search(
            inputs["frame"],
            estimator=estimator,
            param_grid=param_grid,
            target=target,
            features=features,
            cv=cv,
            scoring=scoring,
        )
        return {"model": model, "cv_results": cv_results}
