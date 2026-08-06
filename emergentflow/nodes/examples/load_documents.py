"""
emergentflow.nodes.examples.load_documents
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node: ``data.load_documents`` — a *source* node (0 inputs, 1 output).

Real, pypdf-backed (for PDF) document-chunking loader (Epic 16, Story 20). ``execute`` calls
``emergentflow.data.load_documents`` directly and the code emitted by ``codegen`` calls the
same wrapper via the ``ef.`` alias, so the two paths are equivalent by construction (ADR 0002).

No embedding or retrieval happens here -- see ``emergentflow.data.documents`` for that
boundary note; this node only produces a DocumentFrame for a downstream Epic 11 retrieval
surface to consume.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from emergentflow.data import load_documents
from emergentflow.ir.common import Direction
from emergentflow.ir.node import Node

from ..contract import CodeFragment, NodeDefinition
from ..registry import register
from ..spec import ColumnEffect, ColumnEffectKind, ParamSpec, PortSpec, ValidationHints

if TYPE_CHECKING:
    from emergentflow.codegen.context import CodegenContext


@register
class LoadDocuments(NodeDefinition):
    """Chunk PDF/text/markdown file(s) into a tidy DocumentFrame."""

    type = "data.load_documents"
    version = 1
    family = "data"
    label = "Load Documents"
    category = "Ingest"
    description = (
        "Chunk PDF/text/markdown file(s) into a tidy (doc_id, chunk_id, text, ...) frame. "
        "No embedding or retrieval -- that's Epic 11; this only produces the frame."
    )
    column_effect = ColumnEffect(kind=ColumnEffectKind.SOURCE)
    advisor_persona = "data_modeller"
    # execute() re-reads files from disk on every call; not a pure function of its declared
    # params alone (mirrors LoadExcel's cacheable=False for the same reason).
    cacheable = False

    ports = [
        PortSpec(
            name="frame",
            label="Documents",
            direction=Direction.OUT,
            data_type="DocumentFrame",
            help=(
                "One row per chunk: doc_id, chunk_id, chunk_index, text, source_path, char_count."
            ),
        ),
    ]
    params = [
        ParamSpec(
            name="path",
            type_token="str",
            required=True,
            label="Path",
            help="A single .pdf/.txt/.md/.markdown file, or a directory containing them "
            "(processed in sorted filename order).",
            hints=ValidationHints(widget="file"),
        ),
        ParamSpec(
            name="chunk_size",
            type_token="int",
            default=1000,
            label="Chunk size",
            help="Maximum characters per chunk.",
            hints=ValidationHints(widget="number", min=1),
        ),
        ParamSpec(
            name="chunk_overlap",
            type_token="int",
            default=100,
            label="Chunk overlap",
            help="Characters of overlap between consecutive chunks; must be less than the "
            "chunk size.",
            hints=ValidationHints(widget="number", min=0),
        ),
    ]

    def _args(self, node: Node) -> tuple[str, int, int]:
        values = {p.name: p.value for p in node.params}
        path = values.get("path")
        chunk_size = values.get("chunk_size", 1000)
        if chunk_size is None:
            chunk_size = 1000
        chunk_overlap = values.get("chunk_overlap", 100)
        if chunk_overlap is None:
            chunk_overlap = 100
        return cast(str, path), cast(int, chunk_size), cast(int, chunk_overlap)

    def codegen(self, node: Node, ctx: CodegenContext) -> CodeFragment:
        path, chunk_size, chunk_overlap = self._args(node)
        return CodeFragment(
            imports=["import emergentflow as ef"],
            body=(
                f"{ctx.out_var('frame')} = ef.data.load_documents("
                f"{path!r}, chunk_size={chunk_size!r}, chunk_overlap={chunk_overlap!r})"
            ),
        )

    def execute(self, node: Node, inputs: dict[str, Any]) -> dict[str, Any]:
        path, chunk_size, chunk_overlap = self._args(node)
        return {"frame": load_documents(path, chunk_size=chunk_size, chunk_overlap=chunk_overlap)}
