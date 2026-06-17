"""
colonymind.nodes.examples.load_csv
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.load_csv`` — a *source* node (0 inputs, 1 output).

Exercises the simplest shape of the contract: no IN ports, a required param with
a ``file`` widget hint, and an optional param with a default.  A table is
represented as a plain ``list[dict[str, str]]`` (one dict per row) so the node
carries no third-party dependency — the real pandas-backed loader is Story 8.
"""

from __future__ import annotations

import csv
from typing import Any, cast

from colonymind.ir.common import Direction
from colonymind.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints


def read_csv_rows(path: str, delimiter: str = ",") -> list[dict[str, str]]:
    """Read *path* into a list of row dicts (the shared runtime helper).

    Both ``LoadCsv.execute`` and the code emitted by ``LoadCsv.codegen`` call
    this, so the two paths are equivalent by construction (ADR 0002).
    """
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=delimiter))


@register
class LoadCsv(NodeDefinition):
    """Load a CSV file into a table (list of row dicts)."""

    type = "data.load_csv"
    version = 1
    family = "data"
    label = "Load CSV"

    ports = [
        PortSpec(
            name="table",
            direction=Direction.OUT,
            data_type="Table",
            help="The loaded rows, one dict per record.",
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
            name="delimiter",
            type_token="str",
            default=",",
            label="Delimiter",
            help="Single-character field separator.",
            hints=ValidationHints(min_length=1, max_length=1, widget="text"),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, str]:
        values = {p.name: p.value for p in node.params}
        path = values.get("path")
        delimiter = values.get("delimiter", ",")
        if delimiter is None:
            delimiter = ","
        return cast(str, path), cast(str, delimiter)

    def codegen(self, node: Node) -> CodeFragment:
        path, delimiter = self._args(node)
        return CodeFragment(
            imports=["from colonymind.nodes.examples.load_csv import read_csv_rows"],
            body=f"table = read_csv_rows({path!r}, delimiter={delimiter!r})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        path, delimiter = self._args(node)
        return {"table": read_csv_rows(path, delimiter=delimiter)}
