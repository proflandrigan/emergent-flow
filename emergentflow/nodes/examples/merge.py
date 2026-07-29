"""
emergentflow.nodes.examples.merge
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.merge`` — a *transform* node (2 in, 1 out).

Pandas-parity join over two DataFrames. ``execute`` calls
``emergentflow.clean.merge`` directly and the code emitted by ``codegen``
calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import merge
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Merge(NodeDefinition):
    """Join two DataFrames on key column(s)."""

    type = "clean.merge"
    version = 1
    family = "clean"
    label = "Merge"
    category = "Transform"
    description = (
        "Join two DataFrames on key column(s) (pandas-style inner/left/right/outer/cross)."
    )

    ports = [
        PortSpec(
            name="left",
            label="Left",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The left DataFrame.",
        ),
        PortSpec(
            name="right",
            label="Right",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The right DataFrame.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The joined DataFrame.",
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
            label="Left on",
            help="Left-frame key column(s). Pair with right_on when column names differ.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="right_on",
            type_token="list[str]",
            default=None,
            label="Right on",
            help="Right-frame key column(s). Pair with left_on when column names differ.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="how",
            type_token="str",
            default="inner",
            label="How",
            help="Join type.",
            hints=ValidationHints(
                choices=["inner", "left", "right", "outer", "cross"],
                widget="select",
            ),
        ),
        ParamSpec(
            name="suffixes",
            type_token="list[str]",
            default=["_x", "_y"],
            label="Suffixes",
            help="Suffixes appended to overlapping non-key column names from (left, right).",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="validate",
            type_token="str",
            default=None,
            label="Validate",
            help="Optional relationship check: 1:1, 1:m, m:1, or m:m. Raises if violated.",
            hints=ValidationHints(
                choices=["1:1", "1:m", "m:1", "m:m"],
                widget="select",
            ),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        suffixes = cast(list, values.get("suffixes") or ["_x", "_y"])
        return {
            "on": values.get("on"),
            "left_on": values.get("left_on"),
            "right_on": values.get("right_on"),
            "how": values.get("how") or "inner",
            "suffixes": tuple(suffixes),
            "validate": values.get("validate"),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.merge("
                f"{ctx.in_var('left')}, {ctx.in_var('right')}, "
                f"on={args['on']!r}, left_on={args['left_on']!r}, right_on={args['right_on']!r}, "
                f"how={args['how']!r}, suffixes={args['suffixes']!r}, "
                f"validate={args['validate']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": merge(
                inputs["left"],
                inputs["right"],
                on=args["on"],
                left_on=args["left_on"],
                right_on=args["right_on"],
                how=args["how"],
                suffixes=args["suffixes"],
                validate=args["validate"],
            )
        }
