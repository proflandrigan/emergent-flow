"""
emergentflow.nodes.examples.concat
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.concat`` — row-wise union of two or more DataFrames (Epic 16, Story 7).

Takes a variadic ``Cardinality.MANY`` IN port (the same fan-in machinery proven by
``recommend.compare``) and emits a single schema-aligned ``DataFrame``. ``execute`` calls
``emergentflow.clean.concat`` directly and the code emitted by ``codegen`` calls the same
wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clean import concat
from emergentflow.ir.common import Cardinality, Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Concat(NodeDefinition):
    """Row-wise union of two or more DataFrames, aligned by column name."""

    type = "clean.concat"
    version = 1
    family = "clean"
    label = "Concat"
    category = "Transform"
    description = (
        "Row-wise union of two or more DataFrames, schema-aligned by column name, with an "
        "optional provenance column."
    )

    ports = [
        PortSpec(
            name="frames",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            cardinality=Cardinality.MANY,
            help="Two or more DataFrames to stack row-wise.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The row-wise union of the input frames.",
        ),
    ]
    params = [
        ParamSpec(
            name="source_column",
            type_token="str",
            default=None,
            label="Source column",
            help=(
                "Optional name for a provenance column recording which input frame each row "
                "came from."
            ),
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="keys",
            type_token="list[str]",
            default=None,
            label="Keys",
            help=(
                "Optional label per input frame for the provenance column. Defaults to "
                "frame_0, frame_1, ..."
            ),
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="ignore_index",
            type_token="bool",
            default=True,
            label="Reset index",
            help="Renumber the result index 0..n-1.",
            hints=ValidationHints(widget="checkbox"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        ignore_index = values.get("ignore_index")
        return {
            "source_column": values.get("source_column"),
            "keys": values.get("keys"),
            "ignore_index": True if ignore_index is None else ignore_index,
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.concat("
                f"{ctx.in_var('frames')}, source_column={args['source_column']!r}, "
                f"keys={args['keys']!r}, ignore_index={args['ignore_index']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": concat(
                inputs["frames"],
                source_column=args["source_column"],
                keys=args["keys"],
                ignore_index=args["ignore_index"],
            )
        }
