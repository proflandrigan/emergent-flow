"""
colonymind.ir.serialize
~~~~~~~~~~~~~~~~~~~~~~~~
Public serialization API for the Colony Mind graph IR.

This is the first-class, documented surface for turning a :class:`~colonymind.ir.graph.Graph`
into portable JSON and back. It is a thin, deterministic wrapper over Pydantic's
``model_dump_json`` / ``model_validate_json`` that adds three things the raw methods do not:

1. **Schema-version policy on load** — a serialized graph carries ``schema_version``; this
   module enforces it (see :func:`_reject_if_newer`). Older versions are migrated up to
   ``CURRENT_SCHEMA_VERSION`` via the Story 9 migration framework (``colonymind.ir.migrate``)
   before validation; only versions newer than this build are rejected.
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

from .graph import CURRENT_SCHEMA_VERSION, INITIAL_SCHEMA_VERSION, Graph
from .migrate import MigrationError, migrate_document

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


def _reject_if_newer(found: int) -> None:
    """Reject graphs written by a newer build. Older graphs are NOT rejected here — they
    are migrated up by `migrate_document` (the Story 9 framework). Equal/older versions pass."""
    if found > CURRENT_SCHEMA_VERSION:
        raise SchemaVersionError(
            f"graph schema v{found} was written by a newer version of Colony Mind; "
            f"this build supports schema v{CURRENT_SCHEMA_VERSION}. Upgrade to load it.",
            found=found,
            expected=CURRENT_SCHEMA_VERSION,
        )


def _coerce_version(graph_dict: dict) -> int:
    """Read and validate a graph dict's schema_version (absent defaults to
    INITIAL_SCHEMA_VERSION — a pre-versioning graph — matching migrate._migrate_graph_level
    so the two cannot drift). Raises GraphDeserializationError if it is not an int."""
    found = graph_dict.get("schema_version", INITIAL_SCHEMA_VERSION)
    if not isinstance(found, int) or isinstance(found, bool):
        raise GraphDeserializationError(f"schema_version must be an integer, got {found!r}.")
    return found


def _iter_subgraph_dicts(graph_dict: dict) -> Iterator[dict]:
    """Yield every nested subgraph dict reachable from `graph_dict` (depth-first, excluding
    the root). Each is a serialized graph with its own schema_version."""
    nodes = graph_dict.get("nodes")
    if isinstance(nodes, dict):
        for node in nodes.values():
            if isinstance(node, dict):
                sub = node.get("subgraph")
                if isinstance(sub, dict):
                    yield sub
                    yield from _iter_subgraph_dicts(sub)


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

    Performs, in order: JSON parse → schema-version check (reject newer-than-current) →
    migrate any older graph (top-level and nested subgraphs) up to
    ``CURRENT_SCHEMA_VERSION`` → full model + structural validation (via
    ``Graph._validate_structure``). Any failure is raised as a
    :class:`GraphDeserializationError` (or its :class:`SchemaVersionError` subclass),
    with the underlying cause chained.

    Parameters
    ----------
    data:
        JSON text or bytes produced by :func:`serialize_graph` (or any conforming client).

    Returns
    -------
    Graph
        A fully validated graph at ``CURRENT_SCHEMA_VERSION``.

    Raises
    ------
    SchemaVersionError
        If the embedded ``schema_version`` is newer than this build supports, or if
        migration to the current schema version fails.
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

    # 2. Version policy: reject ONLY newer-than-current versions (top-level + nested), and
    #    validate that every embedded schema_version is an integer.
    top_found = _coerce_version(parsed)
    _reject_if_newer(top_found)
    for sub in _iter_subgraph_dicts(parsed):
        _reject_if_newer(_coerce_version(sub))

    # 3. Migrate older graphs (top-level AND nested) up to CURRENT before validation.
    try:
        migrated = migrate_document(parsed)
    except MigrationError as e:
        raise SchemaVersionError(
            f"graph schema v{top_found} could not be migrated to v{CURRENT_SCHEMA_VERSION}: {e}",
            found=top_found,
            expected=CURRENT_SCHEMA_VERSION,
        ) from e

    # 4. Full model + structural validation on the MIGRATED dict. Reuse Pydantic +
    #    Graph._validate_structure; do not duplicate structural checks here.
    try:
        graph = Graph.model_validate(migrated)
    except ValidationError as e:
        raise GraphDeserializationError(f"graph failed validation: {e}") from e

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
