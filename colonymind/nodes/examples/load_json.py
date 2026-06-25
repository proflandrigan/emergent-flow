"""
colonymind.nodes.examples.load_json
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.load_json`` — a *source* node (0 inputs, 1 output).

Real, pandas-backed loader (Epic 6, Story 3). ``execute`` calls
``colonymind.data.load_json`` directly and the code emitted by ``codegen`` calls the
same wrapper via the ``cm.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from colonymind.data import load_json
from colonymind.ir.common import Direction
from colonymind.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from colonymind.codegen.context import CodegenContext


@register
class LoadJson(NodeDefinition):
    """Load a JSON file into a pandas DataFrame."""

    type = "data.load_json"
    version = 1
    family = "data"
    label = "Load JSON"
    category = "Ingest"
    description = "Load a JSON file into a pandas DataFrame."

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
            label="JSON path",
            help="Filesystem path to the .json file to load.",
            hints=ValidationHints(widget="file"),
        ),
        ParamSpec(
            name="orient",
            type_token="str",
            default=None,
            label="Orient",
            help="pandas read_json orient (e.g. 'records'); unset uses pandas' default.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str | None]:
        values = {p.name: p.value for p in node.params}
        return cast(str, values.get("path")), cast("str | None", values.get("orient"))

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        path, orient = self._args(node)
        return CodeFragment(
            imports=["import colonymind as cm"],
            body=f"{ctx.out_var('frame')} = cm.data.load_json({path!r}, orient={orient!r})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        path, orient = self._args(node)
        return {"frame": load_json(path, orient=orient)}
