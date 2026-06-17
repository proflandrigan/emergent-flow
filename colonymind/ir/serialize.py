"""
colonymind.ir.serialize
~~~~~~~~~~~~~~~~~~~~~~~~
Public serialization API for the Colony Mind graph IR.

This is the first-class, documented surface for turning a :class:`~colonymind.ir.graph.Graph`
into portable JSON and back. It is a thin, deterministic wrapper over Pydantic's
``model_dump_json`` / ``model_validate_json`` that adds three things the raw methods do not:

1. **Schema-version policy on load** — a serialized graph carries ``schema_version``; this
   module enforces it (see :func:`_check_schema_version`). Older versions raise a clear
   "migration required" error: the deliberate seam Story 9 (migration framework) plugs into.
2. **Clean, domain-specific errors** — Pydantic's ``ValidationError`` and ``json`` decode
   errors are re-raised as :class:`GraphDeserializationError` so callers see one error type.
3. **File I/O helpers** — :func:`save_graph` / :func:`load_graph` using the ``.cm.json``
   convention from ``docs/ir-serialization-format.md``.

Structural validation (edges referencing real nodes/ports, port directions, group ids) is
*not* re-implemented here: it lives in ``Graph._validate_structure`` and runs automatically
during ``model_validate_json``. This module simply surfaces those failures as clean errors.

ADR refs:
  - ADR 0002: execute the IR (data), not a generated string — the graph is the artifact.
  - docs/ir-serialization-format.md: JSON-first, ``.cm.json`` at-rest extension.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError

from .graph import CURRENT_SCHEMA_VERSION, Graph

__all__ = [
    "serialize_graph",
    "deserialize_graph",
    "save_graph",
    "load_graph",
    "GraphSerializationError",
    "GraphDeserializationError",
    "SchemaVersionError",
]

# Persisted-file extension convention (docs/ir-serialization-format.md).
GRAPH_FILE_SUFFIX = ".cm.json"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GraphSerializationError(Exception):
    """Base class for all serialization/deserialization failures in this module."""


class GraphDeserializationError(GraphSerializationError):
    """Raised when input cannot be parsed/validated into a :class:`Graph`.

    Covers malformed JSON and structurally invalid graphs (the underlying
    ``json.JSONDecodeError`` / Pydantic ``ValidationError`` is chained via ``from``).
    """


class SchemaVersionError(GraphDeserializationError):
    """Raised when a serialized graph's ``schema_version`` is not loadable by this build.

    Attributes
    ----------
    found:
        The ``schema_version`` embedded in the input.
    expected:
        The schema version this build supports (``CURRENT_SCHEMA_VERSION``).
    """

    def __init__(self, message: str, *, found: int, expected: int) -> None:
        super().__init__(message)
        self.found = found
        self.expected = expected


# ---------------------------------------------------------------------------
# Version policy (the Story 9 migration seam)
# ---------------------------------------------------------------------------


def _check_schema_version(found: int) -> None:
    """Enforce the load-time schema-version policy.

    - ``found == CURRENT`` → ok.
    - ``found > CURRENT``  → written by a newer build; reject.
    - ``found < CURRENT``  → predates this build; reject as "migration required".

    The "older version" branch is the explicit hook for Story 9: once a migration
    framework exists, older graphs should be routed through it here instead of rejected.
    """
    if found == CURRENT_SCHEMA_VERSION:
        return
    if found > CURRENT_SCHEMA_VERSION:
        raise SchemaVersionError(
            f"graph schema v{found} was written by a newer version of Colony Mind; "
            f"this build supports schema v{CURRENT_SCHEMA_VERSION}. Upgrade to load it.",
            found=found,
            expected=CURRENT_SCHEMA_VERSION,
        )
    # found < CURRENT_SCHEMA_VERSION
    # TODO(Story 9): route through the migration framework instead of rejecting.
    raise SchemaVersionError(
        f"graph schema v{found} predates this build (v{CURRENT_SCHEMA_VERSION}); "
        "a migration is required to load it.",
        found=found,
        expected=CURRENT_SCHEMA_VERSION,
    )


def _iter_subgraphs(graph: Graph) -> Iterator[Graph]:
    """Yield every nested subgraph reachable from *graph* (depth-first, excluding the root).

    A composite node's ``subgraph`` is itself a serialized :class:`Graph` carrying its own
    ``schema_version``, so the version policy must reach it too — otherwise a nested graph
    written by a newer/older build would load silently. See :func:`deserialize_graph`.
    """
    for node in graph.nodes.values():
        if node.subgraph is not None:
            yield node.subgraph
            yield from _iter_subgraphs(node.subgraph)


# ---------------------------------------------------------------------------
# Serialize
# ---------------------------------------------------------------------------


def serialize_graph(graph: Graph, *, indent: int | None = 2) -> str:
    """Serialize *graph* to portable JSON text.

    The embedded ``schema_version`` (a field on :class:`Graph`) travels with the output,
    so the result is self-describing and loadable by :func:`deserialize_graph`.

    Parameters
    ----------
    graph:
        The IR graph to serialize.
    indent:
        JSON indentation. Defaults to ``2`` for git-diffable, human-readable output;
        pass ``None`` for a compact single-line wire payload.

    Returns
    -------
    str
        UTF-8-encodable JSON text.
    """
    return graph.model_dump_json(indent=indent)


# ---------------------------------------------------------------------------
# Deserialize
# ---------------------------------------------------------------------------


def deserialize_graph(data: str | bytes) -> Graph:
    """Parse and validate JSON *data* into a :class:`Graph`.

    Performs, in order: JSON parse → schema-version check → full model + structural
    validation (via ``Graph._validate_structure``). Any failure is raised as a
    :class:`GraphDeserializationError` (or its :class:`SchemaVersionError` subclass),
    with the underlying cause chained.

    Parameters
    ----------
    data:
        JSON text or bytes produced by :func:`serialize_graph` (or any conforming client).

    Returns
    -------
    Graph
        A fully validated graph.

    Raises
    ------
    SchemaVersionError
        If the embedded ``schema_version`` is not loadable by this build.
    GraphDeserializationError
        If the input is not valid JSON or is not a structurally valid graph.
    """
    # 1. Parse JSON up front so we can read the version before full validation, and so
    #    malformed JSON surfaces as our error type rather than Pydantic's.
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise GraphDeserializationError(f"input is not valid JSON: {e}") from e

    if not isinstance(parsed, dict):
        raise GraphDeserializationError(
            f"a serialized graph must be a JSON object, got {type(parsed).__name__}."
        )

    # 2. Version policy. Absent version is treated as the original schema (v1); the
    #    check then accepts/rejects it under the normal policy.
    found = parsed.get("schema_version", 1)
    if not isinstance(found, int) or isinstance(found, bool):
        raise GraphDeserializationError(f"schema_version must be an integer, got {found!r}.")
    _check_schema_version(found)

    # 3. Full model + structural validation. Reuse Pydantic + Graph._validate_structure;
    #    do not duplicate structural checks here.
    try:
        graph = Graph.model_validate(parsed)
    except ValidationError as e:
        raise GraphDeserializationError(f"graph failed validation: {e}") from e

    # 4. Apply the version policy to nested subgraphs too — each is a serialized graph
    #    with its own schema_version (the top-level version was already checked above).
    for subgraph in _iter_subgraphs(graph):
        _check_schema_version(subgraph.schema_version)

    return graph


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def save_graph(graph: Graph, path: str | os.PathLike[str], *, indent: int | None = 2) -> Path:
    """Serialize *graph* and write it to *path* as UTF-8 (with a trailing newline).

    The ``.cm.json`` extension is the persisted-file convention but is not enforced.

    Returns
    -------
    Path
        The path written.
    """
    p = Path(path)
    text = serialize_graph(graph, indent=indent)
    p.write_text(text + "\n", encoding="utf-8")
    return p


def load_graph(path: str | os.PathLike[str]) -> Graph:
    """Read a serialized graph from *path* and deserialize it.

    Raises
    ------
    GraphDeserializationError
        If the file is missing/unreadable or its contents are not a valid graph.
    SchemaVersionError
        If the embedded ``schema_version`` is not loadable by this build.
    """
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as e:
        raise GraphDeserializationError(f"could not read graph file {p}: {e}") from e
    return deserialize_graph(raw)
