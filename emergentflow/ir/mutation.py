"""
emergentflow.ir.mutation
~~~~~~~~~~~~~~~~~~~~
Mutation protocol for agent collaboration (Epic 14).

Provides a ``GraphMutation`` proposal model and a pure ``apply_mutation``
function that applies it to a ``Graph``, returning a new ``Graph``.
This module lives beside the graph IR and is never imported eagerly —
callers import it directly.

ADR 0019 records the design decision: the mutation protocol is an opt-in,
lazily-loaded module; nothing that already imports ``emergentflow`` or
``emergentflow.ir`` should pick up this code as a side effect.
"""

from __future__ import annotations

from pydantic import Field, ValidationError

from emergentflow.codegen.validation import Diagnostic, Diagnostics, Severity
from emergentflow.codegen.validation import validate as run_validate
from emergentflow.ir.common import IRModel
from emergentflow.ir.edge import Edge
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node, Position
from emergentflow.ir.params import Param, ParamValue
from emergentflow.nodes import registry as default_node_registry


class MutationError(Exception):
    """Raised by apply_mutation when a GraphMutation cannot be applied to a Graph."""


class GraphMutation(IRModel):
    """A proposal to mutate a Graph, submitted by an AI agent or a human.

    ``base_version`` is the Graph/session version this mutation was computed
    against (used for optimistic-concurrency staleness checks by the caller —
    this module itself does not check versions against anything, since a bare
    Graph has no version; the session layer, a later story, is responsible for
    that check).

    ``add_nodes``/``add_edges`` are added as-is (their ``.id`` fields, if
    unset, default-generate via ``new_id()`` same as any fresh ``Node()``/
    ``Edge()``).  Positions on added nodes are optional — layout is the
    canvas's job, not this module's.

    ``remove_nodes``/``remove_edges`` are lists of existing ids to delete.

    ``set_params`` is a partial per-node param update:
    ``node_id -> {param_name: new_value}``.  An agent never has to reconstruct
    a full ``Param`` object with ``type_token``/``default``, only the new value.

    ``author`` is a persona slug or the literal string ``"human"``.
    """

    base_version: int
    add_nodes: list[Node] = Field(default_factory=list)
    add_edges: list[Edge] = Field(default_factory=list)
    remove_nodes: list[str] = Field(default_factory=list)
    remove_edges: list[str] = Field(default_factory=list)
    set_params: dict[str, dict[str, ParamValue]] = Field(default_factory=dict)
    description: str = ""
    author: str = "human"


_CASCADE_STEP = 60.0


def _next_cascade_position(
    existing_positions: list[Position], index: int, taken: set[tuple[float, float]]
) -> tuple[Position, int]:
    """A position offset past the bounding box of *existing_positions*, stepped by *index*.

    Used as a safety net for GraphMutation.add_nodes left at the default
    Position() sentinel — keeps agent-proposed batches from stacking at the
    origin. The canvas is free to re-lay-out further; this only guarantees
    non-overlap.

    *taken* is the set of (x, y) points already claimed -- by pre-existing
    graph nodes or by earlier nodes in this same ``add_nodes`` batch, whether
    those landed on an explicit position or a previously cascaded one. The
    diagonal offset alone only avoids the pre-existing graph's bounding box;
    without also checking *taken*, a cascaded point can land exactly on an
    explicitly-positioned node added earlier in the same batch. Returns the
    chosen position and the index consumed (so the caller can resume
    cascading from the next index).
    """
    base_x = max((p.x for p in existing_positions), default=0.0)
    base_y = max((p.y for p in existing_positions), default=0.0)
    while True:
        offset = _CASCADE_STEP * (index + 1)
        position = Position(x=base_x + offset, y=base_y + offset)
        if (position.x, position.y) not in taken:
            return position, index
        index += 1


def apply_mutation(graph: Graph, m: GraphMutation) -> Graph:
    """Apply *m* to (a copy of) *graph* and return a new Graph.

    Never mutates *graph* or *m*.  Applies removes, then adds, then param
    updates.  Validates the result through Graph's structural constructor so
    dangling references (e.g. an edge whose source node was removed) surface
    as MutationError rather than a raw pydantic error.

    Raises
    ------
    MutationError
        If a remove targets a nonexistent id, an add collides with an existing
        id, a param update targets an unknown node, or the resulting graph
        fails structural validation.
    """
    # Shallow-copy the node/edge maps — we never mutate the originals.
    new_nodes = dict(graph.nodes)
    new_edges = dict(graph.edges)

    # ------------------------------------------------------------------
    # 1. Removes
    # ------------------------------------------------------------------
    for node_id in m.remove_nodes:
        if node_id not in new_nodes:
            raise MutationError(f"remove_nodes: node {node_id!r} does not exist in the graph.")
        del new_nodes[node_id]

    for edge_id in m.remove_edges:
        if edge_id not in new_edges:
            raise MutationError(f"remove_edges: edge {edge_id!r} does not exist in the graph.")
        del new_edges[edge_id]

    # ------------------------------------------------------------------
    # 2. Adds
    # ------------------------------------------------------------------
    existing_positions = [n.position for n in graph.nodes.values()]
    _default_position = Position()
    cascade_index = 0
    taken_positions = {(p.x, p.y) for p in existing_positions}
    for node in m.add_nodes:
        if node.id in new_nodes:
            raise MutationError(f"add_nodes: node id {node.id!r} already exists in the graph.")
        if node.position == _default_position:
            position, cascade_index = _next_cascade_position(
                existing_positions, cascade_index, taken_positions
            )
            node = node.model_copy(update={"position": position})
            cascade_index += 1
        taken_positions.add((node.position.x, node.position.y))
        new_nodes[node.id] = node

    for edge in m.add_edges:
        if edge.id in new_edges:
            raise MutationError(f"add_edges: edge id {edge.id!r} already exists in the graph.")
        new_edges[edge.id] = edge

    # ------------------------------------------------------------------
    # 3. Param updates
    # ------------------------------------------------------------------
    for node_id, param_updates in m.set_params.items():
        if node_id not in new_nodes:
            raise MutationError(f"set_params: node {node_id!r} does not exist in the graph.")

        node = new_nodes[node_id]
        definition_cls = default_node_registry.try_get(node.type)

        # Build the updated params list: replace matching param values,
        # then add new params for names that don't exist on the node yet.
        existing_params = list(node.params)
        updated_params: list[Param] = []
        updated_param_names: set[str] = set()

        for p in existing_params:
            if p.name in param_updates:
                # Update ONLY the value, preserving the existing param's other fields
                # (type_token, default, and critically `ref`/`description` since issue
                # #116). Rebuilding a fresh Param field-by-field here would silently
                # drop a graph-parameter `ref` -- severing the author's graph-param
                # wiring on an agent-proposed value edit (issue #116 interaction).
                updated_params.append(p.model_copy(update={"value": param_updates[p.name]}))
                updated_param_names.add(p.name)
            else:
                updated_params.append(p)

        for param_name, new_value in param_updates.items():
            if param_name not in updated_param_names:
                updated_params.append(
                    Param(
                        name=param_name,
                        type_token="any",
                        value=new_value,
                        default=None,
                    )
                )

        candidate = node.model_copy(update={"params": updated_params})

        if definition_cls is not None:
            errors = definition_cls().validate_node(candidate)
            if errors:
                raise MutationError(f"{node_id}: {'; '.join(errors)}")

        new_nodes[node_id] = candidate

    # ------------------------------------------------------------------
    # 4. Final construction — Graph structural validation runs here
    # ------------------------------------------------------------------
    try:
        result = Graph(
            schema_version=graph.schema_version,
            paradigm=graph.paradigm,
            name=graph.name,
            nodes=new_nodes,
            edges=new_edges,
            params=graph.params,
        )
    except ValidationError as exc:
        raise MutationError(str(exc)) from exc

    return result


def invert_mutation(graph: Graph, m: GraphMutation) -> GraphMutation:
    """Derive the inverse of *m* against *graph*.

    Returns a new GraphMutation that, when applied to apply_mutation(graph, m),
    returns a graph equivalent to the original *graph*.

    The inverse swaps adds/removes and restores original param values.

    Raises
    ------
    MutationError
        If a removed node/edge does not exist in *graph* (cannot invert).
    """
    # Inverse of add_nodes: remove them
    inverse_remove_nodes = [node.id for node in m.add_nodes]

    # Inverse of add_edges: remove them
    inverse_remove_edges = [edge.id for edge in m.add_edges]

    # Inverse of remove_nodes: add them back (need original nodes from graph)
    inverse_add_nodes: list[Node] = []
    for node_id in m.remove_nodes:
        if node_id not in graph.nodes:
            raise MutationError(
                f"Cannot invert remove_nodes: node {node_id!r} does not exist in the graph."
            )
        inverse_add_nodes.append(graph.nodes[node_id])

    # Inverse of remove_edges: add them back (need original edges from graph)
    inverse_add_edges: list[Edge] = []
    for edge_id in m.remove_edges:
        if edge_id not in graph.edges:
            raise MutationError(
                f"Cannot invert remove_edges: edge {edge_id!r} does not exist in the graph."
            )
        inverse_add_edges.append(graph.edges[edge_id])

    # Inverse of set_params: restore original param values
    inverse_set_params: dict[str, dict[str, ParamValue]] = {}
    for node_id, param_updates in m.set_params.items():
        if node_id not in graph.nodes:
            raise MutationError(
                f"Cannot invert set_params: node {node_id!r} does not exist in the graph."
            )
        original_node = graph.nodes[node_id]
        original_present = {p.name for p in original_node.params}
        original_values: dict[str, ParamValue] = {}
        for param_name in param_updates:
            if param_name not in original_present:
                raise MutationError(
                    f"Cannot invert set_params: param {param_name!r} on node {node_id!r} "
                    "did not exist in the original graph. The graph-mutation protocol has no "
                    "way to express removing a param, so this forward mutation is not "
                    "invertible."
                )
            # Find the original param value
            for param in original_node.params:
                if param.name == param_name:
                    original_values[param_name] = param.value
                    break
        inverse_set_params[node_id] = original_values

    return GraphMutation(
        base_version=m.base_version,
        add_nodes=inverse_add_nodes,
        add_edges=inverse_add_edges,
        remove_nodes=inverse_remove_nodes,
        remove_edges=inverse_remove_edges,
        set_params=inverse_set_params,
        description=f"Inverse of: {m.description}" if m.description else "Inverse mutation",
        author=m.author,
    )


def propose_diagnostics(graph: Graph, m: GraphMutation) -> Diagnostics:
    """Validate-on-propose: apply *m* to *graph* and validate the result.

    Returns ``ef.validate(apply_mutation(graph, m))`` -- the Diagnostics of the
    graph *after* the mutation would be applied, so the canvas can show "this
    proposal type-checks" before a human accepts it. If *m* itself cannot be
    applied (a MutationError -- e.g. it removes a nonexistent node, or a param
    update is rejected by the node's own contract), that failure is folded into
    the SAME Diagnostics shape as a single error-severity diagnostic (code
    "mutation_error") rather than raised, so one call always yields everything
    the canvas needs to show -- a caller never has to catch two different
    failure shapes to render one verdict.
    """
    try:
        mutated = apply_mutation(graph, m)
    except MutationError as exc:
        return Diagnostics(
            diagnostics=[
                Diagnostic(
                    severity=Severity.ERROR,
                    code="mutation_error",
                    message=str(exc),
                )
            ]
        )
    return run_validate(mutated)
