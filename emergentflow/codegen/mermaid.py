"""
emergentflow.codegen.mermaid
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Mermaid ``flowchart`` rendering of a graph IR (issue #169).

`to_mermaid` is a pure, dependency-free *visual* projection of the IR: it never
parses or executes anything, mutates nothing, and is deterministic (topological
order with min-id tie-breaks, stable id allocation) so its output can be
golden-tested and pasted into GitHub Markdown, which renders Mermaid natively.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal

from emergentflow.api import public_op
from emergentflow.codegen.errors import CycleError
from emergentflow.codegen.naming import _slugify
from emergentflow.codegen.traversal import topological_sort
from emergentflow.ir.common import IRId
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node
from emergentflow.nodes import registry as default_node_registry

# Mirrors ui/src/styles/tokens.css --fam-* (canvas family colours).
FAMILY_COLORS: dict[str, str] = {
    "data": "#3b82f6",
    "clean": "#14b8a6",
    "stats": "#a78bfa",
    "ml": "#f59e0b",
    "nn": "#ec4899",
    "reports": "#10b981",
    "transform": "#f97316",
    "notes": "#eab308",
    "viz": "#06b6d4",
    "timeseries": "#0ea5e9",
    "recommend": "#d946ef",
    "explain": "#f43f5e",
    "llm": "#818cf8",
    "eval": "#84cc16",
    "embed": "#2dd4bf",
    "research": "#64748b",
    "script": "#94a3b8",
    "causal": "#8b5cf6",
    "psychometrics": "#0ea5e9",
    "layout": "#64748b",
}

_PRESENTATION_TYPES = frozenset({"notes.markdown", "reports.result_card", "layout.callout"})
_GROUP_TYPE = "layout.group"
DEFAULT_MAX_NODES = 150
_HIGHLIGHT_CLASS = "highlight"
_HIGHLIGHT_STYLE = "stroke:#ef4444,stroke-width:4px"
_INDENT = "    "

# Mermaid decodes ``#name;`` / ``#NNN;`` entities inside quoted labels.
_ESCAPES: dict[str, str] = {
    '"': "#quot;",
    "#": "#35;",
    "%": "#37;",
    "&": "#amp;",
    "<": "#lt;",
    ">": "#gt;",
    "[": "#91;",
    "]": "#93;",
    "|": "#124;",
    "`": "#96;",
    "{": "#123;",
    "}": "#125;",
    "\r": "",
    "\n": "<br/>",
}


def _mermaid_label(text: str) -> str:
    """Escape *text* for use inside a quoted Mermaid label (single pass, no double-escape)."""
    return "".join(_ESCAPES.get(ch, ch) for ch in text)


class _IdAllocator:
    """Allocates unique, deterministic Mermaid ids, memoised per (prefix, scope, raw id)."""

    def __init__(self) -> None:
        self._used: set[str] = set()
        self._memo: dict[tuple[str, int, str], str] = {}

    def alloc(self, prefix: str, raw_id: str, scope: int = 0) -> str:
        key = (prefix, scope, raw_id)
        if key in self._memo:
            return self._memo[key]
        base = f"{prefix}_{_slugify(raw_id) or 'x'}"
        candidate = base
        n = 2
        while candidate in self._used:
            candidate = f"{base}_{n}"
            n += 1
        self._used.add(candidate)
        self._memo[key] = candidate
        return candidate


def _order(graph: Graph) -> list[IRId]:
    """Topological order, falling back to sorted ids for cyclic graphs (never raises)."""
    try:
        return topological_sort(graph)
    except CycleError:
        return sorted(graph.nodes)


def _is_visible(node: Node, include_notes: bool) -> bool:
    if node.type == _GROUP_TYPE:
        return False
    return include_notes or node.type not in _PRESENTATION_TYPES


def _title(node: Node) -> str:
    label = (node.label or "").strip()
    if label:
        return label
    definition = default_node_registry.try_get(node.type)
    reg_label = getattr(definition, "label", None) if definition is not None else None
    return str(reg_label) if reg_label else node.type


def _node_text(node: Node, show_types: bool) -> str:
    title = _title(node)
    text = _mermaid_label(title)
    if show_types and title != node.type:
        text += "<br/><small>" + _mermaid_label(node.type) + "</small>"
    return text


def _family(node: Node) -> str | None:
    definition = default_node_registry.try_get(node.type)
    if definition is not None:
        return str(definition.family)
    if "." in node.type:
        return node.type.split(".")[0]
    return None


def _group_name(node: Node) -> str:
    label = (node.label or "").strip()
    if label:
        return label
    for param in node.params:
        if param.name == "label" and param.value is not None and str(param.value).strip():
            return str(param.value).strip()
    return "Group"


def _port_name(node: Node, port_id: str) -> str:
    for port in node.ports:
        if port.id == port_id:
            return port.name
    return port_id


def _group_of(graph: Graph, visible_ids: list[IRId]) -> dict[IRId, IRId]:
    """Map each visible node to the ``layout.group`` node containing it (if any)."""
    mapping: dict[IRId, IRId] = {}
    for nid in visible_ids:
        gid = graph.nodes[nid].group_id
        if gid is not None and gid in graph.nodes and graph.nodes[gid].type == _GROUP_TYPE:
            mapping[nid] = gid
    return mapping


def _visible_inner(node: Node, include_notes: bool) -> list[IRId]:
    if node.subgraph is None:
        return []
    return [
        nid for nid in _order(node.subgraph) if _is_visible(node.subgraph.nodes[nid], include_notes)
    ]


def _edge_line(a: str, b: str, label: str) -> str:
    if label:
        return f"{a} -->|{_mermaid_label(label)}| {b}"
    return f"{a} --> {b}"


def _class_lines(
    drawn: list[tuple[str, str | None, set[str]]],
    highlight: Collection[IRId],
) -> list[str]:
    """Family + highlight ``classDef``/``class`` lines for ``(mermaid id, family, raw ids)``."""
    lines: list[str] = []
    families = sorted({fam for _, fam, _ in drawn if fam is not None and fam in FAMILY_COLORS})
    for fam in families:
        ids = ",".join(mid for mid, f, _ in drawn if f == fam)
        lines.append(f"classDef fam_{fam} stroke:{FAMILY_COLORS[fam]},stroke-width:2px")
        lines.append(f"class {ids} fam_{fam}")
    wanted = set(highlight)
    hl_ids = [mid for mid, _, raw in drawn if raw & wanted]
    if hl_ids:
        lines.append(f"classDef {_HIGHLIGHT_CLASS} {_HIGHLIGHT_STYLE}")
        lines.append(f"class {','.join(hl_ids)} {_HIGHLIGHT_CLASS}")
    return lines


class _FullRenderer:
    """Renders groups and one level of container subgraphs as Mermaid ``subgraph`` blocks."""

    def __init__(self, graph: Graph, show_types: bool, include_notes: bool) -> None:
        self.show_types = show_types
        self.include_notes = include_notes
        self.ids = _IdAllocator()
        self.lines: list[str] = []
        self.drawn: dict[tuple[int, IRId], str] = {}
        self.draw_order: list[tuple[str, str | None, set[str]]] = []
        self.scopes: list[tuple[Graph, dict[IRId, int]]] = []
        self.add_scope(graph)

    def add_scope(self, graph: Graph) -> int:
        order = _order(graph)
        self.scopes.append((graph, {nid: i for i, nid in enumerate(order)}))
        return len(self.scopes) - 1

    def emit_node(self, scope: int, node: Node, level: int, nested: bool) -> None:
        pad = _INDENT * level
        mid = self.ids.alloc("n", node.id, scope)
        text = _node_text(node, self.show_types)
        self.drawn[(scope, node.id)] = mid
        self.draw_order.append((mid, _family(node), {node.id}))
        inner = [] if nested else _visible_inner(node, self.include_notes)
        if not inner:
            if nested and node.subgraph is not None and node.subgraph.nodes:
                count = len(node.subgraph.nodes)
                self.lines.append(
                    f"{pad}%% flattened: nested subgraph of {_mermaid_label(_title(node))} "
                    f"({count} nodes) not shown"
                )
            self.lines.append(f'{pad}{mid}["{text}"]')
            return
        assert node.subgraph is not None
        inner_scope = self.add_scope(node.subgraph)
        self.lines.append(f'{pad}subgraph {mid}["{text}"]')
        for nid in inner:
            self.emit_node(inner_scope, node.subgraph.nodes[nid], level + 1, True)
        self.lines.append(f"{pad}end")

    def emit_group(self, gid: IRId, members: list[IRId]) -> None:
        graph = self.scopes[0][0]
        gnode = graph.nodes[gid]
        pad = _INDENT
        gmid = self.ids.alloc("g", gid)
        self.lines.append(f'{pad}subgraph {gmid}["{_mermaid_label(_group_name(gnode))}"]')
        for nid in members:
            self.emit_node(0, graph.nodes[nid], 2, False)
        self.lines.append(f"{pad}end")

    def edge_lines(self, *, show_ports: bool) -> list[str]:
        keyed: list[tuple[tuple[int, int, int, str], str]] = []
        for scope_idx, (graph, pos) in enumerate(self.scopes):
            for edge in graph.edges.values():
                a = self.drawn.get((scope_idx, edge.source.node_id))
                b = self.drawn.get((scope_idx, edge.target.node_id))
                if a is None or b is None:
                    continue
                label = ""
                if show_ports:
                    src = _port_name(graph.nodes[edge.source.node_id], edge.source.port_id)
                    tgt = _port_name(graph.nodes[edge.target.node_id], edge.target.port_id)
                    label = src if src == tgt else f"{src}→{tgt}"
                key = (
                    scope_idx,
                    pos[edge.source.node_id],
                    pos[edge.target.node_id],
                    edge.id,
                )
                keyed.append((key, _edge_line(a, b, label)))
        keyed.sort(key=lambda kv: kv[0])
        return [line for _, line in keyed]


def _render_full(
    graph: Graph,
    *,
    show_ports: bool,
    show_types: bool,
    groups: bool,
    include_notes: bool,
    highlight: Collection[IRId],
) -> list[str]:
    r = _FullRenderer(graph, show_types, include_notes)
    visible_ids = [nid for nid in _order(graph) if _is_visible(graph.nodes[nid], include_notes)]
    group_of = _group_of(graph, visible_ids) if groups else {}
    emitted: set[IRId] = set()
    for nid in visible_ids:
        gid = group_of.get(nid)
        if gid is None:
            r.emit_node(0, graph.nodes[nid], 1, False)
        elif gid not in emitted:
            emitted.add(gid)
            r.emit_group(gid, [m for m in visible_ids if group_of.get(m) == gid])
    body = list(r.lines)
    body += [_INDENT + line for line in r.edge_lines(show_ports=show_ports)]
    body += [_INDENT + line for line in _class_lines(r.draw_order, highlight)]
    return body


class _Item:
    """One drawn element of the collapsed (size-guarded) diagram."""

    def __init__(self, mid: str, text: str, family: str | None, raw: set[str]) -> None:
        self.mid = mid
        self.text = text
        self.family = family
        self.raw = raw


def _render_collapsed(
    graph: Graph,
    *,
    show_types: bool,
    groups: bool,
    include_notes: bool,
    highlight: Collection[IRId],
    max_nodes: int,
    count: int,
) -> tuple[list[str], str]:
    ids = _IdAllocator()
    visible_ids = [nid for nid in _order(graph) if _is_visible(graph.nodes[nid], include_notes)]
    group_of = _group_of(graph, visible_ids) if groups else {}
    items: list[_Item] = []
    item_of: dict[IRId, int] = {}
    group_item: dict[IRId, int] = {}
    for nid in visible_ids:
        gid = group_of.get(nid)
        if gid is None:
            node = graph.nodes[nid]
            item_of[nid] = len(items)
            items.append(
                _Item(
                    ids.alloc("n", nid),
                    _node_text(node, show_types),
                    _family(node),
                    {nid},
                )
            )
        elif gid not in group_item:
            members = [m for m in visible_ids if group_of.get(m) == gid]
            n = len(members)
            name = _mermaid_label(_group_name(graph.nodes[gid]))
            text = f"{name}<br/><small>{n} {'node' if n == 1 else 'nodes'}</small>"
            group_item[gid] = len(items)
            items.append(_Item(ids.alloc("g", gid), text, None, set(members)))
            for m in members:
                item_of[m] = group_item[gid]
        else:
            item_of[nid] = group_item[gid]
    kept = items[:max_nodes]
    pairs: set[tuple[int, int]] = set()
    for edge in graph.edges.values():
        si = item_of.get(edge.source.node_id)
        ti = item_of.get(edge.target.node_id)
        if si is None or ti is None or si == ti or si >= len(kept) or ti >= len(kept):
            continue
        pairs.add((si, ti))
    lines = [f'{_INDENT}{it.mid}["{it.text}"]' for it in kept]
    lines += [f"{_INDENT}{kept[a].mid} --> {kept[b].mid}" for a, b in sorted(pairs)]
    drawn = [(it.mid, it.family, it.raw) for it in kept]
    lines += [_INDENT + line for line in _class_lines(drawn, highlight)]
    # Group items stand for several nodes but are not drawn individually.
    individual = sum(1 for it in kept if not it.mid.startswith("g_"))
    omitted = count - individual
    note = (
        f"{_INDENT}%% truncated: {omitted} of {count} nodes not drawn individually "
        f"(limit {max_nodes}); GitHub caps Mermaid diagram size"
    )
    return lines, note


def _renderable_count(graph: Graph, include_notes: bool) -> int:
    total = 0
    for node in graph.nodes.values():
        if not _is_visible(node, include_notes):
            continue
        total += 1 + len(_visible_inner(node, include_notes))
    return total


@public_op(name="ef.to_mermaid")
def to_mermaid(
    graph: Graph,
    *,
    direction: Literal["LR", "TB"] = "LR",
    show_types: bool = True,
    show_ports: bool = True,
    highlight: Collection[IRId] = (),
    groups: bool = True,
    include_notes: bool = False,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> str:
    """Render *graph* as a Mermaid ``flowchart`` string.

    Pure and deterministic: nodes are laid out in topological order (sorted ids
    if the graph has a cycle), ids are allocated stably, and the input graph is
    never mutated. Labels are escaped with Mermaid entity syntax.

    Parameters
    ----------
    graph:
        The IR graph to draw.
    direction:
        ``"LR"`` (left-to-right, default) or ``"TB"`` (top-to-bottom).
    show_types:
        Append the node type under each node's title.
    show_ports:
        Label edges with port names (``src→tgt`` when they differ).
    highlight:
        Node ids to emphasise; unknown ids are ignored.
    groups:
        Draw ``layout.group`` containers as Mermaid subgraphs.
    include_notes:
        Also draw presentation-only nodes (notes, result cards, callouts).
    max_nodes:
        Size guard: above this many drawable nodes, groups and container
        subgraphs collapse to single nodes and the diagram is truncated.

    Returns
    -------
    str
        The Mermaid source, newline-terminated.

    Raises
    ------
    ValueError
        If *direction* is not ``"LR"``/``"TB"`` or *max_nodes* is below 1.
    """
    if direction not in ("LR", "TB"):
        raise ValueError(f"direction must be 'LR' or 'TB', got {direction!r}")
    if max_nodes < 1:
        raise ValueError(f"max_nodes must be >= 1, got {max_nodes!r}")

    if isinstance(highlight, str):  # a bare id is a Collection of characters otherwise
        highlight = (highlight,)
    header = f"flowchart {direction}"
    count = _renderable_count(graph, include_notes)
    if count > max_nodes:
        body, note = _render_collapsed(
            graph,
            show_types=show_types,
            groups=groups,
            include_notes=include_notes,
            highlight=highlight,
            max_nodes=max_nodes,
            count=count,
        )
        return "\n".join([header, note, *body]) + "\n"
    body = _render_full(
        graph,
        show_ports=show_ports,
        show_types=show_types,
        groups=groups,
        include_notes=include_notes,
        highlight=highlight,
    )
    return "\n".join([header, *body]) + "\n"
