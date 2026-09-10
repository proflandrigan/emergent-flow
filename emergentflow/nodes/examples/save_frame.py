"""
emergentflow.nodes.examples.save_frame
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.save_frame`` — dataset persistence (issue #164 Gap 6).

Writes the input frame to a local parquet/csv/json file (or a Hive-partitioned
directory) and passes the frame through unchanged, so the node can be inserted
mid-graph without restructuring downstream edges. ``execute`` calls
``emergentflow.data.save_frame`` directly and ``codegen`` calls the same wrapper via the
``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.data import save_frame
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node
from emergentflow.ir.params import ParamValue

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext

_FORMAT_CHOICES = ["parquet", "csv", "json"]


@register
class SaveFrame(NodeDefinition):
    """Write the input DataFrame to a file and pass it through unchanged."""

    type = "data.save_frame"
    version = 1
    family = "data"
    label = "Save Frame"
    category = "Export"
    description = "Write the input DataFrame to parquet/csv/json and pass it through."

    column_effect = ColumnEffect(kind=ColumnEffectKind.PASSTHROUGH)

    # Effectful: a cached result would skip the write on re-run (and never recreate a deleted
    # file), so never serve this node from the execution cache.
    cacheable = False

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.IN,
            data_type="DataFrame",
            help="The input DataFrame to persist.",
        ),
        PortSpec(
            name="result",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The same DataFrame, unchanged (chainable pass-through).",
        ),
    ]
    params = [
        ParamSpec(
            name="path",
            type_token="str",
            required=True,
            label="Output path",
            help="File or (with partition_by) directory path to write to.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="format",
            type_token="str",
            default="parquet",
            label="Format",
            help="parquet (default), csv, or json.",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", _FORMAT_CHOICES), widget="select"
            ),
        ),
        ParamSpec(
            name="mode",
            type_token="str",
            default="overwrite",
            label="Mode",
            help="overwrite (default) or error (refuse to clobber an existing file).",
            hints=ValidationHints(
                choices=cast("list[ParamValue]", ["overwrite", "error"]), widget="select"
            ),
        ),
        ParamSpec(
            name="partition_by",
            type_token="list[str]",
            default=None,
            label="Partition by",
            help="Optional columns to write a Hive-partitioned directory by.",
            hints=ValidationHints(widget="column"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        return {
            "path": cast(str, values.get("path")),
            "format": cast(str, values.get("format", "parquet")),
            "mode": cast(str, values.get("mode", "overwrite")),
            "partition_by": cast("list[str] | None", values.get("partition_by")),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        codegen_format = f", format={args['format']!r}" if args["format"] != "parquet" else ""
        codegen_mode = f", mode={args['mode']!r}" if args["mode"] != "overwrite" else ""
        codegen_part = f", partition_by={args['partition_by']!r}" if args["partition_by"] else ""
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('result')} = ef.data.save_frame("
                f"{ctx.in_var('frame')}, path={args['path']!r}"
                f"{codegen_format}{codegen_mode}{codegen_part})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        args = self._args(node)
        return {
            "result": save_frame(
                inputs["frame"],
                path=args["path"],
                format=args["format"],
                mode=args["mode"],
                partition_by=args["partition_by"],
            )
        }
