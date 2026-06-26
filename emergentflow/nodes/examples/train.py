"""
emergentflow.nodes.examples.train
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.train_classifier`` — a *transform* node (1 in, 1 out).

Real, scikit-learn-backed logistic-regression classifier (Epic 1, Story 8).
``execute`` calls ``emergentflow.ml.train_classifier`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the
two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import train_classifier

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TrainClassifier(NodeDefinition):
    """Train a logistic-regression classifier and report inspectable metrics."""

    type = "ml.train_classifier"
    version = 2
    family = "ml"
    label = "Train Classifier"
    category = "Machine Learning"
    description = "Train a logistic-regression classifier and report evaluation metrics."

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
            data_type="ClassifierResult",
            help="Inspectable training/evaluation metrics for the fitted classifier.",
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
            name="test_size",
            type_token="float",
            default=0.25,
            label="Test size",
            help="Fraction of rows held out for evaluation.",
            hints=ValidationHints(min=0.0, max=1.0, widget="number"),
        ),
        ParamSpec(
            name="random_state",
            type_token="int",
            default=0,
            label="Random state",
            help="Seed controlling the train/test split and model fit.",
            hints=ValidationHints(widget="number"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, list[str] | None, float, int]:
        values = {p.name: p.value for p in node.params}
        target = values.get("target")
        features = values.get("features")
        test_size = values.get("test_size", 0.25)
        if test_size is None:
            test_size = 0.25
        random_state = values.get("random_state", 0)
        if random_state is None:
            random_state = 0
        return (
            cast(str, target),
            cast("list[str] | None", features),
            cast(float, test_size),
            cast(int, random_state),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        target, features, test_size, random_state = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.ml.train_classifier({ctx.in_var('frame')}, "
                f"target={target!r}, features={features!r}, test_size={test_size!r}, "
                f"random_state={random_state!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        target, features, test_size, random_state = self._args(node)
        return {
            "result": train_classifier(
                inputs["frame"],
                target=target,
                features=features,
                test_size=test_size,
                random_state=random_state,
            )
        }
