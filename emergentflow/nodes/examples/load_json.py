"""
emergentflow.nodes.examples.load_json
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.load_json`` — a *source* node (0 inputs, 1 output).

Real, pandas-backed loader (Epic 6, Story 3). ``execute`` calls
``emergentflow.data.load_json`` directly and the code emitted by ``codegen`` calls the
same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.data import load_json
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class LoadJson(NodeDefinition):
    """Load a JSON file into a pandas DataFrame."""

    type = "data.load_json"
    version = 2
    family = "data"
    label = "Load JSON"
    category = "Ingest"
    description = "Load a JSON or JSON Lines (.jsonl) file into a pandas DataFrame."
    # execute() re-reads the file at `path` on every call; the file's content can
    # change without the `path` param changing, so this is not a pure function of
    # its declared params (see NodeDefinition.cacheable's docstring).
    cacheable = False

    ports = [
        PortSpec(
            name="frame",
            label="Data",
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
        ParamSpec(
            name="lines",
            type_token="bool",
            default=False,
            label="JSON Lines",
            help="Read the file as JSON Lines / newline-delimited JSON (.jsonl): one JSON "
            "object per line.",
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str | None, bool]:
        values = {p.name: p.value for p in node.params}
        return (
            cast(str, values.get("path")),
            cast("str | None", values.get("orient")),
            cast(bool, values.get("lines", False)),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        path, orient, lines = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=f"{ctx.out_var('frame')} = ef.data.load_json("
            f"{path!r}, orient={orient!r}, lines={lines!r})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        path, orient, lines = self._args(node)
        return {"frame": load_json(path, orient=orient, lines=lines)}
