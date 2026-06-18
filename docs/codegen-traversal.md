# Codegen Graph Traversal (Story 2)

The code-generation engine (`colonymind.codegen`, Epic 2) turns a graph IR into either
runnable Python (`cm.compile_to_code`, Story 5) or executed results (`cm.execute`, Story 6).
Both paths first need to understand the graph's *shape*: in what order do nodes run, and which
upstream output feeds each node's inputs? Story 2 provides that shared, paradigm-agnostic
plumbing. It is pure analysis over a single functional-pipeline `Graph` — no code is emitted
and nothing is executed here.

These helpers assume a structurally valid graph: the `Graph` model's own validator already
guarantees that every edge endpoint references an existing node and port, that source ports
are `OUT` and target ports are `IN`. The traversal layer does not re-check structure; it
focuses on ordering, cycles, and wiring.

## Public surface

Both functions are exposed through the lazily-imported `cm.codegen` namespace:

```python
import colonymind as cm

order = cm.codegen.topological_sort(graph)   # list[node_id]
wiring = cm.codegen.build_wiring_map(graph)   # WiringMap
```

The whole-graph verbs `cm.compile_to_code` and `cm.execute` remain reserved at the top level
per [ADR 0010](adr/0010-codegen-package-placement.md); the traversal helpers sit under
`cm.codegen` because they are internal plumbing those verbs compose.

## Deterministic topological order

`topological_sort(graph) -> list[str]` returns every node id in dependency order: a node
always appears after every node feeding one of its IN ports. It uses Kahn's algorithm with a
**stable tie-break by ascending node id**, so independent (unordered) nodes always come out in
the same order. The result is identical regardless of the order nodes or edges were inserted
into the graph.

Determinism is not a nicety — golden-file tests and the [ADR 0002](adr/0002-execute-the-ir-not-the-string.md)
equivalence invariant both depend on the compiler producing byte-stable output for a given
graph, and stable ordering is the foundation of that stability.

## Cycle detection

Functional pipelines must be acyclic — a cycle has no valid topological order. If the graph
contains one, `topological_sort` raises `CycleError` (a subclass of `CodegenError`) whose
message names the nodes still on the cycle (by label when present, otherwise type, always with
the node id), so the author can find and break it.

## The input-wiring map

`build_wiring_map(graph) -> WiringMap` resolves, for every IN port of every node, which
upstream OUT port(s) feed it. The map holds one `InputBinding` per IN port:

- `binding.target` — the IN endpoint (a `PortRef` of node id + port id).
- `binding.sources` — the upstream OUT endpoints feeding it (a list of `PortRef`).
- `binding.is_bound` — whether `sources` is non-empty.

`WiringMap` offers lookups: `upstream(node_id, port_id)` returns the sources feeding an IN
port; `consumers(node_id, port_id)` returns the IN endpoints fed by an OUT port (the fan-out
direction); `is_bound(node_id, port_id)` is a convenience predicate. `WiringMap` is a Pydantic
model — serializable and inspectable — and its lookup indexes are rebuilt automatically after
a JSON round-trip.

### Fan-out and fan-in

**Fan-out** (one OUT port feeding many IN ports) is represented naturally: each downstream IN
port gets its own `InputBinding` pointing back at the shared source, and `consumers()` lists
all of them.

**Fan-in** (one IN port fed by several OUT ports) is governed by the IN port's `cardinality`.
A port declared `Cardinality.MANY` may collect multiple sources. A port declared
`Cardinality.ONE` fed by more than one edge is a wiring error: `build_wiring_map` raises
`CardinalityError`.

### Dangling IN ports

An IN port with no incoming edge is **dangling**. The wiring map records it as unbound — its
`sources` list is empty and `is_bound` is `False` — and `build_wiring_map` does **not** raise.
This is a deliberate choice: the traversal layer reports graph shape without judging it.
Whether an unbound *required* input is fatal is left to the consumers — the compiler (Story 5)
and executor (Story 6) — which have the context to decide. This keeps the foundation pure and
non-prescriptive.

## Scope

Story 2 operates on a single graph's top-level functional nodes and edges. Nodes that carry an
inner `subgraph` are treated as opaque here; the declarative paradigm and subgraph compilation
are [Story 8](../epics/epic-2-code-generation-engine.md). A fuller "how codegen works"
document accompanies the compiler itself in Story 9.
