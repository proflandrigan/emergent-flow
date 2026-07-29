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
    version = 4
    family = "data"
    label = "Load Parquet"
    category = "Ingest"
    description = "Load a Parquet file into a pandas DataFrame."
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
            label="Parquet path",
            help="Filesystem path to the .parquet file to load. Accepts a glob pattern "
            "(e.g. `data/*.parquet`) to row-concatenate every match in sorted order, or "
            "an object-store URI (`s3://`, `gs://`, `az://`) which requires the "
            "`[cloud]` extra.",
            hints=ValidationHints(widget="file"),
        ),
        ParamSpec(
            name="columns",
            type_token="list[str]",
            default=None,
            label="Columns",
            help="Optional subset of columns to read; leave unset to read all columns.",
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
    ) -> tuple[str, list[str] | None, bool, str | None, list[str] | None, dict[str, str] | None]:
        values = {p.name: p.value for p in node.params}
        source_file = values.get("source_file", False)
        if source_file is None:
            source_file = False
        return (
            cast(str, values.get("path")),
            cast("list[str] | None", values.get("columns")),
            cast(bool, source_file),
            cast("str | None", values.get("connection")),
            cast("list[str] | None", values.get("expect_columns")),
            cast("dict[str, str] | None", values.get("expect_dtypes")),
        )

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        path, columns, source_file, connection, expect_columns, expect_dtypes = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=f"{ctx.out_var('frame')} = ef.data.load_parquet("
            f"{path!r}, columns={columns!r}, source_file={source_file!r}, "
            f"connection={connection!r}, expect_columns={expect_columns!r}, "
            f"expect_dtypes={expect_dtypes!r})",
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        path, columns, source_file, connection, expect_columns, expect_dtypes = self._args(node)
        return {
            "frame": load_parquet(
                path,
                columns=columns,
                source_file=source_file,
                connection=connection,
                expect_columns=expect_columns,
                expect_dtypes=expect_dtypes,
            )
        }
