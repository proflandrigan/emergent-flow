"""
emergentflow.nodes.examples.load_parquet
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.load_parquet`` — a *source* node (0 inputs, 1 output).

Real, pandas/pyarrow-backed loader (Epic 6, Story 3). ``execute`` calls
``emergentflow.data.load_parquet`` directly and the code emitted by ``codegen`` calls the
same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.data import load_parquet
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class LoadParquet(NodeDefinition):
    """Load a Parquet file into a pandas DataFrame."""

    type = "data.load_parquet"
    version = 1
    family = "data"
    label = "Load Parquet"
    category = "Ingest"
    description = "Load a Parquet file into a pandas DataFrame."

    ports = [
        PortSpec(
            name="frame",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The loaded data as a pandas DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="path",
            type_token="str",
            required=True,
            label="Parquet path",
            help="Filesystem path to the .parquet file to load.",
            hints=ValidationHints(widget="file"),
        ),
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Optional subset of columns to read; leave unset to read all columns.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, list[str] | None]:
        values = {p.name: p.value for p in node.params}
        return cast(str, values.get("path")), cast("list[str] | None", values.get("columns"))

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        path, columns = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=f"{ctx.out_var('frame')} = ef.data.load_parquet({path!r}, columns={columns!r})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        path, columns = self._args(node)
        return {"frame": load_parquet(path, columns=columns)}
