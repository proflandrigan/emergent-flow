"""
emergentflow.codegen.composite
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared seam for `layout.composite` nodes (issue #117 stage 3): both `execute`
(`emergentflow.codegen.executor`) and `compile_to_code` (`emergentflow.codegen.compiler`)
recursively delegate to a composite node's `subgraph` through the boundary this module
resolves, so ADR-0002 equivalence holds by construction — both paths walk the identical
subgraph and bind the identical boundary ports, in the identical canonical order.

A composite's IN ports correspond, in a fixed canonical order, to its subgraph's *dangling* IN
ports (no internal upstream source); its OUT ports correspond to its subgraph's OUT ports with
no internal consumer ("exposed" outputs). The canonical order is: subgraph nodes sorted by id,
each node's ports in their declared order — the same node-then-port ordering
`emergentflow.codegen.wiring.build_wiring_map` already uses for its own bindings, so this module
introduces no new ordering convention. Whoever builds a composite node (the canvas's "Extract to
composite" action) must populate `Node.ports` in that same order for the mapping to line up;
`resolve_composite_boundary` is the single source of truth both sides read from.
"""

from __future__ import annotations

from dataclasses import dataclass

from emergentflow.ir import Direction, Graph, PortRef

from .wiring import WiringMap, build_wiring_map

COMPOSITE_NODE_TYPE = "layout.composite"


@dataclass(frozen=True)
class CompositeBoundary:
    """The canonical mapping between a composite's own ports and its subgraph's boundary."""

    subgraph: Graph
    wiring: WiringMap
    # Dangling IN ports, in canonical order -- position i is the composite node's i-th
    # declared IN port (in `node.ports`, filtered to IN, in list order).
    dangling_in: list[PortRef]
    # Exposed OUT ports, in canonical order -- position i is the composite node's i-th
    # declared OUT port (in `node.ports`, filtered to OUT, in list order).
    exposed_out: list[PortRef]


def resolve_composite_boundary(subgraph: Graph) -> CompositeBoundary:
    """Resolve *subgraph*'s dangling IN ports and exposed OUT ports, in canonical order.

    Canonical order: subgraph nodes sorted by id, each node's ports in their declared order.
    """
    wiring = build_wiring_map(subgraph)
    dangling_in: list[PortRef] = []
    exposed_out: list[PortRef] = []
    for node in sorted(subgraph.nodes.values(), key=lambda n: n.id):
        for port in node.ports:
            ref = PortRef(node_id=node.id, port_id=port.id)
            if port.direction == Direction.IN:
                if not wiring.is_bound(node.id, port.id):
                    dangling_in.append(ref)
            else:
                if not wiring.consumers(node.id, port.id):
                    exposed_out.append(ref)
    return CompositeBoundary(
        subgraph=subgraph,
        wiring=wiring,
        dangling_in=dangling_in,
        exposed_out=exposed_out,
    )
