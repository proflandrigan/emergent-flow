"""
emergentflow.nodes.examples.train_test_split
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``ml.train_test_split`` — a *split* node (1 in, 2 out).

Real, scikit-learn-backed train/test splitter (Epic 1, Story 9).
``execute`` calls ``emergentflow.ml.train_test_split`` directly and the code
emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias, so the
two paths are equivalent by construction (ADR 0002).

This is the first reference node with two OUT ports; codegen emits a single
tuple-unpack assignment rather than two separate statements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ml import train_test_split

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class TrainTestSplit(NodeDefinition):
    """Split a DataFrame into train and test sets."""

    type = "ml.train_test_split"
    version = 1
    family = "ml"
    label = "Train/Test Split"
    category = "Machine Learning"
    description = "Split a DataFrame into train and test sets."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to split.",
        ),
        PortSpec(
            name="train",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The training split (rows held in for fitting).",
        ),
        PortSpec(
            name="test",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The test split (rows held out for evaluation).",
        ),
    ]
    params = [
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
            help="Seed controlling the train/test split.",
            hints=ValidationHints(widget="number"),
        ),
    ]

    def _args(self, node: Node) -> tuple[float, int]:
        values = {p.name: p.value for p in node.params}
        test_size = values.get("test_size", 0.25)
        if test_size is None:
            test_size = 0.25
        random_state = values.get("random_state", 0)
        if random_state is None:
            random_state = 0
        return cast(float, test_size), cast(int, random_state)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        test_size, random_state = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('train')}, {ctx.out_var('test')} = ef.ml.train_test_split("
                f"{ctx.in_var('frame')}, test_size={test_size!r}, random_state={random_state!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        test_size, random_state = self._args(node)
        result = train_test_split(inputs["frame"], test_size=test_size, random_state=random_state)
        return {"train": result[0], "test": result[1]}
