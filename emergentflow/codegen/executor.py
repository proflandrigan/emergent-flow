"""
emergentflow.codegen.executor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The reference IR interpreter for the code-generation engine (Epic 2, Story 6).

`execute` is the structural twin of `compile_to_code` (`emergentflow/codegen/compiler.py`):
it topo-walks a functional IR graph, but instead of emitting Python source for
each node, it calls the node's `execute(node, inputs)` directly and threads each
OUT port's value to every downstream IN port that consumes it. It reuses the same
Story 2/3 plumbing the compiler does (`topological_sort`, `build_wiring_map`) and
applies the same guards with the same error messages, so a graph that compiles
also executes, and vice versa.

`Paradigm.DECLARATIVE` graphs are run via a separate declarative seam (Epic 2,
Story 8): instead of topo-walking the whole graph, it locates the graph's single
``nn.module`` node and builds the structural twin of the `nn.Module` subclass
`compile_declarative` (`emergentflow/codegen/declarative.py`) would emit for the
same subgraph — same layer types, params, and order, as an `nn.Sequential`. This
requires `torch` at call time (imported lazily) and raises `CodegenError` for
unsupported layer types or agent/LangGraph targets (deferred to Epic 11).

This is a pure, in-process reference implementation: no sandboxing, no resource
limits, no subprocess isolation. It exists to let the rest of the system (tests,
previews, the ADR-0002 equivalence harness) run a graph without going through
`compile_to_code` + `exec`. The productionized, sandboxed execution runtime is
Epic 6.
"""

from __future__ import annotations

from typing import Any, cast

from emergentflow.api import public_op
from emergentflow.clients import Clients
from emergentflow.codegen.composite import COMPOSITE_NODE_TYPE, resolve_composite_boundary
from emergentflow.codegen.declarative import _prepare_declarative
from emergentflow.codegen.errors import CodegenError, UnboundInputError
from emergentflow.codegen.params import has_graph_param_refs, materialize_graph
from emergentflow.codegen.traversal import topological_sort
from emergentflow.codegen.validation import enforce_validation_gate, required_in_port_names
from emergentflow.codegen.wiring import build_wiring_map
from emergentflow.ir import Cardinality, Direction, Graph, Node, Paradigm
from emergentflow.nodes import get as get_node_definition
from emergentflow.nodes import registry as default_node_registry


def _describe(node: Node) -> str:
    """Human-readable identifier for a node in error messages."""
    label = (node.label or "").strip()
    if label:
        return f"{label!r} (id={node.id})"
    return f"{node.type!r} (id={node.id})"


@public_op(name="ef.execute")
def execute(
    graph: Graph,
    *,
    params: dict[str, Any] | None = None,
    clients: Clients | None = None,
    client: Any | None = None,
) -> dict[str, dict[str, Any]]:
    """Run *graph* in-process, node by node, in topological order.

    Args:
        graph: The IR graph to execute.
        params: Optional runtime overrides for graph-level parameters (issue #116).
            Each key must name a graph-level param; overrides are applied on top of the
            param's stored value before any node runs, and never mutate *graph*. When None
            (and the graph declares no ref'd params), execution is byte-identical to the
            pre-parameter behavior.
        clients: An injected ``Clients`` bundle (ADR 0018) exposing named
            effectful-client seams (``clients.llm``, ``clients.warehouse``, ...).
            Each node is handed the client for the single capability it declares
            via ``required_client_kinds()``. Graphs with no client-requiring node
            never touch it and behave exactly as before.
        client: **Legacy** single-client keyword (ADR 0017). It always meant the
            LLM client, so it is mapped onto ``Clients(llm=client)`` for
            back-compat. Passing both ``clients`` and ``client`` is an error.

    Returns:
        A mapping from node id to that node's outputs, themselves keyed by
        OUT-port name: ``{node_id: {out_port_name: value}}``.

    Raises:
        GraphParamError: If an override in *params* names no graph-level parameter
            (from `emergentflow.codegen.params.resolve_graph_params`).
        CodegenError: If the graph is `Paradigm.DECLARATIVE` and the
                      declarative seam rejects it (unsupported layer type,
                      not exactly one `nn.module` node, or an agent/LangGraph
                      target — see `_execute_declarative`). For
                      `Paradigm.FUNCTIONAL` graphs, if the graph or any node
                      has a non-FUNCTIONAL paradigm.
        UnboundInputError: If a *required* input port (per its `PortSpec`) is
                           not connected to an upstream output port. An
                           optional (`required=False`) IN port left
                           unconnected instead receives `None`.
        CycleError: If the graph contains a cycle (propagated from
                    `topological_sort`).
        GraphValidationError: If the graph fails the shared validation gate —
            a type incompatibility, a cardinality violation, an unconnected required
            IN port, OR an error-severity graph-param ref diagnostic (unresolved ref,
            mistyped ref, or ref on a node that does not support refs). Raised before
            any node runs. Warnings do not block.
        ValueError: If both ``clients`` and ``client`` are passed.
    """
    if clients is not None and client is not None:
        raise ValueError(
            "execute() accepts either the legacy client= (the LLM client) or "
            "clients=Clients(...), not both."
        )
    if clients is None:
        clients = Clients.from_legacy_client(client)

    if graph.paradigm is Paradigm.DECLARATIVE:
        declarative = (
            materialize_graph(graph, params=params)
            if params is not None or has_graph_param_refs(graph)
            else graph
        )
        return _execute_declarative(declarative)

    # Story 6: gate the FUNCTIONAL path on validation before running any node, so
    # execute and compile_to_code reject identical graphs for identical reasons
    # (ADR 0002 equivalence extends to rejection). Warnings pass through. Only the
    # top-level graph is gated this way -- a composite node's subgraph is not
    # (see `_execute_functional`), mirroring how `_prepare_declarative` never
    # re-runs this gate on an `nn.module`'s subgraph either. The gate runs on the
    # ORIGINAL graph BEFORE refs are materialized, so an unresolved/mistyped ref
    # surfaces as an error-severity diagnostic here, never as a later KeyError.
    enforce_validation_gate(graph)

    if params is not None or has_graph_param_refs(graph):
        materialized = materialize_graph(graph, params=params)
        # Re-gate the materialized copy so an override whose value violates a ref'd
        # node param's OWN declared contract (choices/min/max, ...) is rejected here
        # too -- the server's FUNCTIONAL walk already does this via
        # `_execute_functional_stream`, and a value `ef.execute` accepts while the
        # server 422s on is an inconsistency (issue #116). `validate_param_values`
        # skips None, and refs are re-checked against the same map, so a graph that
        # passed the first gate passes here unless an override value is genuinely
        # invalid for the node it feeds.
        enforce_validation_gate(materialized)
    else:
        materialized = graph

    return _execute_functional(materialized, clients)


def _execute_functional(
    graph: Graph,
    clients: Clients,
    *,
    seed_inputs: dict[tuple[str, str], Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run a `Paradigm.FUNCTIONAL` graph (or a composite node's subgraph) node by node.

    `seed_inputs`, when given, pre-binds specific `(node_id, port_name)` dangling IN ports to
    a caller-supplied value instead of `None` — used exactly once, by `_execute_composite`, to
    thread a composite node's own resolved inputs onto its subgraph's boundary (issue #117
    stage 3). `execute()`'s top-level call always passes `seed_inputs=None`.
    """
    # Step 1: Paradigm guard
    if graph.paradigm is not Paradigm.FUNCTIONAL:
        raise CodegenError(
            f"Graph {graph.name!r} has paradigm {graph.paradigm!r}. Only "
            f"{Paradigm.FUNCTIONAL!r} is supported by this compiler. "
            "Declarative codegen is Epic 2 Story 8."
        )

    for node in graph.nodes.values():
        if node.paradigm is not Paradigm.FUNCTIONAL:
            raise CodegenError(
                f"Node {_describe(node)} has paradigm {node.paradigm!r}. Only "
                f"{Paradigm.FUNCTIONAL!r} is supported by this compiler. "
                "Declarative codegen is Epic 2 Story 8."
            )

    # Step 2: Topological order
    topo_order_ids = topological_sort(graph)

    # Step 3: Dangling-input guard (required IN ports only -- optional IN ports
    # may legitimately be unconnected; Step 4 below passes `None` for those). A
    # port present in `seed_inputs` is bound by the enclosing composite, not
    # genuinely dangling.
    wiring_map = build_wiring_map(graph)
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        required_in_names = required_in_port_names(node.type, default_node_registry)
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            if port.name not in required_in_names:
                continue
            if seed_inputs is not None and (node.id, port.name) in seed_inputs:
                continue
            if not wiring_map.upstream(node.id, port.id):
                raise UnboundInputError(
                    f"Input port {port.name!r} of node {_describe(node)} is unbound. "
                    "All input ports must be connected."
                )

    # Step 4: Execution walk
    results: dict[str, dict[str, Any]] = {}
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]

        inputs: dict[str, Any] = {}
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            sources = wiring_map.upstream(node.id, port.id)
            if port.cardinality == Cardinality.MANY:
                # A composite's dangling (boundary) MANY IN port is seeded with the
                # composite's own IN-port value by `_execute_composite`; honor it before
                # the sources-only path, exactly as the ONE-cardinality branch does below.
                # Without this, a MANY boundary port has no intra-subgraph source, so the
                # lines below would hand the node an empty list, silently dropping the
                # seeded outer value (an ADR-0002 divergence from compile_to_code, which
                # threads the same value through as a positional arg).
                seed_key = (node.id, port.name)
                if seed_inputs is not None and seed_key in seed_inputs:
                    inputs[port.name] = seed_inputs[seed_key]
                    continue
                values: list[Any] = []
                for src in sources:
                    src_node = graph.nodes[src.node_id]
                    src_port_name = next(p.name for p in src_node.ports if p.id == src.port_id)
                    values.append(results[src.node_id][src_port_name])
                inputs[port.name] = values
                continue
            if len(sources) > 1:
                raise ValueError(
                    f"IN port {port.name!r} on node {node.id!r} has {len(sources)} "
                    "sources but Cardinality.ONE; only one source is allowed. This "
                    "should be unreachable -- build_wiring_map raises CardinalityError "
                    "for this case first."
                )
            if not sources:
                seed_key = (node.id, port.name)
                if seed_inputs is not None and seed_key in seed_inputs:
                    inputs[port.name] = seed_inputs[seed_key]
                else:
                    # The dangling-input guard above only rejects unconnected
                    # *required*, non-seeded ports, so a zero-source port reaching
                    # here is a genuinely optional one (PortSpec.required=False) --
                    # pass `None`, mirroring `build_codegen_context`'s `None`-literal
                    # binding for the same case (ADR 0002 equivalence).
                    inputs[port.name] = None
                continue
            src = sources[0]
            src_node = graph.nodes[src.node_id]
            src_port_name = next(p.name for p in src_node.ports if p.id == src.port_id)
            inputs[port.name] = results[src.node_id][src_port_name]

        if node.type == COMPOSITE_NODE_TYPE:
            # A composite is compiled/executed recursively (see
            # `emergentflow.codegen.composite`), never via generic per-node dispatch --
            # its own `execute()` raises NotImplementedError on purpose.
            results[node.id] = _execute_composite(node, inputs, clients)
            continue

        definition = get_node_definition(node.type)()
        kinds = type(definition).required_client_kinds()
        if not kinds:
            results[node.id] = definition.execute(node, inputs)
        elif len(kinds) == 1:
            # Resolve the node's single declared capability from the bundle and
            # pass it as `client=`. For an LLM node this is `clients.llm` — the
            # exact value the legacy `client=` path supplied — so every Epic 9
            # node is byte-for-byte unchanged; a warehouse node gets
            # `clients.warehouse` through the same keyword. Widen past the
            # abstract (node, inputs) signature via cast(Any, ...): effectful
            # node subclasses accept an extra `client` keyword.
            (kind,) = tuple(kinds)
            resolved = clients.for_kind(kind)
            results[node.id] = cast(Any, definition.execute)(node, inputs, client=resolved)
        else:
            raise NotImplementedError(
                f"Node type {node.type!r} declares multiple client capabilities "
                f"{sorted(k.value for k in kinds)!r}; multi-capability threading is a later "
                "story. File a node needing two effectful clients if you hit this."
            )

    # Step 5: Return collected results
    return results


def _execute_composite(node: Node, inputs: dict[str, Any], clients: Clients) -> dict[str, Any]:
    """Recursively execute a `layout.composite` node's subgraph (issue #117 stage 3).

    `inputs` is keyed by the composite's own IN-port names, resolved from the OUTER graph's
    wiring exactly like any other node's inputs. Each is seeded onto the subgraph's
    corresponding dangling IN port (by canonical boundary position -- see
    `emergentflow.codegen.composite.resolve_composite_boundary`) before the subgraph runs; the
    subgraph's exposed OUT ports, in that same canonical order, become the composite's own
    OUT-port values.
    """
    if node.subgraph is None:
        raise CodegenError(f"Composite node {_describe(node)} has no subgraph to execute.")

    boundary = resolve_composite_boundary(node.subgraph)
    in_ports = [p for p in node.ports if p.direction == Direction.IN]
    out_ports = [p for p in node.ports if p.direction == Direction.OUT]
    if len(in_ports) != len(boundary.dangling_in):
        raise CodegenError(
            f"Composite node {_describe(node)} declares {len(in_ports)} IN port(s) but its "
            f"subgraph has {len(boundary.dangling_in)} dangling IN port(s); they must match."
        )
    if len(out_ports) != len(boundary.exposed_out):
        raise CodegenError(
            f"Composite node {_describe(node)} declares {len(out_ports)} OUT port(s) but its "
            f"subgraph has {len(boundary.exposed_out)} exposed OUT port(s); they must match."
        )

    seed_inputs: dict[tuple[str, str], Any] = {}
    for in_port, ref in zip(in_ports, boundary.dangling_in, strict=True):
        owner = node.subgraph.nodes[ref.node_id]
        port_name = next(p.name for p in owner.ports if p.id == ref.port_id)
        seed_inputs[(ref.node_id, port_name)] = inputs[in_port.name]

    subgraph_results = _execute_functional(node.subgraph, clients, seed_inputs=seed_inputs)

    outputs: dict[str, Any] = {}
    for out_port, ref in zip(out_ports, boundary.exposed_out, strict=True):
        owner = node.subgraph.nodes[ref.node_id]
        port_name = next(p.name for p in owner.ports if p.id == ref.port_id)
        outputs[out_port.name] = subgraph_results[ref.node_id][port_name]
    return outputs


def _execute_declarative(graph: Graph) -> dict[str, dict[str, Any]]:
    """Run a `Paradigm.DECLARATIVE` graph's single `nn.module` node.

    This is the execution-side sibling of `compile_declarative`
    (`emergentflow/codegen/declarative.py`, Story 8): it builds the structural
    twin of the `nn.Module` that `compile_declarative` would emit for the same
    subgraph — same layer types, params, and order, assembled as an
    `nn.Sequential` — rather than emitting and exec'ing Python source. Because
    the layers are constructed fresh (not loaded from a trained checkpoint),
    their weights are randomly initialized, so equivalence to the compiled
    class is STRUCTURAL only (same architecture), not numerical. Real forward
    execution against input tensors and sandboxed running of arbitrary
    declarative graphs are Epic 6/10.

    Args:
        graph: The IR graph to execute. Must own exactly one `nn.module` node
               whose `subgraph` holds a single linear chain of supported layer
               nodes (currently `nn.linear` and `nn.relu`).

    Returns:
        ``{module_node.id: {"layers": [<layer repr str>, ...]}}`` — the ordered
        architecture of the structural-twin module. The summary is a list of
        strings (not the live `nn.Sequential`) so the result satisfies the
        `ef.execute` inspectable-return contract (`emergentflow.api.is_inspectable`);
        a live torch module is not a serializable/inspectable artifact.

    Raises:
        CodegenError: Whatever `_prepare_declarative` (the shared compiler/
                      executor validation gate) rejects — an agent/LangGraph
                      node (Epic 11); not exactly one `nn.module` node owning a
                      non-empty subgraph; an unsupported, non-DECLARATIVE, or
                      invalid-param layer; or a subgraph that is not a single
                      linear chain (the full catalog/branching is Epic 10).
    """
    # Validate and resolve via the SAME gate the compiler uses, so execute and
    # compile_to_code accept/reject exactly the same declarative graphs.
    module_node, subgraph, order, _wiring = _prepare_declarative(graph)

    # Build the structural twin of the compiled nn.Module: same layer
    # types/params/order as `compile_declarative` would emit, as an
    # nn.Sequential. Weights are randomly initialized (no checkpoint is
    # loaded), so equivalence to the compiled class is STRUCTURAL only; real
    # forward execution and sandboxing are Epic 6/10.
    import torch.nn as nn  # noqa: PLC0415  (lazy: torch is not a hard dependency)

    layers = []
    for node_id in order:
        node = subgraph.nodes[node_id]
        definition = get_node_definition(node.type)()
        out = definition.execute(node, {})  # layer node returns {"out": <layer obj>}
        layers.append(out["out"])
    module = nn.Sequential(*layers)
    # Return an inspectable architecture summary (ordered layer reprs), not the
    # live module: `ef.execute` is a public op and must return a serializable +
    # inspectable result (emergentflow.api.is_inspectable).
    layer_reprs = [repr(layer) for layer in module.children()]
    return {module_node.id: {"layers": layer_reprs}}
