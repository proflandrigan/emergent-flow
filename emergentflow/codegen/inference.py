"""
emergentflow.codegen.inference
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Whole-graph type inference (Epic 3, Story 4).

`NodeDefinition.infer_types` resolves the data-type token each node produces on
its OUT ports, but nothing calls it across a whole graph. This module provides
the pass that does: it walks the IR in deterministic topological order (reusing
`emergentflow.codegen.traversal.topological_sort`), threads each node's resolved
OUT-port types into the IN ports they feed (via
`emergentflow.codegen.wiring.build_wiring_map`), and calls each node's
`infer_types`. The result is a resolved-type map the Story 5 validation pass
consumes to check edge compatibility against *propagated* types, not just
declared ones.

The pass is **pure** and deterministic: it reads the node registry passed to it
explicitly (no global lookup, no I/O), so it can feed golden tests and ship to
the frontend as data — the same purity constraint the rest of Epic 3 keeps.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from emergentflow.api import public_op
from emergentflow.codegen.traversal import topological_sort
from emergentflow.codegen.wiring import build_wiring_map
from emergentflow.ir import Direction, Graph
from emergentflow.nodes import NodeRegistry
from emergentflow.nodes import registry as default_node_registry
from emergentflow.types.registry import TOP_TYPE


class ResolvedPortType(BaseModel):
    """The inferred data-type token produced on a single OUT port.

    Attributes:
        node_id: Id of the node owning the OUT port.
        port_id: Id of the OUT port.
        port_name: Name of the OUT port (its `Port.name`).
        type: The resolved data-type token produced on the port.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    port_id: str
    port_name: str
    type: str


class UnboundInput(BaseModel):
    """An IN port with no upstream source feeding it (a dangling input).

    Recorded rather than raised: an exploratory, half-wired graph is allowed to
    have dangling IN ports. The Story 5 validation pass decides severity.

    Attributes:
        node_id: Id of the node owning the IN port.
        port_id: Id of the IN port.
        port_name: Name of the IN port (its `Port.name`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    port_id: str
    port_name: str


class InferenceResult(BaseModel):
    """The output of the whole-graph inference pass.

    Attributes:
        resolved: One `ResolvedPortType` per OUT port across the graph.
        unbound: One `UnboundInput` per IN port that had no upstream source.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    resolved: list[ResolvedPortType] = Field(default_factory=list)
    unbound: list[UnboundInput] = Field(default_factory=list)

    # `resolved` stays the serializable wire surface; a private (node_id, port_id)
    # index is rebuilt after construction/deserialization so `type_of` is O(1),
    # mirroring how `WiringMap` indexes its `bindings` list (wiring.py). The Story
    # 5 validation pass calls `type_of` once per edge, so the index matters.
    _by_port: dict[tuple[str, str], str] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Build the (node_id, port_id) -> resolved-token index from `resolved`."""
        self._by_port = {(r.node_id, r.port_id): r.type for r in self.resolved}

    def type_of(self, node_id: str, port_id: str) -> str | None:
        """Return the resolved token for an OUT port, or None if not resolved."""
        return self._by_port.get((node_id, port_id))


def _reduce_inbound_types(tokens: list[str]) -> str:
    """Reduce the type tokens of several inbound edges to a single IN-port token.

    `NodeDefinition.infer_types` takes one token per IN-port name, but a
    `Cardinality.MANY` fan-in port can have several upstream sources. The rule
    (Story 4): if every inbound source resolves to the same token, use it;
    otherwise the inbound types disagree and we fall back to the wildcard
    `"any"` (the top type), which is compatible with anything downstream.

    `tokens` is assumed non-empty (an unbound IN port is handled separately and
    never reaches here). Deterministic: the result depends only on the set of
    tokens, not their order.

    Args:
        tokens: The resolved type tokens of the inbound edges (one per edge).

    Returns:
        The single token feeding the IN port: the common token if uniform, else
        `TOP_TYPE`.
    """
    unique = set(tokens)
    if len(unique) == 1:
        return next(iter(unique))
    return TOP_TYPE


@public_op(name="ef.codegen.infer_graph_types")
def infer_graph_types(
    graph: Graph,
    *,
    node_registry: NodeRegistry = default_node_registry,
) -> InferenceResult:
    """Resolve the data-type token on every OUT port of *graph*.

    Walks the graph in deterministic topological order. For each node, the
    resolved tokens of its inbound edges are reduced (per IN-port name) and
    passed to the node definition's `infer_types`; the returned OUT-port tokens
    are recorded and become the inputs of downstream nodes. An IN port with no
    inbound edge is recorded in `unbound` rather than raising — exploratory,
    half-wired graphs are allowed (the Story 5 validation pass decides severity).

    Pure and deterministic: the *node_registry* is passed in explicitly (it
    defaults to the package singleton) and there is no I/O, so the pass can feed
    golden tests and run client-side-equivalently. A node whose `type` is not in
    the registry falls back to its declared OUT-port `data_type` tokens.

    Args:
        graph: The functional-pipeline graph to infer types over.
        node_registry: The node registry used to resolve each node's definition
            (and thus its `infer_types`). Defaults to the package singleton.

    Returns:
        An `InferenceResult` with one `ResolvedPortType` per OUT port and one
        `UnboundInput` per dangling IN port.
    """
    wiring = build_wiring_map(graph)
    order = topological_sort(graph)

    # Resolved OUT-port tokens keyed by (node_id, port_id), threaded downstream.
    resolved_map: dict[tuple[str, str], str] = {}
    resolved: list[ResolvedPortType] = []
    unbound: list[UnboundInput] = []

    for node_id in order:
        node = graph.nodes[node_id]
        in_ports = [p for p in node.ports if p.direction == Direction.IN]
        out_ports = [p for p in node.ports if p.direction == Direction.OUT]

        # Build input_types keyed by IN-port name from resolved upstream OUT types.
        input_types: dict[str, str] = {}
        for port in in_ports:
            sources = wiring.upstream(node_id, port.id)
            if not sources:
                unbound.append(UnboundInput(node_id=node_id, port_id=port.id, port_name=port.name))
                continue
            tokens = [resolved_map.get((s.node_id, s.port_id), TOP_TYPE) for s in sources]
            input_types[port.name] = _reduce_inbound_types(tokens)

        # Resolve the node definition and infer its OUT-port tokens.
        definition_cls = node_registry.try_get(node.type)
        if definition_cls is not None:
            out_types = definition_cls().infer_types(node, input_types)
        else:
            out_types = {p.name: p.data_type for p in out_ports}

        for port in out_ports:
            # `.get(..., declared)` covers two cases: a registered node whose
            # `infer_types` omits an OUT-port name, and (redundantly but harmlessly)
            # the unregistered branch above, which already declared every name.
            token = out_types.get(port.name, port.data_type)
            resolved_map[(node_id, port.id)] = token
            resolved.append(
                ResolvedPortType(
                    node_id=node_id,
                    port_id=port.id,
                    port_name=port.name,
                    type=token,
                )
            )

    return InferenceResult(resolved=resolved, unbound=unbound)
