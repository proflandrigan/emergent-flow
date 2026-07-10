"""
emergentflow.nodes.examples.eda_profile
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.eda_profile`` — a *transform* node (1 in, 1 out).

Real, pandas-backed per-column profile (Epic 12, Story 11). ``execute`` calls
``emergentflow.stats.profile`` directly and the code emitted by ``codegen``
calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent
by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import profile

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class EdaProfile(NodeDefinition):
    """Per-column profile: dtype, missingness, cardinality, skew/kurtosis."""

    type = "stats.eda_profile"
    version = 1
    family = "stats"
    label = "Profile"
    category = "Statistics"
    description = "Per-column profile: dtype, missingness, cardinality, skew/kurtosis."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame whose columns should be profiled.",
        ),
        PortSpec(
            name="summary",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Per-column profile as a tidy DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Columns to profile; empty/unset profiles all columns.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str] | None]:
        values = {p.name: p.value for p in node.params}
        columns = values.get("columns")
        return (cast("list[str] | None", columns),)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        (columns,) = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('summary')} = ef.stats.profile("
                f"{ctx.in_var('frame')}, columns={columns!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        (columns,) = self._args(node)
        return {"summary": profile(inputs["frame"], columns=columns)}
