"""
emergentflow.nodes.examples.funnel
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.funnel`` — a *transform* node (1 in, 1 out).

Real, pandas-backed per-step conversion/drop-off funnel (Epic 16). ``execute`` calls
``emergentflow.stats.funnel`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by
construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import funnel

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Funnel(NodeDefinition):
    """Per-step conversion + drop-off funnel over an event log."""

    type = "stats.funnel"
    version = 1
    family = "stats"
    label = "Funnel"
    category = "Statistics"
    description = "Per-step conversion and drop-off funnel over an event log."

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the user and event columns.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="Tidy per-step conversion/drop-off funnel table.",
        ),
    ]
    params = [
        ParamSpec(
            name="user_col",
            type_token="str",
            required=True,
            label="User column",
            help="Column identifying each user.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="event_col",
            type_token="str",
            required=True,
            label="Event column",
            help="Column with each row's event name.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="steps",
            type_token="list[str]",
            required=True,
            label="Steps",
            help="Ordered list of event names defining the funnel.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str, list[str]]:
        values = {p.name: p.value for p in node.params}
        user_col = values.get("user_col")
        event_col = values.get("event_col")
        steps = values.get("steps")
        return cast(str, user_col), cast(str, event_col), cast("list[str]", steps)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        user_col, event_col, steps = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.stats.funnel({ctx.in_var('frame')}, "
                f"user_col={user_col!r}, event_col={event_col!r}, steps={steps!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        user_col, event_col, steps = self._args(node)
        return {
            "result": funnel(
                inputs["frame"],
                user_col=user_col,
                event_col=event_col,
                steps=steps,
            )
        }
