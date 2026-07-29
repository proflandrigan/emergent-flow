"""
emergentflow.nodes.examples.data_dictionary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``stats.data_dictionary`` — a *transform* node (1 in, 1 out).

Real, ``ef.stats.profile``-backed data-dictionary generation (Epic 16, Story 21). ``execute``
calls ``emergentflow.stats.data_dictionary`` directly and the code emitted by ``codegen`` calls
the same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction
(ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.stats import data_dictionary

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class DataDictionary(NodeDefinition):
    """Auto-emit a documented schema (type, null rate, cardinality, top values) per column."""

    type = "stats.data_dictionary"
    version = 1
    family = "stats"
    label = "Data Dictionary"
    category = "Statistics"
    description = (
        "Auto-emit a documented schema per column: type, null rate, cardinality, "
        "range/top-values, and optional user notes."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The DataFrame to document.",
        ),
        PortSpec(
            name="dictionary",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="One row per column: type/null-rate/cardinality/range/top-values/notes.",
        ),
    ]
    params = [
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Optional subset of columns to document; defaults to every column.",
            hints=ValidationHints(widget="json"),
        ),
        ParamSpec(
            name="top_n",
            type_token="int",
            default=5,
            label="Top N values",
            help="How many of each column's most frequent values to record.",
            hints=ValidationHints(widget="number", min=1),
        ),
        ParamSpec(
            name="notes",
            type_token="dict",
            default=None,
            label="Column notes",
            help="Optional map of column name to a free-text note, carried through untouched.",
            hints=ValidationHints(widget="json"),
        ),
    ]

    def _args(self, node: Node) -> tuple[list[str] | None, int, dict[str, str] | None]:
        values = {p.name: p.value for p in node.params}
        top_n = values.get("top_n", 5)
        if top_n is None:
            top_n = 5
        return (
            cast("list[str] | None", values.get("columns")),
            cast(int, top_n),
            cast("dict[str, str] | None", values.get("notes")),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        columns, top_n, notes = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('dictionary')} = ef.stats.data_dictionary("
                f"{ctx.in_var('frame')}, columns={columns!r}, top_n={top_n!r}, "
                f"notes={notes!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        columns, top_n, notes = self._args(node)
        return {
            "dictionary": data_dictionary(
                inputs["frame"], columns=columns, top_n=top_n, notes=notes
            )
        }
