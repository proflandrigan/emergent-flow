"""
emergentflow.research.lineage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Data lineage / provenance (Epic 16, Story 17).

``trace_lineage`` is a pure function computed on demand from the existing graph IR — lineage is
never stored as a Graph/Node/Edge schema field (mirrors ADR 0019's "state lives beside the
graph, never on it" discipline: adding a field would force a schema-version bump and break
older deployments, and two structurally-identical graphs shouldn't serialize differently based
on non-structural metadata).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from emergentflow.api import public_op
from emergentflow.ir.common import IRId
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node
from emergentflow.research.errors import UnknownNodeError

if TYPE_CHECKING:
    from emergentflow.nodes.spec import ColumnEffect

__all__ = [
    "LineageNode",
    "LineageEdge",
    "Lineage",
    "trace_lineage",
    "ColumnRole",
    "ColumnLineageNode",
    "ColumnLineageEdge",
    "ColumnLineage",
    "trace_column_lineage",
    "trace_column_impact",
]


@dataclass
class LineageNode:
    """One node in a traced lineage chain."""

    node_id: str
    node_type: str
    label: str | None


@dataclass
class LineageEdge:
    """One edge in a traced lineage chain, between two nodes both present in
    :attr:`Lineage.nodes`."""

    source_node_id: str
    source_port: str
    target_node_id: str
    target_port: str


@dataclass
class Lineage:
    """The upstream source -> transform -> artifact chain behind a target node.

    Attributes
    ----------
    target_node_id: the node id lineage was traced for.
    nodes: the target node plus every ancestor reachable by walking edges backward
        (source <- target), deduplicated, in deterministic topological order (the same order
        ``ef.codegen.topological_sort`` would assign the whole graph, filtered to this subset).
        The target node is always last.
    edges: every edge in *graph* whose source and target are both in ``nodes`` — i.e. the
        induced subgraph's edges — in deterministic order (following ``nodes``' topological
        order by source then target, with the edge id as the tie-break for parallel edges),
        so a graph traces identically regardless of the order its edges were added in.
    """

    target_node_id: str
    nodes: list[LineageNode] = field(default_factory=list)
    edges: list[LineageEdge] = field(default_factory=list)


class ColumnRole(str, Enum):
    """How a column is produced or transformed by a node in a column lineage chain."""

    SOURCE = "source"
    PASSTHROUGH = "passthrough"
    RENAMED = "renamed"
    DERIVED = "derived"
    AGGREGATED = "aggregated"
    ENCODED = "encoded"
    DROPPED = "dropped"
    UNKNOWN = "unknown"


@dataclass
class ColumnLineageNode:
    """One node in a traced column lineage chain, for a single output column."""

    node_id: str
    node_type: str
    label: str | None
    column: str
    role: ColumnRole
    source_column: str | None = None
    detail: str | None = None


@dataclass
class ColumnLineageEdge:
    """One edge in a traced column lineage chain, between two nodes both present in
    :attr:`ColumnLineage.nodes`."""

    source_node_id: str
    source_column: str
    target_node_id: str
    target_column: str
    role: ColumnRole


@dataclass
class ColumnLineage:
    """The upstream source -> transform -> artifact chain behind a target column.

    Attributes
    ----------
    target_node_id: the node id lineage was traced for.
    target_column: the output column name lineage was traced for.
    nodes: the target node plus every ancestor reachable by walking edges backward
        (source <- target), deduplicated, in deterministic topological order. The target
        node is always last.
    edges: every column edge in *graph* whose source and target are both in ``nodes``, in
        deterministic order.
    """

    target_node_id: str
    target_column: str
    nodes: list[ColumnLineageNode] = field(default_factory=list)
    edges: list[ColumnLineageEdge] = field(default_factory=list)


@public_op(name="ef.research.trace_lineage")
def trace_lineage(graph: Graph, node_id: IRId) -> Lineage:
    """Trace the upstream lineage of *node_id* within *graph*.

    Walks edges backward from *node_id* (an edge's ``target.node_id`` -> its
    ``source.node_id``) to collect every ancestor node, handling branching (a node with
    multiple upstream sources) and merging (two paths converging on a shared ancestor)
    correctly via a visited-set BFS/DFS -- each ancestor is visited at most once regardless of
    how many downstream paths reach it.

    Parameters
    ----------
    graph:
        A structurally valid Graph (edge endpoints are assumed to reference existing
        nodes/ports -- the Graph validator enforces this at construction time).
    node_id:
        The id of the node to trace lineage for.

    Returns
    -------
    Lineage
        ``target_node_id=node_id``, ``nodes`` containing *node_id* and every ancestor in
        deterministic topological order (target last), and ``edges`` containing every edge of
        *graph* connecting two nodes both present in ``nodes``, itself in a deterministic
        order that does not depend on the order the edges were added to *graph*.

    Raises
    ------
    UnknownNodeError
        If *node_id* does not exist in *graph*.
    """
    # Deferred import: emergentflow.codegen's package __init__ eagerly imports
    # emergentflow.nodes (for the declarative compiler), which imports every reference node
    # including the research.build_report node -- which imports back from emergentflow.research.
    # A module-level import here would make that a real circular import whenever
    # emergentflow.research is the first of the two packages touched (e.g. iterating
    # emergentflow.__all__, where "research" precedes "codegen"). Deferring to call time avoids
    # it: by the time trace_lineage is actually invoked, both packages are already initialized.
    from emergentflow.codegen.traversal import topological_sort

    if node_id not in graph.nodes:
        raise UnknownNodeError(
            f"node {node_id!r} does not exist in this graph; known node ids: "
            f"{sorted(graph.nodes)!r}."
        )

    # Backward adjacency: node_id -> the node ids feeding one of its IN ports.
    predecessors: dict[str, list[str]] = {nid: [] for nid in graph.nodes}
    for edge in graph.edges.values():
        predecessors[edge.target.node_id].append(edge.source.node_id)

    visited: set[str] = {node_id}
    frontier = [node_id]
    while frontier:
        current = frontier.pop()
        for pred in predecessors[current]:
            if pred not in visited:
                visited.add(pred)
                frontier.append(pred)

    # A degenerate cycle is tolerated, mirroring `trace_column_lineage`: the
    # visited-set walk above already terminated (so every node in `visited`
    # genuinely feeds `node_id`); we only need a stable ordering, which falls
    # back to insertion order when no topological order exists.
    try:
        order = [nid for nid in topological_sort(graph) if nid in visited]
    except Exception:
        order = [nid for nid in graph.nodes if nid in visited]
        if node_id not in order:
            order.append(node_id)

    nodes = [
        LineageNode(node_id=nid, node_type=graph.nodes[nid].type, label=graph.nodes[nid].label)
        for nid in order
    ]
    # Deterministic edge order, mirroring the discipline every other pass keeps
    # (`topological_sort`'s node-id tie-break, `build_wiring_map`'s sorted fan-in sources,
    # `validate`'s `sorted(graph.edges.items())`): iterating `graph.edges.values()` directly
    # would follow dict INSERTION order, so two structurally identical graphs whose edges
    # were added in a different order -- ordinary canvas editing -- would trace to different
    # `edges` orderings. Keyed to follow `order` (so hops read along the chain `nodes`
    # already presents) with the edge id as a final tie-break for parallel edges.
    position = {nid: i for i, nid in enumerate(order)}
    in_subgraph = [
        (edge_id, edge)
        for edge_id, edge in graph.edges.items()
        if edge.source.node_id in visited and edge.target.node_id in visited
    ]
    in_subgraph.sort(
        key=lambda item: (
            position[item[1].source.node_id],
            position[item[1].target.node_id],
            item[0],
        )
    )
    edges = [
        LineageEdge(
            source_node_id=edge.source.node_id,
            source_port=edge.source.port_id,
            target_node_id=edge.target.node_id,
            target_port=edge.target.port_id,
        )
        for _edge_id, edge in in_subgraph
    ]

    return Lineage(target_node_id=node_id, nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Column-level lineage (Epic 18)
# ---------------------------------------------------------------------------
#
# Column lineage extends the same on-demand, pure computation discipline as
# trace_lineage: it is never stored on the Graph. An optional `column_effect`
# declaration on a node's spec (introduced in Epic 18) tells the tracer how to
# map input columns to output columns; absent a declaration, the tracer reports
# `unknown` rather than inventing an edge (the epic's "unknown is a first-class
# answer" bet). The high-value families get explicit resolvers (select_columns
# names its columns, derive_column's expression references are parsed); the
# long tail falls back to the declared `column_effect` and then to `unknown`.


def _param_values(node: Node) -> dict[str, Any]:
    return {p.name: p.value for p in node.params}


def _declared_effect(node: Node) -> ColumnEffect | None:
    """The declared ``column_effect`` for *node*'s type, or ``None``.

    Looked up through the node registry (deferred import, matching the
    existing deferral in ``trace_lineage`` to avoid the ``research`` ⇄ ``nodes``
    import cycle). An absent declaration returns ``None``.
    """
    from emergentflow.nodes.registry import get

    try:
        definition = get(node.type)
    except KeyError:
        return None
    return getattr(definition, "column_effect", None)


def _derive_source_cols(expr: str) -> tuple[str, ...]:
    """Every column name referenced by a derive expression (ast parse, best effort).

    Excludes bare function calls (e.g. ``log1p(...)``), which are operators, not
    columns; only bare ``ast.Name`` identifiers used as operands are columns.
    """
    import ast as _ast

    try:
        tree = _ast.parse(expr, mode="eval")
    except SyntaxError:
        return ()
    excluded: set[str] = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            # A qualified call like `np.sqrt(...)` / `np.linalg.norm(...)` is an
            # operator, not a column: exclude the base of its attribute chain
            # (`np`) so it isn't mistaken for an operand column.
            func = node.func
            while isinstance(func, _ast.Attribute):
                func = func.value
            if isinstance(func, _ast.Name):
                excluded.add(func.id)
            # Bare function names (e.g. `log1p` in `log1p(...)`) are operators.
            if isinstance(node.func, _ast.Name):
                excluded.add(node.func.id)
    referenced = {
        n.id for n in _ast.walk(tree) if isinstance(n, _ast.Name) and n.id not in excluded
    }
    return tuple(sorted(referenced))


def _derive_spec_source_cols(spec: Mapping[str, Any]) -> tuple[str, ...]:
    """Every column a derive *spec* references, across ``expr`` and case-when ``when``
    clauses (whose ``if`` conditions are expressions). Mirrors the ``expr``-only
    ``_derive_source_cols`` for the conditional-column shape so a case-when derived
    column's lineage walks its condition references too.
    """
    refs: set[str] = set()
    expr = spec.get("expr")
    if isinstance(expr, str):
        refs |= set(_derive_source_cols(expr))
    when = spec.get("when")
    if isinstance(when, list):
        for branch in when:
            if isinstance(branch, Mapping) and isinstance(branch.get("if"), str):
                refs |= set(_derive_source_cols(branch["if"]))
    return tuple(sorted(refs))


def _incoming_edges(graph: Graph, node_id: str) -> list[tuple[str, str, str]]:
    """(source_node_id, source_port_id, target_port_id) edges targeting *node_id*."""
    return [
        (e.source.node_id, e.source.port_id, e.target.port_id)
        for e in graph.edges.values()
        if e.target.node_id == node_id
    ]


def _frame_predecessor(graph: Graph, node: Node) -> str | None:
    """The single upstream node feeding *node*'s first IN port, or ``None``.

    Transform nodes carry one IN ``frame`` table; the chain follows that edge.
    For nodes whose only IN port is ambiguous (multiple IN tables, e.g. a
    merge) the caller treats provenance as unresolved rather than guessing.
    """
    ins = [p for p in node.ports if p.direction.value == "in"]
    if not ins:
        return None
    in_port_id = ins[0].id
    matches = [
        (src, spid, tpid)
        for (src, spid, tpid) in _incoming_edges(graph, node.id)
        if tpid == in_port_id
    ]
    if not matches:
        # Fall back to the single incoming edge if it exists.
        all_in = _incoming_edges(graph, node.id)
        if len(all_in) == 1:
            return all_in[0][0]
        return None
    if len(matches) == 1:
        return matches[0][0]
    return None


def _resolve_column(
    graph: Graph, node: Node, column: str
) -> tuple[ColumnRole, tuple[str, ...]] | None:
    """How *column* is produced at *node*. ``None`` ⇒ statically unknowable here.

    Returns ``(role, source_columns)``. ``source_columns`` names the *input*
    column(s) feeding *column* (empty for ``SOURCE``). Resolution:
      * explicit per-node-type semantics (select/derive);
      * a declared ``PASSTHROUGH`` column_effect (1:1 carry);
      * a node with no upstream → a ``SOURCE`` boundary;
      * otherwise ``None`` (unknown — never a guessed passthrough).
    """
    ntype = node.type
    if ntype == "clean.select_columns":
        values = _param_values(node)
        chosen = values.get("columns")
        drop = bool(values.get("drop"))
        if isinstance(chosen, list):
            names = {str(c) for c in chosen if isinstance(c, str)}
            kept = column in names
            if drop:
                kept = column not in names
            if kept:
                return (ColumnRole.PASSTHROUGH, (column,))
        return None
    if ntype == "clean.derive_column":
        values = _param_values(node)
        specs = values.get("columns")
        derived: set[str] = set()
        if isinstance(specs, list):
            for spec in specs:
                if isinstance(spec, dict) and isinstance(spec.get("name"), str):
                    derived.add(spec["name"])
        if column in derived:
            for spec in specs or []:
                if isinstance(spec, dict) and spec.get("name") == column:
                    return (ColumnRole.DERIVED, _derive_spec_source_cols(spec))
            return (ColumnRole.DERIVED, ())
        # Unknown/non-derived column passes through from the input table.
        if _frame_predecessor(graph, node) is not None:
            return (ColumnRole.PASSTHROUGH, (column,))
        return None
    # Declared passthrough column effect.
    from emergentflow.nodes.spec import ColumnEffectKind

    effect = _declared_effect(node)
    if effect is not None and effect.kind == ColumnEffectKind.SOURCE:
        return (ColumnRole.SOURCE, ())
    if effect is not None and effect.kind == ColumnEffectKind.PASSTHROUGH:
        if _frame_predecessor(graph, node) is not None:
            return (ColumnRole.PASSTHROUGH, (column,))
        return None
    # A node with no upstream produces columns; the chain terminates here.
    if not _incoming_edges(graph, node.id):
        return (ColumnRole.SOURCE, ())
    return None


def _is_source(graph: Graph, node_id: str) -> bool:
    return not _incoming_edges(graph, node_id)


def _surviving_columns(node: Node, incoming: Iterable[str]) -> set[str]:
    """Which of *incoming* columns are present on *node*'s output table.

    Used by impact analysis to stop propagating a seed column through a node
    that drops it (e.g. ``clean.select_columns`` with ``drop=True``), so the
    blast radius doesn't overstate reach past a node that eliminated the column.
    For every node type without explicit drop semantics, the incoming columns
    survive unchanged.
    """
    if node.type == "clean.select_columns":
        values = _param_values(node)
        chosen = values.get("columns")
        drop = bool(values.get("drop"))
        if isinstance(chosen, list):
            names = {str(c) for c in chosen if isinstance(c, str)}
            if drop:
                return set(incoming) - names
            return set(incoming) & names
    return set(incoming)


@public_op(name="ef.research.trace_column_lineage")
def trace_column_lineage(
    graph: Graph,
    node_id: IRId,
    column: str,
    *,
    observed: Mapping[str, Sequence[str]] | None = None,
) -> ColumnLineage:
    """Trace the upstream provenance of one *column* on one node.

    Pure and on-demand (never stored), mirroring ``trace_lineage``. Walks the
    graph backward from ``node_id`` following the target column's derivation
    chain: a passthrough/derived column steps to the upstream node that fed the
    transform's input table; a source node terminates the chain as
    ``SOURCE``; wherever static resolution genuinely breaks (an undeclared
    node, ``custom_code``/``sql_query``, a merge) the chain reports an explicit
    ``ColumnRole.UNKNOWN`` node and stops — it never invents an edge.

    Parameters
    ----------
    graph:
        A structurally valid Graph.
    node_id:
        The id of the node owning *column* on its output.
    column:
        An output column name on *node_id*.
    observed:
        Optional mapping of ``node_id`` → its observed output column names,
        refined from the last run's schema (Epic 18 Story 4). A node that is
        statically undecidable (``sql_query``/``http_fetch``/``custom_code``)
        but whose observed columns include *column* terminates as an observed
        ``SOURCE`` rather than ``unknown``, so a ``sql_query``-rooted flow
        traces after one run. ``custom_code`` still breaks the chain (no
        upstream) even when observed.

    Returns
    -------
    ColumnLineage
        ``target_node_id=node_id``, ``target_column=column``, ``nodes`` in
        deterministic topological order (target last) and ``edges`` in a
        matching deterministic order, containing an explicit ``unknown``
        boundary whenever provenance breaks.

    Raises
    ------
    UnknownNodeError
        If *node_id* does not exist in *graph*.
    """
    from emergentflow.codegen.traversal import topological_sort

    if node_id not in graph.nodes:
        raise UnknownNodeError(
            f"node {node_id!r} does not exist in this graph; known node ids: "
            f"{sorted(graph.nodes)!r}."
        )

    # Deterministic node order (topo, target handled last) for stable output.
    # A degenerate cycle is tolerated: the visited-set walk terminates, and we
    # fall back to insertion order for a stable presentation.
    try:
        topo = topological_sort(graph)
    except Exception:
        topo = list(graph.nodes)
    order = [nid for nid in topo]
    if node_id not in order:
        order.append(node_id)
    position = {nid: i for i, nid in enumerate(order)}

    visited: set[tuple[str, str]] = set()
    nodes: list[ColumnLineageNode] = []
    edges: list[ColumnLineageEdge] = []

    def walk(nid: str, col: str) -> None:
        if (nid, col) in visited:
            return
        visited.add((nid, col))
        node = graph.nodes[nid]
        resolved = _resolve_column(graph, node, col)
        if resolved is not None:
            role, source_cols = resolved
        elif (
            node.type != "script.custom_code"
            and observed is not None
            and col in observed.get(nid, ())
        ):
            # Last-run observed schema refines a statically-undecidable node:
            # its output column is known, but provenance stops here (Epic 18,
            # Story 4). custom_code still terminates the chain (no upstream) --
            # it must NOT be asserted as a genetic SOURCE just because a prior
            # run observed an output column, since that would falsely claim an
            # arbitrary computed column is a data origin. It falls through to
            # the UNKNOWN boundary below instead.
            role, source_cols = ColumnRole.SOURCE, ()
            nodes.append(
                ColumnLineageNode(
                    node_id=nid,
                    node_type=node.type,
                    label=node.label,
                    column=col,
                    role=role,
                    source_column=None,
                    detail="observed in last run (column not statically declared)",
                )
            )
            return
        else:
            nodes.append(
                ColumnLineageNode(
                    node_id=nid,
                    node_type=node.type,
                    label=node.label,
                    column=col,
                    role=ColumnRole.UNKNOWN,
                    detail="column not resolvable from static declaration",
                )
            )
            return
        node_entry = ColumnLineageNode(
            node_id=nid,
            node_type=node.type,
            label=node.label,
            column=col,
            role=role,
            source_column=source_cols[0] if source_cols else None,
            detail=(
                f"derived from {', '.join(source_cols)}"
                if role == ColumnRole.DERIVED and source_cols
                else None
            ),
        )
        if role == ColumnRole.SOURCE or not source_cols:
            nodes.append(node_entry)
            return
        pred = _frame_predecessor(graph, node)
        if pred is None:
            if any(e.target.node_id == nid for e in graph.edges.values()):
                # Multi-table input: provenance genuinely splits here -> unknown.
                nodes.append(
                    ColumnLineageNode(
                        node_id=nid,
                        node_type=node.type,
                        label=node.label,
                        column=col,
                        role=ColumnRole.UNKNOWN,
                        detail="column flows from multiple upstream inputs; origin ambiguous",
                    )
                )
                return
            # A terminal node producing the column from named sources with no
            # further upstream (e.g. the head of a two-hop chain): keep its
            # resolved entry and stop.
            nodes.append(node_entry)
            return
        nodes.append(node_entry)
        for sc in source_cols:
            edges.append(
                ColumnLineageEdge(
                    source_node_id=pred,
                    source_column=sc,
                    target_node_id=nid,
                    target_column=col,
                    role=role,
                )
            )
            walk(pred, sc)

    walk(node_id, column)

    nodes.sort(key=lambda n: position[n.node_id])
    edges.sort(
        key=lambda e: (position[e.source_node_id], position[e.target_node_id], e.source_column)
    )
    return ColumnLineage(
        target_node_id=node_id,
        target_column=column,
        nodes=nodes,
        edges=edges,
    )


@public_op(name="ef.research.trace_column_impact")
def trace_column_impact(
    graph: Graph,
    node_id: IRId,
    column: str,
    *,
    observed: Mapping[str, Sequence[str]] | None = None,
) -> ColumnLineage:
    """Trace every downstream column and node that (transitively) depends on *column*.

    The inverse of :func:`trace_column_lineage`. Walks the graph forward from
    ``node_id``'s *column*, collecting every consumer node and the column(s)
    into which it flows. Wherever an unresolvable node intervenes, the answer
    records an explicit ``unknown`` boundary (the true blast radius may be
    larger — the caller is expected to surface this).

    Parameters
    ----------
    graph:
        A structurally valid Graph.
    node_id:
        The id of the node owning *column* on its output.
    column:
        An output column name on *node_id*.
    observed:
        Optional mapping of ``node_id`` → its observed output column names
        (Epic 18 Story 4). Used to refine downstream resolution where a node's
        columns are only known from the last run.

    Returns
    -------
    ColumnLineage
        ``target_node_id=node_id``, ``target_column=column``, ``nodes``
        (sources-first topological order; the originating node is first) and
        downstream ``edges``.
    """
    from emergentflow.codegen.traversal import topological_sort

    if node_id not in graph.nodes:
        raise UnknownNodeError(
            f"node {node_id!r} does not exist in this graph; known node ids: "
            f"{sorted(graph.nodes)!r}."
        )

    children: dict[str, list[str]] = {nid: [] for nid in graph.nodes}
    for edge in graph.edges.values():
        children[edge.source.node_id].append(edge.target.node_id)

    # Forward reachability from the seed column's node.
    visited_nodes: set[str] = {node_id}
    frontier = [node_id]
    while frontier:
        cur = frontier.pop()
        for child in children[cur]:
            if child not in visited_nodes:
                visited_nodes.add(child)
                frontier.append(child)

    try:
        order = [nid for nid in topological_sort(graph) if nid in visited_nodes or nid == node_id]
    except Exception:
        # A degenerate cycle is tolerated (same policy as `trace_column_lineage`):
        # the reachability walk above already bounded `visited_nodes`, so fall back
        # to insertion order for a stable presentation rather than crashing.
        order = [nid for nid in graph.nodes if nid in visited_nodes or nid == node_id]
    downstream_order = [nid for nid in order]
    position = {nid: i for i, nid in enumerate(downstream_order)}

    # Forward column propagation: which columns reach each downstream node.
    reach: dict[str, set[str]] = {node_id: {column}}
    for nid in downstream_order:
        if nid == node_id:
            continue
        node = graph.nodes[nid]
        collected: set[str] = set()
        for src, _sp, _tpid in _incoming_edges(graph, nid):
            outs = reach.get(src)
            if outs is not None:
                collected |= outs
        reach[nid] = _surviving_columns(node, collected)
        # A derived column whose expression references a reaching seed column is
        # itself impacted and must propagate forward so transitive consumers
        # (e.g. a node deriving from *it*) are reported as impacted too.
        if node.type == "clean.derive_column":
            values = _param_values(node)
            specs = values.get("columns")
            if isinstance(specs, list):
                for spec in specs:
                    if not isinstance(spec, dict):
                        continue
                    name = spec.get("name")
                    if not isinstance(name, str):
                        continue
                    refs = set(_derive_spec_source_cols(spec))
                    if refs & reach[nid]:
                        reach[nid].add(name)

    nodes_by_id: dict[str, list[ColumnLineageNode]] = {}
    for nid in downstream_order:
        node = graph.nodes[nid]
        cols = reach.get(nid, set())
        if nid == node_id:
            nodes_by_id[nid] = [
                ColumnLineageNode(
                    node_id=nid,
                    node_type=node.type,
                    label=node.label,
                    column=column,
                    role=ColumnRole.SOURCE,
                )
            ]
            continue
        if not cols:
            nodes_by_id[nid] = [
                ColumnLineageNode(
                    node_id=nid,
                    node_type=node.type,
                    label=node.label,
                    column="",
                    role=ColumnRole.UNKNOWN,
                    detail="no seed column reaches this node",
                )
            ]
            continue
        produced: list[ColumnLineageNode] = []
        for c in sorted(cols):
            resolved = _resolve_column(graph, node, c)
            if resolved is not None:
                role = resolved[0]
            elif observed is not None and c in observed.get(nid, ()):
                role = ColumnRole.SOURCE
            else:
                role = ColumnRole.UNKNOWN
            produced.append(
                ColumnLineageNode(
                    node_id=nid,
                    node_type=node.type,
                    label=node.label,
                    column=c,
                    role=role,
                )
            )
        # A derived column whose expression references a reaching seed column is
        # itself impacted: surface it so the blast radius includes the derived
        # feature, not just the passthrough of the seed column.
        if node.type == "clean.derive_column":
            values = _param_values(node)
            specs = values.get("columns")
            if isinstance(specs, list):
                for spec in specs:
                    if not isinstance(spec, dict):
                        continue
                    name = spec.get("name")
                    if not isinstance(name, str):
                        continue
                    refs = set(_derive_spec_source_cols(spec))
                    if refs & cols:
                        produced.append(
                            ColumnLineageNode(
                                node_id=nid,
                                node_type=node.type,
                                label=node.label,
                                column=name,
                                role=ColumnRole.DERIVED,
                                source_column=next(iter(sorted(refs & cols))),
                                detail=f"derived from {', '.join(sorted(refs & cols))}",
                            )
                        )
        nodes_by_id[nid] = produced

    nodes: list[ColumnLineageNode] = []
    edges: list[ColumnLineageEdge] = []
    for nid in downstream_order:
        nodes.extend(nodes_by_id[nid])
        for src, _sp, _tp in _incoming_edges(graph, nid):
            if src not in reach:
                continue
            # Only emit an edge for a seed column that survives into *nid*'s
            # output: a node that drops the column (e.g. select_columns) is a
            # blast-radius dead-end, not a passthrough hop.
            for sc in sorted(reach[src] & reach[nid]):
                edges.append(
                    ColumnLineageEdge(
                        source_node_id=src,
                        source_column=sc,
                        target_node_id=nid,
                        target_column=sc,
                        role=ColumnRole.PASSTHROUGH,
                    )
                )

    nodes.sort(key=lambda n: position[n.node_id])
    edges.sort(
        key=lambda e: (position[e.source_node_id], position[e.target_node_id], e.source_column)
    )
    return ColumnLineage(
        target_node_id=node_id,
        target_column=column,
        nodes=nodes,
        edges=edges,
    )
