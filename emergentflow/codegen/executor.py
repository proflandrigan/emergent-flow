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
from emergentflow.codegen.declarative import _prepare_declarative
from emergentflow.codegen.errors import CodegenError, UnboundInputError
from emergentflow.codegen.traversal import topological_sort
from emergentflow.codegen.validation import enforce_validation_gate, required_in_port_names
from emergentflow.codegen.wiring import build_wiring_map
from emergentflow.ir import Direction, Graph, Node, Paradigm
from emergentflow.nodes import get as get_node_definition
from emergentflow.nodes import registry as default_node_registry


def _describe(node: Node) -> str:
    """Human-readable identifier for a node in error messages."""
    label = (node.label or "").strip()
    if label:
        return f"{label!r} (id={node.id})"
    return f"{node.type!r} (id={node.id})"


@public_op(name="ef.execute")
def execute(graph: Graph, *, client: Any | None = None) -> dict[str, dict[str, Any]]:
    """Run *graph* in-process, node by node, in topological order.

    Args:
        graph: The IR graph to execute.
        client: An injected ``LLMClient`` (ADR 0017), passed to any node whose
            definition class sets ``requires_client = True``. Graphs with no
            such node never touch this parameter and behave exactly as before
            this parameter was added (back-compat gate, Epic 9 Story 1).

    Returns:
        A mapping from node id to that node's outputs, themselves keyed by
        OUT-port name: ``{node_id: {out_port_name: value}}``.

    Raises:
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
                              a type incompatibility, a cardinality violation,
                              or an unconnected required IN port. Raised before
                              any node runs. Warnings do not block.
    """
    if graph.paradigm is Paradigm.DECLARATIVE:
        return _execute_declarative(graph)

    # Story 6: gate the FUNCTIONAL path on validation before running any node, so
    # execute and compile_to_code reject identical graphs for identical reasons
    # (ADR 0002 equivalence extends to rejection). Warnings pass through.
    enforce_validation_gate(graph)

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
    # may legitimately be unconnected; Step 4 below passes `None` for those).
    wiring_map = build_wiring_map(graph)
    for node_id in topo_order_ids:
        node = graph.nodes[node_id]
        required_in_names = required_in_port_names(node.type, default_node_registry)
        for port in node.ports:
            if port.direction != Direction.IN:
                continue
            if port.name not in required_in_names:
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
            if len(sources) > 1:
                raise ValueError(
                    f"IN port {port.name!r} on node {node.id!r} has {len(sources)} "
                    "sources; multi-source fan-in is not yet supported by codegen "
                    "context."
                )
            if not sources:
                # The dangling-input guard above only rejects unconnected
                # *required* ports, so a zero-source port reaching here is a
                # genuinely optional one (PortSpec.required=False) -- pass
                # `None`, mirroring `build_codegen_context`'s `None`-literal
                # binding for the same case (ADR 0002 equivalence).
                inputs[port.name] = None
                continue
            src = sources[0]
            src_node = graph.nodes[src.node_id]
            src_port_name = next(p.name for p in src_node.ports if p.id == src.port_id)
            inputs[port.name] = results[src.node_id][src_port_name]

        definition = get_node_definition(node.type)()
        if type(definition).requires_client:
            # Widen past NodeDefinition.execute's declared (node, inputs)
            # signature via cast(Any, ...): LLM-call node subclasses accept an
            # extra `client` keyword, but the abstract base signature stays
            # unchanged so the ~30 existing node subclasses need no re-typing.
            results[node.id] = cast(Any, definition.execute)(node, inputs, client=client)
        else:
            results[node.id] = definition.execute(node, inputs)

    # Step 5: Return collected results
    return results


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
