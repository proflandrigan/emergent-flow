"""
emergentflow.nodes.examples.reshape
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``clean.reshape`` — a *transform* node (1 in, 1 out).

Long<->wide reshaping (pivot / melt). ``execute`` calls ``emergentflow.clean.reshape``
directly and the code emitted by ``codegen`` calls the same wrapper via the ``ef.`` alias,
so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clean import PIVOT_AGGFUNCS, RESHAPE_MODES, reshape
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class Reshape(NodeDefinition):
    """Reshape a DataFrame between long and wide form (pivot / melt)."""

    type = "clean.reshape"
    version = 1
    family = "clean"
    label = "Reshape"
    category = "Transform"
    description = (
        "Reshape a DataFrame between long and wide form: pivot (long->wide) or melt (wide->long)."
    )

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to reshape.",
        ),
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The reshaped DataFrame (flat columns, reset index).",
        ),
    ]
    params = [
        ParamSpec(
            name="mode",
            type_token="str",
            default="pivot",
            label="Mode",
            help="pivot reshapes long->wide; melt reshapes wide->long.",
            hints=ValidationHints(choices=list(RESHAPE_MODES), widget="select"),
        ),
        ParamSpec(
            name="index",
            type_token="list[str]",
            default=None,
            label="Index",
            help="Pivot only: column(s) whose values become the output rows.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Pivot only: column(s) whose values become the output column names.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="values",
            type_token="list[str]",
            default=None,
            label="Values",
            help="Pivot only: column(s) to fill the cells with. Defaults to all remaining columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="aggfunc",
            type_token="str",
            default=None,
            label="Aggregate",
            help=(
                "Pivot only: how to aggregate duplicate index/column pairs. "
                "Required when duplicates exist."
            ),
            hints=ValidationHints(choices=list(PIVOT_AGGFUNCS), widget="select"),
        ),
        ParamSpec(
            name="id_vars",
            type_token="list[str]",
            default=None,
            label="Id vars",
            help="Melt only: column(s) to keep as identifier columns.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="value_vars",
            type_token="list[str]",
            default=None,
            label="Value vars",
            help="Melt only: column(s) to unpivot. Defaults to every non-id column.",
            hints=ValidationHints(widget="column"),
        ),
        ParamSpec(
            name="var_name",
            type_token="str",
            default="variable",
            label="Variable name",
            help="Melt only: name of the output column holding the former column names.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="value_name",
            type_token="str",
            default="value",
            label="Value name",
            help="Melt only: name of the output column holding the values.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        var_name = values.get("var_name")
        value_name = values.get("value_name")
        return {
            "mode": values.get("mode") or "pivot",
            "index": values.get("index"),
            "columns": values.get("columns"),
            "values": values.get("values"),
            "aggfunc": values.get("aggfunc"),
            "id_vars": values.get("id_vars"),
            "value_vars": values.get("value_vars"),
            "var_name": "variable" if var_name is None else var_name,
            "value_name": "value" if value_name is None else value_name,
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.clean.reshape("
                f"{ctx.in_var('frame')}, mode={args['mode']!r}, "
                f"index={args['index']!r}, columns={args['columns']!r}, "
                f"values={args['values']!r}, aggfunc={args['aggfunc']!r}, "
                f"id_vars={args['id_vars']!r}, value_vars={args['value_vars']!r}, "
                f"var_name={args['var_name']!r}, value_name={args['value_name']!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "frame": reshape(
                inputs["frame"],
                mode=args["mode"],
                index=args["index"],
                columns=args["columns"],
                values=args["values"],
                aggfunc=args["aggfunc"],
                id_vars=args["id_vars"],
                value_vars=args["value_vars"],
                var_name=args["var_name"],
                value_name=args["value_name"],
            )
        }
