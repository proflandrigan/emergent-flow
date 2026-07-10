"""
emergentflow.collab.knowledge
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14 Story 10: a minimal agent "knowledge base" — workspace-level, slug-keyed
KnowledgeEntries persisted as a single JSON file per ADR 0004 (small scalar/JSON
metadata belongs in a lightweight local store, never the artifact store).

Each KnowledgeEntry pairs a slug+description with a small subgraph and its computed
dangling-port signature (unbound IN types + produced OUT types), so an agent can
discover fragments by required inputs or guaranteed outputs without loading every
entry's graph.

Deliberately minimal: no embeddings, no dedup/GC, no versioning — those are
recorded as deferred in the epic and not implemented here.

Never imported by emergentflow/__init__.py, emergentflow/ir/__init__.py, or anything
under emergentflow/codegen/ — knowledge is an additive, opt-in layer that requires
agents to be useful (works-without-agents invariant).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from emergentflow.codegen.inference import infer_graph_types
from emergentflow.ir import Direction
from emergentflow.ir.graph import Graph
from emergentflow.nodes import registry as default_node_registry


class KnowledgeEntry(BaseModel):
    """A named, slug-keyed knowledge fragment: a subgraph with its computed
    dangling-port signature.

    Attributes:
        slug: Unique key for this entry.
        description: Human-readable summary of what the fragment does.
        subgraph: The graph fragment being stored.
        tags: Optional classification tags for filtering.
        created_by: Persona slug or ``"human"``.
        metrics: Optional numeric metrics (e.g. accuracy, latency).
        unbound_in_types: Sorted, deduplicated type tokens of every unbound IN
            port in the subgraph (computed, never caller-supplied).
        produced_out_types: Sorted, deduplicated type tokens of every dangling
            (unconsumed) OUT port in the subgraph (computed, never caller-supplied).
    """

    model_config = ConfigDict(extra="forbid")

    slug: str
    description: str
    subgraph: Graph
    tags: list[str] = Field(default_factory=list)
    created_by: str
    metrics: dict[str, float] = Field(default_factory=dict)
    unbound_in_types: list[str] = Field(default_factory=list)
    produced_out_types: list[str] = Field(default_factory=list)


class KnowledgeError(Exception):
    """Base class for all knowledge-store errors."""


class UnknownKnowledgeEntryError(KnowledgeError):
    """Raised when a slug lookup does not match any entry in the store."""


class DuplicateSlugError(KnowledgeError):
    """Raised when ``save()`` is called with a slug that already exists in the store."""


def compute_signature(
    subgraph: Graph,
    *,
    node_registry=default_node_registry,
) -> tuple[list[str], list[str]]:
    """Return the sorted, deduplicated (unbound_in_types, produced_out_types)
    signature of *subgraph*.

    Uses ``infer_graph_types`` to resolve OUT-port types and detect unbound IN
    ports. The unbound types are the declared ``data_type`` of each unbound IN
    port. The produced types are the resolved (or declared) type of every OUT
    port that is NOT consumed as an edge source within the subgraph.
    """
    result = infer_graph_types(subgraph, node_registry=node_registry)

    # Unbound IN-port types: each unbound port's declared data_type.
    unbound_types: list[str] = []
    for u in result.unbound:
        node = subgraph.nodes[u.node_id]
        port = next(p for p in node.ports if p.id == u.port_id)
        unbound_types.append(port.data_type)

    # Produced (dangling) OUT-port types: OUT ports that are never used as an
    # edge source within the subgraph.
    source_ports: set[tuple[str, str]] = set()
    for edge in subgraph.edges.values():
        source_ports.add((edge.source.node_id, edge.source.port_id))

    produced_types: list[str] = []
    for node in subgraph.nodes.values():
        for port in node.ports:
            if port.direction == Direction.OUT and (node.id, port.id) not in source_ports:
                token = result.type_of(node.id, port.id)
                if token is None:
                    token = port.data_type
                produced_types.append(token)

    return sorted(set(unbound_types)), sorted(set(produced_types))


class KnowledgeStore:
    """A slug-keyed, JSON-file-backed store of KnowledgeEntries (ADR 0004).

    One JSON object per file, keyed by slug, written atomically (temp file +
    os.replace). Deliberately single-file for simplicity: a workspace's worth
    of knowledge fragments fits comfortably in a few KB of JSON.
    """

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = Path.cwd() / ".emergentflow" / "knowledge.json"
        self._path = path
        self._lock = threading.Lock()
        self._entries: dict[str, KnowledgeEntry] = {}
        if self._path.is_file():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for slug, entry_data in data.items():
                self._entries[slug] = KnowledgeEntry.model_validate(entry_data)

    def save(self, entry: KnowledgeEntry) -> KnowledgeEntry:
        """Store *entry* under its slug, computing the port signature from the
        subgraph rather than trusting the caller's values.

        Raises
        ------
        DuplicateSlugError
            If ``entry.slug`` already exists in the store.
        """
        with self._lock:
            if entry.slug in self._entries:
                raise DuplicateSlugError(
                    f"a knowledge entry with slug {entry.slug!r} already exists"
                )
            unbound, produced = compute_signature(entry.subgraph)
            stored_entry = entry.model_copy(
                update={
                    "unbound_in_types": unbound,
                    "produced_out_types": produced,
                }
            )
            self._entries[stored_entry.slug] = stored_entry
            self._persist()
            return stored_entry

    def get(self, slug: str) -> KnowledgeEntry:
        """Return the entry for *slug*.

        Raises
        ------
        UnknownKnowledgeEntryError
            If no entry with that slug exists.
        """
        with self._lock:
            entry = self._entries.get(slug)
            if entry is None:
                raise UnknownKnowledgeEntryError(f"no knowledge entry with slug {slug!r}")
            return entry

    def list(
        self,
        *,
        in_type: str | None = None,
        out_type: str | None = None,
        tag: str | None = None,
    ) -> list[KnowledgeEntry]:
        """Return entries matching the given filters (all given filters AND
        together), sorted by slug.

        Parameters
        ----------
        in_type:
            If given, only entries where this type appears in
            ``unbound_in_types``.
        out_type:
            If given, only entries where this type appears in
            ``produced_out_types``.
        tag:
            If given, only entries where this tag appears in ``tags``.
        """
        with self._lock:
            result = list(self._entries.values())
            if in_type is not None:
                result = [e for e in result if in_type in e.unbound_in_types]
            if out_type is not None:
                result = [e for e in result if out_type in e.produced_out_types]
            if tag is not None:
                result = [e for e in result if tag in e.tags]
            return sorted(result, key=lambda e: e.slug)

    def _persist(self) -> None:
        """Atomically write all entries to the JSON file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {slug: entry.model_dump(mode="json") for slug, entry in self._entries.items()}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)


_default_store: KnowledgeStore | None = None
_default_store_lock = threading.Lock()


def get_default_store() -> KnowledgeStore:
    """Return the lazily-created process-wide default :class:`KnowledgeStore`.

    Double-checked locking: the store is created once and shared across all
    callers (the same pattern as ``SessionStore`` and ``ReportStore``).
    """
    global _default_store
    if _default_store is None:
        with _default_store_lock:
            if _default_store is None:
                _default_store = KnowledgeStore()
    return _default_store
