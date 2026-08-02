"""
emergentflow.codegen.validation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Graph validation pass & diagnostics (Epic 3, Story 5).

`validate(graph)` runs whole-graph type inference (Story 4) then checks every
edge with the rules engine (Story 3), plus the structural cardinality and
required-IN checks, and returns `Diagnostics` — the JSON-native result the
frontend renders directly: a list of `Diagnostic` findings plus a per-edge
compatibility map. It is deliberately a *separate* call from `Graph`'s
construction-time structural validation, so it never blocks building exploratory,
half-wired graphs. All result models are `frozen=True, extra="forbid"`, mirroring
the rules-engine result models in `emergentflow.types.compatibility`, so they are
stable for golden tests. `apply_type_compatibility` records the per-edge verdicts
onto a copy of the graph's `Edge.type_compatible` fields.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from emergentflow.api import public_op
from emergentflow.codegen.errors import CardinalityError, GraphValidationError
from emergentflow.codegen.inference import infer_graph_types
from emergentflow.ir import Direction, Graph, IRId, Node, Port
from emergentflow.nodes import NodeRegistry
from emergentflow.nodes import registry as default_node_registry
from emergentflow.types.compatibility import Compatibility, check_cardinality, is_compatible
from emergentflow.types.registry import TypeRegistry
from emergentflow.types.registry import registry as default_type_registry


class Severity(str, Enum):
    """Severity of a single validation diagnostic (Story 5; INFO added Epic 14 Story 6 for
    agent review comments that aren't errors or warnings)."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


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
        source: who produced this finding -- "validator" (ef.validate itself) or a persona
            slug (an agent's review comment, Epic 14 Story 6). None for pre-Story-6 callers
            that never set it.
        rule_id: the machine-readable id of the validity rule that produced this
            finding, when it came from the experiment-validity engine.
        related_node_ids: other nodes implicated alongside ``node_id``, for
            findings about a relationship between two nodes (e.g. a transform
            fitted upstream of a split).
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
    source: str | None = None
    rule_id: str | None = None
    related_node_ids: list[str] = Field(default_factory=list)


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


def required_in_port_names(node_type: str, node_registry: NodeRegistry) -> set[str]:
    """Names of *node_type*'s required IN ports, per its registered `PortSpec`s.

    Returns an empty set when *node_type* isn't registered -- its required-ness
    is unknown, so no port of an unregistered type is treated as required here.
    Shared by `_collect_structural_diagnostics` and the codegen/executor
    dangling-input guards, so all three agree on which unconnected IN ports are
    actually errors (ADR 0002 extends to rejection).
    """
    definition_cls = node_registry.try_get(node_type)
    if definition_cls is None:
        return set()
    return {
        spec.name
        for spec in definition_cls.ports
        if spec.direction == Direction.IN and spec.required
    }


def _collect_structural_diagnostics(
    graph: Graph,
    node_registry: NodeRegistry,
) -> list[Diagnostic]:
    """Collect structural diagnostics: cardinality violations and unconnected
    required IN ports.

    Pure: counts inbound edges per IN port directly from `graph.edges` (so it
    never raises the way the codegen wiring map does), and reads each node
    definition's `PortSpec.required` from the registry via
    `required_in_port_names`. A node whose type is not registered contributes no
    required-input check (its required-ness is unknown).

    Deterministic: nodes are visited in ascending node-id order (ports are
    already in declared list order), mirroring `wiring.py`'s tie-break, so the
    same graph always yields the same diagnostics order regardless of dict
    insertion order.
    """
    diagnostics: list[Diagnostic] = []

    # Count inbound edges per (target node id, target port id).
    inbound_count: dict[tuple[str, str], int] = {}
    for edge in graph.edges.values():
        key = (edge.target.node_id, edge.target.port_id)
        inbound_count[key] = inbound_count.get(key, 0) + 1

    for node in sorted(graph.nodes.values(), key=lambda n: n.id):
        required_in_names = required_in_port_names(node.type, node_registry)

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


def _collect_param_diagnostics(
    graph: Graph,
    node_registry: NodeRegistry,
) -> list[Diagnostic]:
    """Collect per-node param-value diagnostics from each node definition's own contract.

    Delegates to `NodeDefinition.validate_param_values`, which applies every
    `ValidationHints` constraint (choices, numeric min/max, string/list length, regex) to
    the params a node actually carries. Those checks already existed but had no caller
    outside tests, so a param value that a node's contract forbids -- most visibly a
    `choices` entry that a node version has since dropped, e.g. an `ml.cluster_detect` node
    still naming an estimator that moved to the `ml.outlier_detect` archetype -- reached
    `execute` and failed there instead of surfacing on the canvas as a diagnostic on the
    offending node.

    Scoped to param *values* on purpose: a missing required param means "not configured
    yet", which must stay valid so half-built graphs remain inspectable (see this module's
    docstring). See `validate_param_values` for that split.

    A node whose type is not registered contributes nothing (its contract is unknown),
    mirroring `required_in_port_names`.

    Deterministic: nodes are visited in ascending node-id order, and messages come back in
    the node's own param order, so the same graph always yields the same diagnostics order.
    """
    diagnostics: list[Diagnostic] = []

    for node in sorted(graph.nodes.values(), key=lambda n: n.id):
        definition_cls = node_registry.try_get(node.type)
        if definition_cls is None:
            continue
        for message in definition_cls().validate_param_values(node):
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="param_invalid",
                    message=f"node {node.id!r} ({node.type}): {message}",
                    node_id=node.id,
                )
            )

    return diagnostics


def _param_token_compatible(source_type: str, target_type: str) -> bool:
    """True when a graph-param *source_type* token can feed a node-param *target_type* token.

    Param ``type_token`` labels (``"str"``, ``"int"``, ``"list[str]"``, ...) are NOT registered
    in the port ``data_type`` type registry (that registry only knows port tokens like
    ``"DataFrame"``), so ``is_compatible`` cannot judge them. This is the small, deterministic
    rule: equal tokens, the ``"any"`` wildcard on either side, and the safe numeric widening
    ``int -> float`` are compatible; everything else is a mismatch (issue #116).
    """
    if source_type == target_type or source_type == "any" or target_type == "any":
        return True
    return source_type == "int" and target_type == "float"


def _collect_param_ref_diagnostics(
    graph: Graph,
    node_registry: NodeRegistry,
) -> list[Diagnostic]:
    """Collect diagnostics for node params that ``ref`` a graph-level parameter (issue #116).

    A ``ref`` must name a graph-level param (``ref_unresolved``), the referenced graph param's
    ``type_token`` must be compatible with the node param's declared ``type_token``
    (``ref_type_mismatch``), and the node's codegen must support refs on that param
    (``ref_not_supported``).

    Composite subgraphs are walked recursively, and every ref at every nesting level resolves
    against the TOP graph's params map: ``materialize_graph`` resolves subgraph refs against the
    enclosing graph's params (see ``emergentflow.codegen.params``), and ``_codegen_composite``
    compiles subgraph refs against the enclosing graph's ``main()`` kwargs -- so the gate must
    validate them against the same map, or a subgraph ref that compile rejects with ``KeyError``
    (``_param_expr_refs``) and that execute rejects with ``GraphParamError`` would slip through
    ``validate`` entirely (ADR 0002 equivalence extends to rejection).

    Deterministic: nodes in ascending node-id order (subgraph nodes visited within their owning
    composite's visit), params in declared order, mirroring ``_collect_param_diagnostics``.
    """
    diagnostics: list[Diagnostic] = []

    def _visit(nodes: dict[IRId, Node]) -> None:
        for node in sorted(nodes.values(), key=lambda n: n.id):
            if node.subgraph is not None:
                _visit(node.subgraph.nodes)
            definition_cls = node_registry.try_get(node.type)
            specs = (
                {ps.name: ps for ps in definition_cls.params} if definition_cls is not None else {}
            )

            for param in node.params:
                if param.ref is None:
                    continue
                ref = param.ref
                graph_param = graph.params.get(ref)
                if graph_param is None:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="ref_unresolved",
                            message=(
                                f"node {node.id!r} ({node.type}) param {param.name!r} "
                                f"references graph parameter {ref!r} which is not defined"
                            ),
                            node_id=node.id,
                        )
                    )
                    continue

                spec = specs.get(param.name)
                if spec is None or spec.hints is None or not spec.hints.ref_supported:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="ref_not_supported",
                            message=(
                                f"node {node.id!r} ({node.type}) param {param.name!r} "
                                f"references graph parameter {ref!r} but this node's codegen "
                                "does not support graph-parameter references"
                            ),
                            node_id=node.id,
                        )
                    )
                    continue

                result = _param_token_compatible(graph_param.type_token, spec.type_token)
                if result:
                    continue
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="ref_type_mismatch",
                        message=(
                            f"node {node.id!r} ({node.type}) param {param.name!r} references "
                            f"graph parameter {ref!r} with type token "
                            f"{graph_param.type_token!r} which is "
                            f"incompatible with the param's declared type token {spec.type_token!r}"
                        ),
                        node_id=node.id,
                        expected_type=spec.type_token,
                        actual_type=graph_param.type_token,
                    )
                )

    _visit(graph.nodes)
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

    Deterministic: edges are visited in ascending edge-id order so the same
    graph always yields the same diagnostics order regardless of dict
    insertion order (mirroring `wiring.py`'s tie-break).
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

    for edge_id, edge in sorted(graph.edges.items()):
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


@public_op(name="ef.validate")
def validate(
    graph: Graph,
    *,
    node_registry: NodeRegistry = default_node_registry,
    type_registry: TypeRegistry = default_type_registry,
) -> Diagnostics:
    """Validate *graph*'s wiring and return structured diagnostics (Story 5).

    Runs whole-graph type inference (Story 4) then checks every edge with the
    rules engine (Story 3), and adds the structural checks (cardinality, required
    IN ports) plus each node's own param contract (required/undeclared params and
    every `ValidationHints` constraint, via `NodeDefinition.validate_node`). The
    result is JSON-native so the canvas renders it directly.

    The experiment-validity rule pack (Epic 17) is also run: findings ride the
    same channel, each carrying a ``rule_id`` and every implicated node in
    ``related_node_ids``, with ``source="validator"``.

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
    params = _collect_param_diagnostics(graph, node_registry)
    ref_params = _collect_param_ref_diagnostics(graph, node_registry)
    type_diagnostics, edge_compatibility = _collect_type_diagnostics(
        graph, node_registry, type_registry
    )
    validity_diagnostics = _collect_validity_diagnostics(graph)
    diagnostics = [
        d.model_copy(update={"source": "validator"})
        for d in structural + params + ref_params + type_diagnostics + validity_diagnostics
    ]
    return Diagnostics(
        diagnostics=diagnostics,
        edge_compatibility=edge_compatibility,
    )


def _collect_validity_diagnostics(graph: Graph) -> list[Diagnostic]:
    """Run the experiment-validity rule pack and map findings to `Diagnostic`s.

    Each `ValidityFinding` becomes a `Diagnostic` carrying ``rule_id`` and
    ``related_node_ids`` (added Task 01) so findings ride the existing
    diagnostics channel (ADR 0012). Lazy-imports the validity package to avoid a
    circular import through ``emergentflow.ir`` (mutation imports this module).

    Deterministic: the runner returns findings in rule-id order, each rule in
    node-id order, so `validate` stays golden-testable.
    """
    from emergentflow.validity.runner import run_validity_checks

    return [
        Diagnostic(
            severity=Severity(finding.severity),
            code=finding.rule_id,
            message=finding.message,
            node_id=finding.node_id,
            related_node_ids=list(finding.related_node_ids),
            rule_id=finding.rule_id,
        )
        for finding in run_validity_checks(graph)
    ]


@public_op(name="ef.apply_suppressions")
def apply_suppressions(
    diagnostics: Diagnostics,
    suppressions: list[list[str]],
) -> Diagnostics:
    """Return a copy of *diagnostics* with suppressed validity findings removed.

    Suppression is workspace/session state that lives BESIDE the graph, never on
    it (ADR 0019 discipline): a finding is suppressed by (rule_id, node_id).
    *suppressions* is a list of ``[rule_id, node_id]`` pairs (JSON-native shape,
    matching what the canvas stores per flow). A diagnostic is dropped when its
    ``rule_id`` and ``node_id`` both match a pair. Non-validity diagnostics
    (no ``rule_id``) are never suppressed. Pure: the input *diagnostics* is not
    mutated.

    Args:
        diagnostics: The `Diagnostics` to filter.
        suppressions: JSON-native list of ``[rule_id, node_id]`` pairs.

    Returns:
        A new `Diagnostics` with the same ``edge_compatibility`` and the
        unsuppressed diagnostics, in the original order.
    """
    suppressed = {(pair[0], pair[1]) for pair in suppressions if len(pair) >= 2}
    kept = [
        d
        for d in diagnostics.diagnostics
        if d.rule_id is None or (d.rule_id, d.node_id) not in suppressed
    ]
    return Diagnostics(
        diagnostics=kept,
        edge_compatibility=diagnostics.edge_compatibility,
    )


@public_op(name="ef.apply_type_compatibility")
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


def _format_error_location(diag: Diagnostic) -> str:
    """One-line, location-naming description of a single error diagnostic.

    Names the edge and/or node/port the diagnostic is about so the raised
    `GraphValidationError` points the author straight at the broken wiring.
    """
    where_parts: list[str] = []
    if diag.edge_id is not None:
        where_parts.append(f"edge {diag.edge_id!r}")
    if diag.node_id is not None:
        port = f".{diag.port_name}" if diag.port_name else ""
        where_parts.append(f"node {diag.node_id!r}{port}")
    where = " ".join(where_parts) if where_parts else "graph"
    return f"[{diag.code}] {where}: {diag.message}"


@public_op(name="ef.codegen.enforce_validation_gate")
def enforce_validation_gate(
    graph: Graph,
    *,
    node_registry: NodeRegistry = default_node_registry,
    type_registry: TypeRegistry = default_type_registry,
) -> Diagnostics:
    """Validate *graph* and raise on any error-severity diagnostic (Story 6).

    The single shared gate both `compile_to_code` and `execute` call before doing
    any work on the **FUNCTIONAL** path, so the two pure functions accept/reject
    identical graphs for identical reasons (ADR 0002 equivalence extends to
    rejection). DECLARATIVE graphs are out of scope here: they are gated
    separately by `_prepare_declarative` (the shared compiler/executor declarative
    seam), which both pure functions reach before this gate. This is a
    codegen-internal seam (like `infer_graph_types`); users call `ef.validate`.

    Runs `validate` (Story 5) and, if it produced any error-severity diagnostic
    (type incompatibility, cardinality violation, or unconnected required IN
    port), raises `GraphValidationError` naming every offending node/edge/port.
    Warnings (e.g. unregistered tokens) **pass through** — they never block, so
    exploratory runs still execute; callers inspect them on the returned
    `Diagnostics` (or via `ef.validate`).

    Pure and deterministic: both registries are passed straight through to
    `validate` (defaulting to the package singletons) and there is no I/O or
    mutation, so the gate keeps Epic 6 sandboxing and client-side shipping
    trivial.

    Args:
        graph: The graph to gate.
        node_registry: Node registry, forwarded to `validate`. Defaults to the
            package singleton.
        type_registry: Type registry, forwarded to `validate`. Defaults to the
            package singleton.

    Returns:
        The `Diagnostics` from `validate` when there are no errors (it may still
        carry warnings).

    Raises:
        GraphValidationError: If `validate` produced any error-severity
            diagnostic.
    """
    diagnostics = validate(graph, node_registry=node_registry, type_registry=type_registry)
    if diagnostics.errors:
        detail = "\n".join(_format_error_location(d) for d in diagnostics.errors)
        raise GraphValidationError(
            f"Graph {graph.name!r} failed validation with "
            f"{len(diagnostics.errors)} error(s):\n{detail}"
        )
    return diagnostics
