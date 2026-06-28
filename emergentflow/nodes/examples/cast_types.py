"""
emergentflow.nodes.examples.cast_types
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.cast_types`` — a *transform* node (1 in, 1 out).

Real, pandas-backed type caster (Epic 1, Story 8). ``execute`` calls
``emergentflow.clean.cast_types`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import cast_types
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class CastTypes(NodeDefinition):
    """Cast selected columns to new data types."""

    type = "clean.cast_types"
    version = 1
    family = "clean"
    label = "Cast Types"
    category = "Transform"
    description = "Cast selected columns to new data types."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame whose columns should be cast.",
        ),
        PortSpec(
            name="frame",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The DataFrame with cast columns.",
        ),
    ]
    params = [
        ParamSpec(
            name="dtypes",
            type_token="dict[str, str]",
            default=None,
            required=True,
            label="Type Mapping",
            help="Mapping of column name to dtype (int/float/str/bool/category).",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, str]:
        values = {p.name: p.value for p in node.params}
        dtypes = cast("dict[str, str]", values.get("dtypes"))
        return dtypes

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        dtypes = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.cast_types("
                f"{ctx.in_var('frame')}, dtypes={dtypes!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        dtypes = self._args(node)
        return {"frame": cast_types(inputs["frame"], dtypes=dtypes)}
