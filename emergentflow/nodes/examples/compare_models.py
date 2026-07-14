"""
emergentflow.nodes.examples.compare_models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.compare_models`` — a PyCaret-style baseline model comparison node
(ADR 0016), thin wrapper over ``ef.ml.compare_models``.

Cross-validates every curated ``fit``-archetype estimator matching the chosen task (or an
explicit subset), and returns a sorted comparison table plus the top-ranked estimator refit on
the full input frame. ``execute`` calls ``emergentflow.ml.compare_models`` directly and the
code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue
from emergentflow.ml import compare_models
from emergentflow.ml.registry import keys_for_archetype

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class CompareModels(NodeDefinition):
    """Cross-validate every curated fit-archetype estimator matching a task and rank them."""

    type = "ml.compare_models"
    version = 1
    family = "ml"
    label = "Compare Models"
    category = "Machine Learning"
    description = "Cross-validate multiple curated estimators and rank them by held-out score."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing features and the target column.",
        ),
        PortSpec(
            name="comparison",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One row per compared estimator, with cross-validated metrics, sorted by "
            "the ranking metric.",
        ),
        PortSpec(
            name="model",
            direction=Direction.OUT,
            data_type="Model",
            help="The top-ranked estimator, refit on the full input frame.",
        ),
    ]
    params = [
        ParamSpec(
            name="task",
            type_token="str",
            required=True,
            label="Task",
            help="Whether to compare classifiers or regressors.",
            hints=ValidationHints(choices=["classification", "regression"], widget="select"),
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
            name="estimators",
            type_token="list[str]",
            default=None,
            label="Estimators",
            help="Subset of curated fit-archetype estimators to compare; empty/unset "
            "compares every curated estimator matching the chosen task.",
            hints=ValidationHints(choices=cast("list[ParamValue]", keys_for_archetype("fit"))),
        ),
        ParamSpec(
            name="cv",
            type_token="int",
            default=5,
            label="CV folds",
            help="Number of cross-validation folds.",
        ),
        ParamSpec(
            name="sort_by",
            type_token="str",
            default=None,
            label="Sort by",
            help="Metric to rank by; unset uses accuracy (classification) or r2 (regression).",
        ),
    ]

    def _args(
        self, node: Node
    ) -> tuple[str, str, list[str] | None, list[str] | None, int, str | None]:
        values = {p.name: p.value for p in node.params}
        task = values.get("task")
        target = values.get("target")
        features = values.get("features")
        estimators = values.get("estimators")
        cv = values.get("cv", 5)
        sort_by = values.get("sort_by")
        return (
            cast(str, task),
            cast(str, target),
            cast("list[str] | None", features),
            cast("list[str] | None", estimators),
            cast(int, cv),
            cast("str | None", sort_by),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        task, target, features, estimators, cv, sort_by = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('comparison')}, {ctx.out_var('model')} = "
                f"ef.ml.compare_models({ctx.in_var('frame')}, task={task!r}, "
                f"target={target!r}, features={features!r}, estimators={estimators!r}, "
                f"cv={cv!r}, sort_by={sort_by!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        task, target, features, estimators, cv, sort_by = self._args(node)
        comparison, model = compare_models(
            inputs["frame"],
            task=task,
            target=target,
            features=features,
            estimators=estimators,
            cv=cv,
            sort_by=sort_by,
        )
        return {"comparison": comparison, "model": model}
