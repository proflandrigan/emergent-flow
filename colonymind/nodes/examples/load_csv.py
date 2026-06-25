"""
colonymind.nodes.examples.load_csv
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.load_csv`` — a *source* node (0 inputs, 1 output).

Real, pandas-backed loader (Epic 1, Story 8). ``execute`` calls
``colonymind.data.load_csv`` directly and the code emitted by ``codegen``
calls the same wrapper via the ``cm.`` alias, so the two paths are equivalent
by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from colonymind.data import load_csv
from colonymind.ir.common import Direction
from colonymind.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from colonymind.codegen.context import CodegenContext


@register
class LoadCsv(NodeDefinition):
    """Load a CSV file into a pandas DataFrame."""

    type = "data.load_csv"
    version = 2
    family = "data"
    label = "Load CSV"
    category = "Ingest"
    description = "Load a CSV file into a pandas DataFrame."

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
            label="CSV path",
            help="Filesystem path to the .csv file to load.",
            hints=ValidationHints(widget="file"),
        ),
        ParamSpec(
            name="encoding",
            type_token="str",
            default="utf-8",
            label="Encoding",
            help="Text encoding used to read the file.",
            hints=ValidationHints(widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str]:
        values = {p.name: p.value for p in node.params}
        path = values.get("path")
        encoding = values.get("encoding", "utf-8")
        if encoding is None:
            encoding = "utf-8"
        return cast(str, path), cast(str, encoding)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        path, encoding = self._args(node)
        return CodeFragment(
            imports=["import colonymind as cm"],
            body=f"{ctx.out_var('frame')} = cm.data.load_csv({path!r}, encoding={encoding!r})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        path, encoding = self._args(node)
        return {"frame": load_csv(path, encoding=encoding)}
