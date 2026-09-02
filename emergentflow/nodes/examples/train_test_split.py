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
from emergentflow.ir.params import ParamValue
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
    version = 2
    family = "ml"
    label = "Train/Test Split"
    category = "Machine Learning"
    description = "Split a DataFrame into train and test sets."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
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
        ParamSpec(
            name="strategy",
            type_token="str",
            default="random",
            label="Strategy",
            help="Split strategy: random, stratified, grouped, or temporal.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["random", "stratified", "grouped", "temporal"]),
                widget="select",
            ),
        ),
        ParamSpec(
            name="stratify_col",
            type_token="str",
            default=None,
            label="Stratify column",
            help="Column to stratify on (for strategy='stratified').",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="group_col",
            type_token="str",
            default=None,
            label="Group column",
            help="Column to group by (for strategy='grouped').",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="time_col",
            type_token="str",
            default=None,
            label="Time column",
            help="Column to sort by (for strategy='temporal').",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        test_size = values.get("test_size", 0.25)
        if test_size is None:
            test_size = 0.25
        random_state = values.get("random_state", 0)
        if random_state is None:
            random_state = 0
        strategy = values.get("strategy") or "random"
        stratify_col = values.get("stratify_col")
        group_col = values.get("group_col")
        time_col = values.get("time_col")
        return {
            "test_size": cast(float, test_size),
            "random_state": cast(int, random_state),
            "strategy": cast(str, strategy),
            "stratify_col": cast("str | None", stratify_col),
            "group_col": cast("str | None", group_col),
            "time_col": cast("str | None", time_col),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        codegen_strategy = f", strategy={args['strategy']!r}"
        codegen_stratify = (
            f", stratify_col={args['stratify_col']!r}" if args["stratify_col"] else ""
        )
        codegen_group = f", group_col={args['group_col']!r}" if args["group_col"] else ""
        codegen_time = f", time_col={args['time_col']!r}" if args["time_col"] else ""
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('train')}, {ctx.out_var('test')} = ef.ml.train_test_split("
                f"{ctx.in_var('frame')}, test_size={args['test_size']!r}, "
                f"random_state={args['random_state']!r}"
                f"{codegen_strategy}{codegen_stratify}{codegen_group}{codegen_time})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        result = train_test_split(
            inputs["frame"],
            test_size=args["test_size"],
            random_state=args["random_state"],
            strategy=args["strategy"],
            stratify_col=args["stratify_col"],
            group_col=args["group_col"],
            time_col=args["time_col"],
        )
        return {"train": result[0], "test": result[1]}
