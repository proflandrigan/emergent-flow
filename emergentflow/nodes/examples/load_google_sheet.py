"""
emergentflow.nodes.examples.load_google_sheet
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.load_google_sheet`` — a *source* node (0 inputs, 1 output).

Both ``execute`` and ``codegen`` route through the same
``ef.data.load_google_sheet`` wrapper, so the two paths are equivalent by
construction (ADR 0002). This node sets
``requires = frozenset({ClientKind.HTTP})``: the injected ``HttpClient`` is
threaded in by the executor / the compiled module's ``main()``, never constructed
here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from emergentflow.clients import ClientKind
from emergentflow.data import load_google_sheet
from emergentflow.data.http.protocol import HttpClient
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class LoadGoogleSheet(NodeDefinition):
    """Load a Google Sheets tab into a pandas DataFrame over the HTTP client seam."""

    type = "data.load_google_sheet"
    version = 2
    family = "data"
    label = "Load Google Sheet"
    category = "Ingest"
    description = "Load a Google Sheets tab into a pandas DataFrame over the HTTP client seam."
    column_effect = ColumnEffect(kind=ColumnEffectKind.SOURCE)
    requires = frozenset({ClientKind.HTTP})
    advisor_persona = "data_modeller"
    cacheable = False

    ports = [
        PortSpec(
            name="frame",
            label="Data",
            direction=Direction.OUT,
            data_type="DataFrame",
            help="The loaded sheet data as a pandas DataFrame.",
        ),
    ]
    params = [
        ParamSpec(
            name="spreadsheet_id",
            type_token="str",
            required=True,
            label="Spreadsheet ID",
            help="The id from the sheet's URL.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="sheet",
            type_token="str",
            default=None,
            label="Sheet name",
            help="Tab name within the spreadsheet (omit for the first/default tab).",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="header_row",
            type_token="int",
            default=0,
            label="Header row",
            help="Zero-based row index to use as column header.",
            hints=ValidationHints(min=0, widget="number"),
        ),
        ParamSpec(
            name="connection",
            type_token="str",
            default=None,
            label="Connection",
            help="A connection-profile name (never a credential). Resolved to live "
            "credentials by the HttpClient at fetch time.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="timeout_s",
            type_token="float",
            default=None,
            label="Timeout (s)",
            help="Request timeout in seconds.",
            hints=ValidationHints(widget="number"),
        ),
        ParamSpec(
            name="expect_columns",
            type_token="list[str]",
            default=None,
            label="Expected columns",
            help="Optional list of column names that must be present after loading. A "
            "missing column fails the load with a typed SchemaContractError naming every "
            "mismatch at once, rather than surfacing as a KeyError further downstream.",
            hints=ValidationHints(widget="json"),
        ),
        ParamSpec(
            name="expect_dtypes",
            type_token="dict",
            default=None,
            label="Expected dtypes",
            help="Optional map of column name to expected pandas dtype string (e.g. "
            "{'id': 'int64', 'name': 'object'}). Checked after loading; a mismatch fails "
            "the load with a typed SchemaContractError.",
            hints=ValidationHints(widget="json"),
        ),
    ]

    def _args(self, node: Node) -> dict[str, Any]:
        values = {p.name: p.value for p in node.params}
        header_row = values.get("header_row")
        if header_row is None:
            header_row = 0
        return {
            "spreadsheet_id": values.get("spreadsheet_id") or "",
            "sheet": values.get("sheet"),
            "header_row": header_row,
            "connection": values.get("connection"),
            "timeout_s": values.get("timeout_s"),
            "expect_columns": values.get("expect_columns"),
            "expect_dtypes": values.get("expect_dtypes"),
        }

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        args = self._args(node)
        lines = [
            f"{ctx.out_var('frame')} = ef.data.load_google_sheet(",
            f"    spreadsheet_id={args['spreadsheet_id']!r},",
            "    client=http,",
            f"    sheet={args['sheet']!r},",
            f"    header_row={args['header_row']!r},",
            f"    connection={args['connection']!r},",
            f"    timeout_s={args['timeout_s']!r},",
            f"    expect_columns={args['expect_columns']!r},",
            f"    expect_dtypes={args['expect_dtypes']!r},",
            ")",
        ]
        return CodeFragment(imports=["import emergentflow as ef"], body="\n".join(lines))

    def execute(
        self, node: Node, inputs: dict[str, Any], *, client: HttpClient | None = None
    ) -> dict[str, Any]:
        args = self._args(node)
        return {"frame": load_google_sheet(client=client, **args)}
