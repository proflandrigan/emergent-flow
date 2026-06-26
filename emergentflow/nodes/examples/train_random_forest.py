"""
emergentflow.nodes.examples.train_random_forest
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.train_random_forest`` — a *transform* node (1 in, 1 out).

Real, scikit-learn-backed random-forest fitter (Epic 1, Story 11). A single
``task`` param selects ``RandomForestClassifier`` or ``RandomForestRegressor``.
``execute`` calls ``emergentflow.ml.train_random_forest`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the
two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import FOREST_TASKS, train_random_forest

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TrainRandomForest(NodeDefinition):
    """Fit a random-forest classifier or regressor and return a FittedModel."""

    type = "ml.train_random_forest"
    version = 1
    family = "ml"
    label = "Train Random Forest"
    category = "Machine Learning"
    description = "Fit a random-forest classifier or regressor."

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
            help="The fitted random-forest model.",
        ),
    ]
    params = [
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
            name="task",
            type_token="str",
            default="classification",
            label="Task",
            help="Whether to fit a classifier or a regressor.",
            hints=ValidationHints(choices=list(FOREST_TASKS), widget="select"),
        ),
        ParamSpec(
            name="n_estimators",
            type_token="int",
            default=100,
            label="Number of estimators",
            help="Number of trees in the forest.",
            hints=ValidationHints(min=1, widget="number"),
        ),
        ParamSpec(
            name="random_state",
            type_token="int",
            default=0,
            label="Random state",
            help="Seed for reproducibility.",
            hints=ValidationHints(widget="number"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, list[str] | None, str, int, int]:
        values = {p.name: p.value for p in node.params}
        target = values.get("target")
        features = values.get("features")
        task = values.get("task", "classification") or "classification"
        n_estimators = values.get("n_estimators", 100)
        if n_estimators is None:
            n_estimators = 100
        random_state = values.get("random_state", 0)
        if random_state is None:
            random_state = 0
        return (
            cast(str, target),
            cast("list[str] | None", features),
            cast(str, task),
            cast(int, n_estimators),
            cast(int, random_state),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        target, features, task, n_estimators, random_state = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('model')} = ef.ml.train_random_forest("
                f"{ctx.in_var('frame')}, target={target!r}, features={features!r}, "
                f"task={task!r}, n_estimators={n_estimators!r}, random_state={random_state!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        target, features, task, n_estimators, random_state = self._args(node)
        return {
            "model": train_random_forest(
                inputs["frame"],
                target=target,
                features=features,
                task=task,
                n_estimators=n_estimators,
                random_state=random_state,
            )
        }
