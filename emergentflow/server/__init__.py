"""Thin local server for the bundled Emergent Flow app (ADR 0013, §A6).

The bundled package's Phase-2 "Living Bridge": a thin local server that calls the
SDK's ``ef.*`` entry points **in-process**. Importing this subpackage is opt-in --
a bare ``import emergentflow`` does not pull it in, so the SDK stays headless and
light per ADR 0007's portability guarantee.
"""

from __future__ import annotations

from emergentflow.server.app import app, create_app, serve
from emergentflow.server.service import (
    compile_graph,
    execute_graph,
    execute_node,
    export_eval_set_bytes,
    export_finetune_bytes,
    get_catalog,
    get_schema,
    label_eval,
    lineage_for_node,
    validate_graph,
)

__all__ = [
    "app",
    "create_app",
    "serve",
    "compile_graph",
    "execute_graph",
    "execute_node",
    "export_eval_set_bytes",
    "export_finetune_bytes",
    "get_catalog",
    "get_schema",
    "label_eval",
    "lineage_for_node",
    "validate_graph",
]
