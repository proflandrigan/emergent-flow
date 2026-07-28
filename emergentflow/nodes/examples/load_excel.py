"""
emergentflow.nodes.examples.load_excel
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.load_excel`` — a *source* node (0 inputs, 1 output).

Real, pandas-backed Excel loader (Epic 16, Story 3). ``execute`` calls
``emergentflow.data.load_excel`` directly and the code emitted by ``codegen``
calls the same wrapper via the ``ef.`` alias, so the two paths are equivalent
by construction (ADR 0002).

Requires the optional ``[excel]`` extra at run time (provides ``openpyxl``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.data import load_excel
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class LoadExcel(NodeDefinition):
    """Load a sheet from an Excel workbook into a pandas DataFrame."""

    type = "data.load_excel"
    version = 2
    family = "data"
    label = "Load Excel"
    category = "Ingest"
    description = "Load a sheet from an Excel workbook into a pandas DataFrame."
    # execute() re-reads the file at `path` on every call; the file's content can
    # change without the `path` param changing, so this is not a pure function of
    # its declared params (see NodeDefinition.cacheable's docstring).
    advisor_persona = "data_modeller"
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
            label="Excel path",
            help="Filesystem path to the .xlsx file to load. Accepts a glob pattern (e.g. "
            "`data/*.xlsx`) to row-concatenate every match in sorted order, or an "
            "object-store URI (`s3://`, `gs://`, `az://`) which requires the `[cloud]` "
            "extra.",
            hints=ValidationHints(widget="file"),
        ),
        ParamSpec(
            name="sheet",
            type_token="str",
            default="0",
            label="Sheet name or index",
            help="A sheet name, or a zero-based index like ``0``. A string of all digits "
            "is automatically converted to an integer index.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="header_row",
            type_token="int",
            default=0,
            label="Header row",
            help="Zero-based row index to use as the column header.",
            hints=ValidationHints(widget="number", min=0),
        ),
        ParamSpec(
            name="usecols",
            type_token="str",
            default=None,
            label="Columns to load",
            help='An Excel range string (e.g. ``"A:D"``) or a comma-separated list of '
            "column names. Passed through to pandas.read_excel.",
            hints=ValidationHints(widget="text"),
        ),
        ParamSpec(
            name="source_file",
            type_token="bool",
            default=False,
            label="Add source file column",
            help="Add a 'source_file' column naming the file each row came from. Useful "
            "when loading a glob pattern across many files.",
            hints=ValidationHints(widget="checkbox"),
        ),
        ParamSpec(
            name="connection",
            type_token="str",
            default=None,
            label="Connection profile",
            help="Name of a connection profile supplying object-store credentials for a "
            "remote URI. A profile NAME only -- never a credential, which is resolved from "
            "the profile's env-var names at load time. Ignored for local paths.",
            hints=ValidationHints(widget="text"),
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

    def _args(
        self, node: Node
    ) -> tuple[
        str, str | int, int, str | None, bool, str | None, list[str] | None, dict[str, str] | None
    ]:
        values = {p.name: p.value for p in node.params}
        path = values.get("path")
        sheet_raw = values.get("sheet", "0")
        if sheet_raw is None:
            sheet_raw = "0"
        # coerce all-digit strings to int so codegen and execute pass the same type
        sheet: str | int
        if isinstance(sheet_raw, str):
            sheet = sheet_raw.strip()
            if sheet.isdigit():
                sheet = int(sheet)
        else:
            sheet = cast("str | int", sheet_raw)
        header_row = values.get("header_row", 0)
        if header_row is None:
            header_row = 0
        usecols = values.get("usecols")
        source_file = values.get("source_file", False)
        if source_file is None:
            source_file = False
        connection = values.get("connection")
        return (
            cast(str, path),
            sheet,
            cast(int, header_row),
            cast("str | None", usecols),
            cast(bool, source_file),
            cast("str | None", connection),
            cast("list[str] | None", values.get("expect_columns")),
            cast("dict[str, str] | None", values.get("expect_dtypes")),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        path, sheet, header_row, usecols, source_file, connection, expect_columns, expect_dtypes = (
            self._args(node)
        )
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=f"{ctx.out_var('frame')} = ef.data.load_excel("
            f"{path!r}, sheet={sheet!r}, header_row={header_row!r}, "
            f"usecols={usecols!r}, source_file={source_file!r}, "
            f"connection={connection!r}, expect_columns={expect_columns!r}, "
            f"expect_dtypes={expect_dtypes!r})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        path, sheet, header_row, usecols, source_file, connection, expect_columns, expect_dtypes = (
            self._args(node)
        )
        return {
            "frame": load_excel(
                path,
                sheet=sheet,
                header_row=header_row,
                usecols=usecols,
                source_file=source_file,
                connection=connection,
                expect_columns=expect_columns,
                expect_dtypes=expect_dtypes,
            )
        }
