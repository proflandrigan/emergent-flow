"""
colonymind.codegen.wiring
~~~~~~~~~~~~~~~~~~~~~~~~~~~
The input-wiring map for the code-generation engine (Epic 2, Story 2).

`compile_to_code` (Story 5) and `execute` (Story 6) both need to know, for every
IN port of every node, which upstream OUT port(s) feed it. This module resolves
that from the graph's edges into a `WiringMap`: one `InputBinding` per IN port,
carrying the upstream `PortRef`(s).

Three shapes are handled:

* **fan-in** — an IN port with `Cardinality.MANY` may have several upstream
  sources; an IN port with `Cardinality.ONE` fed by more than one edge is a
  `CardinalityError`.
* **fan-out** — one OUT port feeding many IN ports; resolved via `consumers()`.
* **dangling** — an IN port with no incoming edge is recorded with an empty
  `sources` list (`is_bound` is False). This is deliberately not an error here.

The map is deterministic: bindings are ordered by ascending target node id then
port order, and each binding's sources are ordered by `(node_id, port_id)`, so
the same graph always produces an identical map (needed for golden tests and the
ADR-0002 equivalence invariant).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from colonymind.api import public_op
from colonymind.codegen.errors import CardinalityError
from colonymind.ir.common import Cardinality, Direction
from colonymind.ir.edge import PortRef
from colonymind.ir.graph import Graph
from colonymind.ir.node import Node


def _describe_node(node: Node) -> str:
    """Human-readable identifier for a node in error messages."""
    label = (node.label or "").strip()
    if label:
        return f"{label!r} (id={node.id})"
    return f"{node.type!r} (id={node.id})"


class InputBinding(BaseModel):
    """Resolved wiring for a single IN port.

    Attributes
    ----------
    target:
        The IN endpoint this binding describes (its node + port).
    sources:
        The upstream OUT endpoints feeding this IN port. Empty means the port is
        dangling (no incoming edge). More than one is fan-in (only allowed when
        the IN port's cardinality is MANY).
    """

    target: PortRef
    sources: list[PortRef] = Field(default_factory=list)

    @property
    def is_bound(self) -> bool:
        """True if at least one upstream source feeds this IN port."""
        return bool(self.sources)


class WiringMap(BaseModel):
    """The whole-graph input-wiring map: one `InputBinding` per IN port.

    The serializable surface is the `bindings` list; fast lookups are served by
    private indexes rebuilt automatically after construction or deserialization.
    """

    bindings: list[InputBinding] = Field(default_factory=list)

    _by_target: dict[tuple[str, str], InputBinding] = PrivateAttr(default_factory=dict)
    _by_source: dict[tuple[str, str], list[PortRef]] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Build the (node_id, port_id) lookup indexes from `bindings`."""
        self._by_target = {}
        self._by_source = {}
        for binding in self.bindings:
            self._by_target[(binding.target.node_id, binding.target.port_id)] = binding
            for src in binding.sources:
                self._by_source.setdefault((src.node_id, src.port_id), []).append(binding.target)

    def upstream(self, node_id: str, port_id: str) -> list[PortRef]:
        """Return the upstream OUT endpoints feeding the given IN port.

        Returns an empty list for a dangling IN port. Raises `KeyError` if the
        (node_id, port_id) is not a known IN port in this map.
        """
        key = (node_id, port_id)
        if key not in self._by_target:
            raise KeyError(f"No IN port {port_id!r} on node {node_id!r} in this wiring map.")
        # Return a copy so callers cannot mutate the map's internal binding state
        # (kept consistent with consumers(), which also returns a fresh list).
        return list(self._by_target[key].sources)

    def is_bound(self, node_id: str, port_id: str) -> bool:
        """True if the given IN port has at least one upstream source."""
        return bool(self.upstream(node_id, port_id))

    def consumers(self, node_id: str, port_id: str) -> list[PortRef]:
        """Return the IN endpoints fed by the given OUT port (fan-out).

        Returns an empty list if nothing consumes the port.
        """
        return list(self._by_source.get((node_id, port_id), []))


@public_op(name="cm.codegen.build_wiring_map")
def build_wiring_map(graph: Graph) -> WiringMap:
    """Resolve *graph*'s edges into a deterministic `WiringMap`.

    Builds one `InputBinding` for every IN port of every node. Dangling IN ports
    (no incoming edge) get an empty `sources` list. An IN port with cardinality
    ONE fed by more than one edge raises `CardinalityError`.
    """
    # Gather incoming OUT endpoints per (target node id, target port id).
    # Sources are kept per edge and NOT de-duplicated: two parallel edges from the
    # same OUT port to the same IN port yield two identical PortRefs, mirroring the
    # per-edge counting in topological_sort. A consumer that needs distinct sources
    # de-dupes itself (Story 5/6).
    incoming: dict[tuple[str, str], list[PortRef]] = {}
    for edge in graph.edges.values():
        key = (edge.target.node_id, edge.target.port_id)
        incoming.setdefault(key, []).append(
            PortRef(node_id=edge.source.node_id, port_id=edge.source.port_id)
        )

    bindings: list[InputBinding] = []
    # Iterate nodes by ascending id, ports in declared order, for a stable map.
    for node in sorted(graph.nodes.values(), key=lambda n: n.id):
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            sources = incoming.get((node.id, port.id), [])
            if port.cardinality == Cardinality.ONE and len(sources) > 1:
                raise CardinalityError(
                    f"IN port {port.name!r} on node {_describe_node(node)} has "
                    f"cardinality ONE but is fed by {len(sources)} incoming edges; "
                    "only one is allowed. Declare the port Cardinality.MANY to allow "
                    "fan-in."
                )
            ordered = sorted(sources, key=lambda ref: (ref.node_id, ref.port_id))
            bindings.append(
                InputBinding(
                    target=PortRef(node_id=node.id, port_id=port.id),
                    sources=ordered,
                )
            )

    return WiringMap(bindings=bindings)
