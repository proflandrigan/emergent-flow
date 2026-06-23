"""Thin local server for the bundled Colony Mind app (ADR 0013, §A6).

The bundled package's Phase-2 "Living Bridge": a thin local server that calls the
SDK's ``cm.*`` entry points **in-process**. Importing this subpackage is opt-in --
a bare ``import colonymind`` does not pull it in, so the SDK stays headless and
light per ADR 0007's portability guarantee.
"""

from __future__ import annotations

from colonymind.server.app import make_server, serve
from colonymind.server.service import compile_graph, execute_graph, validate_graph

__all__ = [
    "make_server",
    "serve",
    "compile_graph",
    "execute_graph",
    "validate_graph",
]
