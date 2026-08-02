"""
emergentflow.ir.graph
~~~~~~~~~~~~~~~~~~~
Graph model — top-level, serialisable IR object for an Emergent Flow pipeline.

The Graph assembles nodes and edges into a CRDT-friendly id→object map and
carries the schema version and paradigm tag.  Structural validation is enforced
at construction time; invalid graphs are rejected with clear error messages.

ADR refs:
  - ADR 0002: declarative IR, executable as data
  - ADR 0003: two first-class paradigms (FUNCTIONAL / DECLARATIVE) with
              Option A unified nesting via Node.subgraph
  - ADR 0004: artifact bytes are never embedded in the IR (not relevant here,
              just confirmed we don't do it)
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import Direction, IRId, IRModel, Paradigm
from .edge import Edge
from .node import Node
from .params import Param

# ---------------------------------------------------------------------------
# Schema version — bump when the Graph wire format changes incompatibly
# ---------------------------------------------------------------------------

CURRENT_SCHEMA_VERSION: int = 2

# The version assumed for a serialized graph that carries no ``schema_version`` field at
# all — i.e. one written before versioning existed. Such a graph is treated as the earliest
# schema and routed through the full migration chain. Both the loader (serialize) and the
# migration walker default to THIS value, so they cannot drift apart when CURRENT bumps.
INITIAL_SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


class Graph(IRModel):
    """Top-level, serialisable IR graph for an Emergent Flow pipeline.

    Attributes
    ----------
    schema_version:
        Embedded schema version (default: CURRENT_SCHEMA_VERSION).  Allows
        loaders to detect and reject stale or future graphs.
    paradigm:
        Graph-level paradigm tag (default: FUNCTIONAL).  Combined with
        per-node ``paradigm``, this drives codegen/execution branching.
    name:
        Optional human-friendly label for the graph.
    nodes:
        CRDT-friendly id→Node map.  Keys MUST equal ``node.id``.
    edges:
        CRDT-friendly id→Edge map.  Keys MUST equal ``edge.id``.
    params:
        Optional graph-level id→Param map.  Keys MUST equal ``param.name``.
        Defaults to an empty map.
    """

    schema_version: int = CURRENT_SCHEMA_VERSION
    paradigm: Paradigm = Paradigm.FUNCTIONAL
    name: str | None = None
    nodes: dict[IRId, Node] = Field(default_factory=dict)
    edges: dict[IRId, Edge] = Field(default_factory=dict)
    params: dict[IRId, Param] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Structural validator
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _validate_structure(self) -> Graph:
        """Enforce graph-level structural invariants.

        Checks (all O(nodes + edges)):
        1. Key/id agreement in nodes and edges maps.
        2. Edge endpoints reference nodes that exist in the graph.
        3. Edge endpoints reference ports that exist on those nodes.
        4. Source port direction == OUT; target port direction == IN.
        5. group_id, when set, must reference an existing node.
        """
        # Build a flat (node_id, port_id) → Direction lookup once.
        port_direction: dict[tuple[IRId, IRId], Direction] = {}
        for node_id, node in self.nodes.items():
            # 1a. Key/id agreement for nodes.
            if node.id != node_id:
                raise ValueError(
                    f"Graph.nodes key {node_id!r} does not match node.id {node.id!r}. "
                    "Map keys must equal the object's own .id."
                )
            for port in node.ports:
                port_direction[(node_id, port.id)] = port.direction

        for param_name, param in self.params.items():
            # 1c. Key/name agreement for graph-level params.
            if param.name != param_name:
                raise ValueError(
                    f"Graph.params key {param_name!r} does not match param.name {param.name!r}. "
                    "Map keys must equal the object's own .name."
                )

        for edge_id, edge in self.edges.items():
            # 1b. Key/id agreement for edges.
            if edge.id != edge_id:
                raise ValueError(
                    f"Graph.edges key {edge_id!r} does not match edge.id {edge.id!r}. "
                    "Map keys must equal the object's own .id."
                )

            # 2. Edge endpoints reference existing nodes.
            if edge.source.node_id not in self.nodes:
                raise ValueError(
                    f"Edge {edge.id!r}: source.node_id {edge.source.node_id!r} "
                    "does not reference any node in this graph."
                )
            if edge.target.node_id not in self.nodes:
                raise ValueError(
                    f"Edge {edge.id!r}: target.node_id {edge.target.node_id!r} "
                    "does not reference any node in this graph."
                )

            # 3. Edge endpoints reference existing ports.
            src_key = (edge.source.node_id, edge.source.port_id)
            if src_key not in port_direction:
                raise ValueError(
                    f"Edge {edge.id!r}: source.port_id {edge.source.port_id!r} "
                    f"does not exist on node {edge.source.node_id!r}."
                )
            tgt_key = (edge.target.node_id, edge.target.port_id)
            if tgt_key not in port_direction:
                raise ValueError(
                    f"Edge {edge.id!r}: target.port_id {edge.target.port_id!r} "
                    f"does not exist on node {edge.target.node_id!r}."
                )

            # 4. Direction sanity: source must be OUT, target must be IN.
            src_dir = port_direction[src_key]
            if src_dir != Direction.OUT:
                raise ValueError(
                    f"Edge {edge.id!r}: source port {edge.source.port_id!r} on node "
                    f"{edge.source.node_id!r} has direction {src_dir!r}; "
                    "source ports must have direction OUT."
                )
            tgt_dir = port_direction[tgt_key]
            if tgt_dir != Direction.IN:
                raise ValueError(
                    f"Edge {edge.id!r}: target port {edge.target.port_id!r} on node "
                    f"{edge.target.node_id!r} has direction {tgt_dir!r}; "
                    "target ports must have direction IN."
                )

        # 5. group_id integrity.
        for node_id, node in self.nodes.items():
            if node.group_id is not None and node.group_id not in self.nodes:
                raise ValueError(
                    f"Node {node_id!r}: group_id {node.group_id!r} does not reference "
                    "any node in this graph."
                )

        return self

    # ------------------------------------------------------------------
    # Convenience mutators
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Insert *node* into the nodes map, keyed by node.id.

        Note: Pydantic v2 model_validator(mode="after") runs at construction
        time and on ``model_validate``/``model_copy`` calls.  It does NOT
        automatically re-run on in-place dict mutation.  For construction-time
        validation (the primary contract), always build the graph with complete
        ``nodes`` / ``edges`` dicts, or reconstruct via ``model_validate``.
        """
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        """Insert *edge* into the edges map, keyed by edge.id.

        See ``add_node`` note about when the structural validator runs.
        """
        self.edges[edge.id] = edge


# ---------------------------------------------------------------------------
# Resolve the Node.subgraph: "Graph | None" forward reference.
#
# node.py uses TYPE_CHECKING to declare the annotation without importing Graph
# at runtime (to avoid a circular import).  Now that Graph is defined, we call
# model_rebuild() on both classes so Pydantic can wire up the full CoreSchema.
# ---------------------------------------------------------------------------

Node.model_rebuild()
Graph.model_rebuild()
