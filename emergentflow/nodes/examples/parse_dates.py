"""
emergentflow.nodes.examples.parse_dates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.parse_dates`` — a *transform* node (1 in, 1 out).

Parses string column(s) to datetime and optionally extracts calendar components.
``execute`` calls ``emergentflow.clean.parse_dates`` directly and the code emitted by
``codegen`` calls the same wrapper via the ``ef.`` alias, so the two paths are
equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clean import DATE_ERRORS, parse_dates
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class ParseDates(NodeDefinition):
    """Parse string column(s) to datetime and optionally extract calendar components."""

    type = "clean.parse_dates"
    version = 1
    family = "clean"
    label = "Parse Dates"
    category = "Transform"
    description = (
        "Parse string column(s) to datetime and optionally extract calendar components "
        "(year, month, day, quarter, ...) into new columns."
    )

    column_effect = ColumnEffect(kind=ColumnEffectKind.PASSTHROUGH)

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame containing the date column(s) to parse.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The DataFrame with the parsed datetime column(s) and any extracted components.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            required=True,
            label="Columns",
            help="Column(s) to parse as datetimes.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="format",
            type_token="str",
            default=None,
            label="Format",
            help="Optional strptime format (e.g. %Y-%m-%d). Leave unset to let pandas infer.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="errors",
            type_token="str",
            default="raise",
            label="On error",
            help="raise fails on an unparseable value; coerce turns it into NaT.",
            hints=ValidationHints(choices=list(DATE_ERRORS), widget="select"),
        ),
        ParamSpec(
            name="components",
            type_token="list[str]",
            default=None,
            label="Components",
            help=(
                "Calendar components to extract into new <column>_<component> columns. "
                "One or more of: year, month, day, dayofweek, dayofyear, quarter, hour, "
                "minute, second."
            ),
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "columns": values.get("columns") or [],
            "format": values.get("format"),
            "errors": values.get("errors") or "raise",
            "components": values.get("components"),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.parse_dates("
                f"{ctx.in_var('frame')}, columns={args['columns']!r}, "
                f"format={args['format']!r}, errors={args['errors']!r}, "
                f"components={args['components']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": parse_dates(
                inputs["frame"],
                columns=args["columns"],
                format=args["format"],
                errors=args["errors"],
                components=args["components"],
            )
        }
