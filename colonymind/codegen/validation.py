"""
colonymind.codegen.validation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Graph validation pass & diagnostics (Epic 3, Story 5).

`validate(graph)` runs whole-graph type inference (Story 4) then checks every
edge with the rules engine (Story 3), plus the structural cardinality and
required-IN checks, and returns `Diagnostics` — the JSON-native result the
frontend renders directly: a list of `Diagnostic` findings plus a per-edge
compatibility map. It is deliberately a *separate* call from `Graph`'s
construction-time structural validation, so it never blocks building exploratory,
half-wired graphs. All result models are `frozen=True, extra="forbid"`, mirroring
the rules-engine result models in `colonymind.types.compatibility`, so they are
stable for golden tests. `apply_type_compatibility` records the per-edge verdicts
onto a copy of the graph's `Edge.type_compatible` fields.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from colonymind.api import public_op
from colonymind.codegen.errors import CardinalityError
from colonymind.codegen.inference import infer_graph_types
from colonymind.ir import Direction, Graph, Port
from colonymind.nodes import NodeRegistry
from colonymind.nodes import registry as default_node_registry
from colonymind.types.compatibility import Compatibility, check_cardinality, is_compatible
from colonymind.types.registry import TypeRegistry
from colonymind.types.registry import registry as default_type_registry


class Severity(str, Enum):
    """Severity of a single validation diagnostic (Story 5)."""

    ERROR = "error"
    WARNING = "warning"


class Diagnostic(BaseModel):
    """A single structured validation finding.

    Attributes:
        severity: error (hard problem) or warning (runtime-only-knowable).
        code: machine-readable code, e.g. "type_incompatible".
        message: human-readable explanation (the canvas's "why" tooltip text).
        edge_id: the offending edge id, when the finding is about an edge.
        node_id: the node id, when the finding is about a port.
        port_id: the port id, when the finding is about a port.
        port_name: the port name, when the finding is about a port.
        expected_type: the type the target IN port expected, for type findings.
        actual_type: the type the source OUT port produced, for type findings.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    severity: Severity
    code: str
    message: str
    edge_id: str | None = None
    node_id: str | None = None
    port_id: str | None = None
    port_name: str | None = None
    expected_type: str | None = None
    actual_type: str | None = None


class Diagnostics(BaseModel):
    """The result of `validate`: every finding plus the per-edge verdict map.

    Attributes:
        diagnostics: every `Diagnostic` produced for the graph.
        edge_compatibility: per-edge-id verdict — True (compatible),
            False (incompatible), or None (unknown / not type-checked). This is
            the source for `Edge.type_compatible` (see `apply_type_compatibility`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    diagnostics: list[Diagnostic] = Field(default_factory=list)
    edge_compatibility: dict[str, bool | None] = Field(default_factory=dict)

    @property
    def errors(self) -> list[Diagnostic]:
        """All error-severity diagnostics."""
        return [d for d in self.diagnostics if d.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        """All warning-severity diagnostics."""
        return [d for d in self.diagnostics if d.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        """True when there are no error-severity diagnostics."""
        return not self.errors


def _collect_structural_diagnostics(
    graph: Graph,
    node_registry: NodeRegistry,
) -> list[Diagnostic]:
    """Collect structural diagnostics: cardinality violations and unconnected
    required IN ports.

    Pure: counts inbound edges per IN port directly from `graph.edges` (so it
    never raises the way the codegen wiring map does), and reads each node
    definition's `PortSpec.required` from the registry. A node whose type is not
    registered contributes no required-input check (its required-ness is
    unknown).
    """
    diagnostics: list[Diagnostic] = []

    # Count inbound edges per (target node id, target port id).
    inbound_count: dict[tuple[str, str], int] = {}
    for edge in graph.edges.values():
        key = (edge.target.node_id, edge.target.port_id)
        inbound_count[key] = inbound_count.get(key, 0) + 1

    for node in graph.nodes.values():
        # Names of this node type's required IN ports, when the type is registered.
        definition_cls = node_registry.try_get(node.type)
        required_in_names: set[str] = set()
        if definition_cls is not None:
            for spec in definition_cls.ports:
                if spec.direction == Direction.IN and spec.required:
                    required_in_names.add(spec.name)

        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            count = inbound_count.get((node.id, port.id), 0)

            # Cardinality: a Cardinality.ONE IN port fed by >1 edge is an error.
            card = check_cardinality(port.cardinality, count, port_name=port.name)
            if not card.ok:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="cardinality_violation",
                        message=card.reason,
                        node_id=node.id,
                        port_id=port.id,
                        port_name=port.name,
                    )
                )

            # Required IN port with no inbound edge is an error.
            if count == 0 and port.name in required_in_names:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="required_input_unconnected",
                        message=(
                            f"required IN port {port.name!r} on node {node.id!r} "
                            "has no inbound edge"
                        ),
                        node_id=node.id,
                        port_id=port.id,
                        port_name=port.name,
                    )
                )

    return diagnostics


def _collect_type_diagnostics(
    graph: Graph,
    node_registry: NodeRegistry,
    type_registry: TypeRegistry,
) -> tuple[list[Diagnostic], dict[str, bool | None]]:
    """Collect per-edge type-compatibility diagnostics and the verdict map.

    Runs the Story 4 inference pass (so checks see *propagated* types), then
    checks every edge with the Story 3 rules engine. INCOMPATIBLE -> error,
    UNKNOWN -> warning, COMPATIBLE -> no diagnostic. The returned map records
    True / False / None per edge id (the source for `Edge.type_compatible`).

    Catch-and-degrade: inference calls the codegen wiring map, which raises
    `CardinalityError` when a `Cardinality.ONE` IN port has >1 inbound edges.
    That is already reported by `_collect_structural_diagnostics`, so here we
    catch it and return no type diagnostics rather than crash.
    """
    diagnostics: list[Diagnostic] = []
    edge_compatibility: dict[str, bool | None] = {}

    # (node_id, port_id) -> Port, for resolving source/target type tokens.
    ports: dict[tuple[str, str], Port] = {}
    for node in graph.nodes.values():
        for port in node.ports:
            ports[(node.id, port.id)] = port

    try:
        inference = infer_graph_types(graph, node_registry=node_registry)
    except CardinalityError:
        return diagnostics, edge_compatibility

    for edge_id, edge in graph.edges.items():
        source_port = ports.get((edge.source.node_id, edge.source.port_id))
        target_port = ports.get((edge.target.node_id, edge.target.port_id))
        if source_port is None or target_port is None:
            continue  # Graph guarantees endpoints exist; stay defensive anyway.

        # Resolved source token, falling back to the declared OUT data_type.
        source_type = (
            inference.type_of(edge.source.node_id, edge.source.port_id) or source_port.data_type
        )
        target_type = target_port.data_type
        result = is_compatible(source_type, target_type, registry=type_registry)

        if result.verdict == Compatibility.COMPATIBLE:
            edge_compatibility[edge_id] = True
            continue
        if result.verdict == Compatibility.INCOMPATIBLE:
            edge_compatibility[edge_id] = False
            severity, code = Severity.ERROR, "type_incompatible"
        else:  # Compatibility.UNKNOWN
            edge_compatibility[edge_id] = None
            severity, code = Severity.WARNING, "type_unknown"

        diagnostics.append(
            Diagnostic(
                severity=severity,
                code=code,
                message=result.reason,
                edge_id=edge_id,
                node_id=edge.target.node_id,
                port_id=edge.target.port_id,
                port_name=target_port.name,
                expected_type=target_type,
                actual_type=source_type,
            )
        )

    return diagnostics, edge_compatibility


@public_op(name="cm.validate")
def validate(
    graph: Graph,
    *,
    node_registry: NodeRegistry = default_node_registry,
    type_registry: TypeRegistry = default_type_registry,
) -> Diagnostics:
    """Validate *graph*'s wiring and return structured diagnostics (Story 5).

    Runs whole-graph type inference (Story 4) then checks every edge with the
    rules engine (Story 3), and adds the structural checks (cardinality, required
    IN ports). The result is JSON-native so the canvas renders it directly.

    This is deliberately a *separate* call from `Graph`'s construction-time
    structural validation: type/cardinality validation must NOT block building
    exploratory, half-wired graphs, so those can exist on the canvas and still be
    inspected. Pure and deterministic — both registries are passed in explicitly
    (defaulting to the package singletons) and there is no I/O or argument
    mutation, so the same call can gate codegen/execution (Story 6) and ship to
    the frontend. To record the per-edge verdicts onto `Edge.type_compatible`,
    pass the result to `apply_type_compatibility`.

    Args:
        graph: The graph to validate.
        node_registry: Node registry resolving each node's definition (for
            `infer_types` and required-port specs). Defaults to the singleton.
        type_registry: Type registry resolving registration and subtype facts.
            Defaults to the singleton.

    Returns:
        A `Diagnostics` with every finding plus the per-edge compatibility map.
    """
    structural = _collect_structural_diagnostics(graph, node_registry)
    type_diagnostics, edge_compatibility = _collect_type_diagnostics(
        graph, node_registry, type_registry
    )
    return Diagnostics(
        diagnostics=structural + type_diagnostics,
        edge_compatibility=edge_compatibility,
    )


@public_op(name="cm.apply_type_compatibility")
def apply_type_compatibility(graph: Graph, diagnostics: Diagnostics) -> Graph:
    """Return a copy of *graph* with `Edge.type_compatible` populated.

    Pure: the input *graph* is not mutated. A deep copy is made, then each edge's
    `type_compatible` is set from *diagnostics*' per-edge verdict map
    (`True` compatible, `False` incompatible, `None` unknown). Edges absent from
    the map (e.g. when type checks were skipped) keep their existing value. This
    fulfils the `Edge.type_compatible` field Epic 1 reserved (Story 5), without
    `validate` itself having any side effect.

    Args:
        graph: The graph whose edges should carry the verdicts.
        diagnostics: The result of `validate(graph)` for the same graph.

    Returns:
        A new `Graph` (deep copy) with `Edge.type_compatible` populated.
    """
    updated = graph.model_copy(deep=True)
    for edge_id, edge in updated.edges.items():
        if edge_id in diagnostics.edge_compatibility:
            edge.type_compatible = diagnostics.edge_compatibility[edge_id]
    return updated
