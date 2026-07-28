"""
emergentflow.nodes.examples.semi_join
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.semi_join`` — a *transform* node (2 in, 1 out).

Filters one DataFrame's rows by key membership against another (semi-join
when ``mode="keep"``, anti-join when ``mode="exclude"``) — never widens the
output with columns from the keys frame. ``execute`` calls
``emergentflow.clean.semi_join`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths
are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clean import semi_join
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class SemiJoin(NodeDefinition):
    """Filter a DataFrame's rows by key membership against another DataFrame."""

    type = "clean.semi_join"
    version = 1
    family = "clean"
    label = "Semi Join"
    category = "Transform"
    description = (
        "Keep or exclude rows whose key column(s) match another DataFrame "
        "(semi-join / anti-join); never adds columns from the keys frame."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The DataFrame to filter.",
        ),
        PortSpec(
            name="keys",
            label="Keys",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The DataFrame whose key column(s) define membership.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The filtered DataFrame (same columns as the input Data).",
        ),
    ]
    params = [
        ParamSpec(
            name="on",
            type_token="list[str]",
            default=None,
            label="On",
            help="Column(s) shared by both frames. Alternative to left_on/right_on.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="left_on",
            type_token="list[str]",
            default=None,
            label="Left on (Data)",
            help="Key column(s) on the Data frame. Pair with right_on when column names differ.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="right_on",
            type_token="list[str]",
            default=None,
            label="Right on (Keys)",
            help="Key column(s) on the Keys frame. Pair with left_on when column names differ.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="mode",
            type_token="str",
            default="keep",
            label="Mode",
            help="Keep matching rows (semi-join) or drop them (anti-join).",
            hints=ValidationHints(
                choices=["keep", "exclude"],
                widget="select",
            ),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "on": values.get("on"),
            "left_on": values.get("left_on"),
            "right_on": values.get("right_on"),
            "mode": values.get("mode") or "keep",
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.semi_join("
                f"{ctx.in_var('frame')}, {ctx.in_var('keys')}, "
                f"on={args['on']!r}, left_on={args['left_on']!r}, right_on={args['right_on']!r}, "
                f"mode={args['mode']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": semi_join(
                inputs["frame"],
                inputs["keys"],
                on=args["on"],
                left_on=args["left_on"],
                right_on=args["right_on"],
                mode=args["mode"],
            )
        }
