"""
emergentflow.nodes.examples.drop_missing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.drop_missing`` — a *transform* node (1 in, 1 out).

Pandas-backed row/column dropper for missing values (Epic 1, Story 8). ``execute``
calls ``emergentflow.clean.drop_missing`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.clean import drop_missing
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class DropMissing(NodeDefinition):
    """Drop rows or columns that contain missing values."""

    type = "clean.drop_missing"
    version = 1
    family = "clean"
    label = "Drop Missing"
    category = "Transform"
    description = "Drop rows or columns that contain missing values."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame from which rows/columns with NA should be dropped.",
        ),
        PortSpec(
            name="frame",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The DataFrame with missing-value rows or columns removed.",
        ),
    ]
    params = [
        ParamSpec(
            name="axis",
            type_token="str",
            default="rows",
            label="Axis",
            help="Which axis to drop from: rows or columns.",
            hints=ValidationHints(choices=["rows", "columns"], widget="select"),
        ),
        ParamSpec(
            name="how",
            type_token="str",
            default="any",
            label="How",
            help="Drop if any or all cells in the row/column are NA.",
            hints=ValidationHints(choices=["any", "all"], widget="select"),
        ),
        ParamSpec(
            name="subset",
            type_token="list[str]",
            default=None,
            label="Subset",
            help="Columns to check for NA (row-axis only); empty/unset checks all.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, list[str] | None]:
        values = {p.name: p.value for p in node.params}
        axis = values.get("axis", "rows") or "rows"
        how = values.get("how", "any") or "any"
        subset = values.get("subset")
        return cast(str, axis), cast(str, how), cast("list[str] | None", subset)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        axis, how, subset = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.drop_missing("
                f"{ctx.in_var('frame')}, axis={axis!r}, how={how!r}, subset={subset!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        axis, how, subset = self._args(node)
        return {"frame": drop_missing(inputs["frame"], axis=axis, how=how, subset=subset)}
