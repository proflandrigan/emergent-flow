# Graph IR & Compilation

Emergent Flow is built around one invariant (ADR 0001): **the graph IR is the single source
of truth**. Every pipeline — whether you build it in Python, load it from JSON, or drag nodes
around on the canvas — is a `Graph` object. Two pure functions consume that same IR:
`ef.compile_to_code(graph)`, which emits a runnable Python module, and `ef.execute(graph)`,
which runs it in-process. Python source code is a **one-way compiled artifact**: it is never
re-parsed back into a graph. This guide is a deeper look at the IR shape and the four entry
points (`compile_to_code`, `execute`, `validate`, `export_script`) that operate on it. For the
higher-level tour of the SDK, see [Getting Started](getting-started.md).

## 1. IR Structure

A serialized graph is a JSON object with four top-level fields: `schema_version`, `paradigm`,
`nodes`, and `edges` (plus an optional `name`). Here is a minimal, real two-node graph —
`data.load_sample` feeding `stats.describe`:

```json
{
  "schema_version": 1,
  "paradigm": "functional",
  "name": "Simple Pipeline",
  "nodes": {
    "n-load": {
      "id": "n-load",
      "type": "data.load_sample",
      "label": "Load Iris",
      "paradigm": "functional",
      "params": [
        { "name": "name", "type_token": "str", "value": "iris", "default": null }
      ],
      "ports": [
        {
          "id": "p-load-out",
          "name": "frame",
          "direction": "out",
          "data_type": "DataFrame",
          "cardinality": "one",
          "label": null
        }
      ],
      "position": { "x": 100.0, "y": 100.0 },
      "group_id": null,
      "subgraph": null
    },
    "n-describe": {
      "id": "n-describe",
      "type": "stats.describe",
      "label": "Summary Stats",
      "paradigm": "functional",
      "params": [
        { "name": "columns", "type_token": "list[str]", "value": null, "default": null }
      ],
      "ports": [
        {
          "id": "p-describe-in",
          "name": "frame",
          "direction": "in",
          "data_type": "DataFrame",
          "cardinality": "one",
          "label": null
        },
        {
          "id": "p-describe-out",
          "name": "summary",
          "direction": "out",
          "data_type": "DataFrame",
          "cardinality": "one",
          "label": null
        }
      ],
      "position": { "x": 300.0, "y": 100.0 },
      "group_id": null,
      "subgraph": null
    }
  },
  "edges": {
    "e-load-describe": {
      "id": "e-load-describe",
      "source": { "node_id": "n-load", "port_id": "p-load-out" },
      "target": { "node_id": "n-describe", "port_id": "p-describe-in" },
      "type_compatible": null
    }
  }
}
```

A few details worth noting because they're easy to get wrong from memory:

- **`schema_version`** is currently **`1`** (`emergentflow.ir.graph.CURRENT_SCHEMA_VERSION`).
  Older on-disk graphs are migrated up to this version on load; newer-than-current graphs are
  rejected. Don't hardcode a version number in your own tooling — read it from
  `CURRENT_SCHEMA_VERSION`.
- **`paradigm`** is a lowercase string: `"functional"` or `"declarative"`
  (`emergentflow.ir.common.Paradigm`, a `(str, Enum)`). Both the graph and every node carry
  their own `paradigm` field.
- **`nodes` and `edges` are dicts keyed by id, not arrays.** Each node's map key must equal its
  own `.id`, and same for edges — `Graph`'s structural validator rejects a mismatch. This
  dict-of-objects shape is deliberately CRDT-friendly (concurrent edits from the canvas and an
  agent merge without positional-array conflicts).
- **A node's `params` is a list of typed `Param` objects** (`name`, `type_token`, `value`,
  `default`), not a bare `{"key": "value"}` dict. A node's `ports` is likewise an explicit list
  of `Port` objects (`id`, `name`, `direction`, `data_type`, `cardinality`, `label`) — the IR
  carries the full port shape per node instance, not just a type name.
- **Edges reference endpoints by `{node_id, port_id}` (a `PortRef`)**, not by flat
  `source`/`target`/`source_port`/`target_port` strings. `Graph`'s structural validator checks
  that every edge's `source` resolves to an OUT port and every `target` resolves to an IN port
  on nodes that actually exist in the graph.
- `position` (`{x, y}`), `group_id`, and `subgraph` round out `Node` — canvas placement, an
  optional parent group/composite node, and an optional inner graph (used by declarative
  `nn.module` nodes and, in future epics, agent subgraphs). This guide only covers the
  FUNCTIONAL paradigm; see [Declarative / PyTorch](declarative-pytorch.md) for `subgraph`.

## 2. Loading Graphs

```python
from emergentflow.ir.serialize import load_graph

# From a file on disk
graph = load_graph("examples/functional_pipeline.json")

# The graph is a Pydantic model
print(graph.paradigm)          # Paradigm.FUNCTIONAL  (serializes to "functional")
print(len(graph.nodes))        # number of nodes
print(graph.schema_version)    # 1
```

`load_graph` reads the file, parses the JSON, migrates it to `CURRENT_SCHEMA_VERSION` if it was
written by an older build, and validates it — raising `GraphDeserializationError` (or its
`SchemaVersionError` subclass) if anything is wrong. The counterpart `save_graph(graph, path)`
writes a graph back out as indented, git-diffable JSON.

## 3. Compiling to Code

```python
import emergentflow as ef

code = ef.compile_to_code(graph)
print(code)
```

`compile_to_code(graph: Graph) -> str` is a pure function of the graph alone — no I/O, no
client. For the two-node graph above, it emits:

```python
"""Generated by Emergent Flow. Do not edit by hand."""

import emergentflow as ef


def main() -> dict[str, object]:
    load_iris_frame = ef.data.load_sample(name="iris")
    summary_stats_summary = ef.stats.describe(load_iris_frame, columns=None)
    return {"summary_stats_summary": summary_stats_summary}


if __name__ == "__main__":
    _results = main()
    for _name, _value in _results.items():
        print(f"{_name} = {_value!r}")
```

Variable names (`load_iris_frame`, `summary_stats_summary`) are derived from each node's
`label` plus the OUT port's name (falling back to the node's `type` when there's no label), not
from opaque IDs — this is what `naming.py`'s `build_name_map` does (Step 8 below). The output
always passes `ruff` formatting; it's a complete, runnable module you could paste into a file
and execute directly. A graph containing a `requires_client` node (an LLM call, ADR 0017)
instead emits a `main(*, client: object | None = None)` entry point — `compile_to_code` itself
stays a pure function of `graph` alone; only the *emitted* module's entry point takes a client.

## 4. Executing

```python
results = ef.execute(graph)
print(results)
# {'n-load': {'frame': <DataFrame>}, 'n-describe': {'summary': <DataFrame>}}
```

`execute(graph: Graph, *, clients=None, client=None) -> dict[str, dict[str, Any]]` is the
in-process reference interpreter — the structural twin of `compile_to_code`. It returns a
mapping from **node id** to that node's outputs, themselves keyed by **OUT-port name**. This is
the same graph, walked the same way (topological order, same wiring), just interpreted instead
of compiled to source.

This is the ADR-0002 invariant the whole product rests on: running the code from
`compile_to_code(graph)` must produce results equivalent to `execute(graph)`. It's enforced as a
CI gate (`uv run pytest -m equivalence`) — whenever a node's `codegen` changes, its `execute`
must change to match, and vice versa.

## 5. Validating

```python
diagnostics = ef.validate(graph)

print(diagnostics.ok)            # True iff there are no error-severity diagnostics
print(diagnostics.errors)        # list[Diagnostic] — hard problems (type mismatch, etc.)
print(diagnostics.warnings)      # list[Diagnostic] — runtime-only-knowable issues
print(diagnostics.diagnostics)   # every finding, error + warning + info
print(diagnostics.edge_compatibility)  # {edge_id: True | False | None}
```

`validate(graph)` runs whole-graph type inference plus the edge-compatibility rules engine and
the structural checks (cardinality, required unconnected IN ports), returning a JSON-native
`Diagnostics` result — the same shape the canvas renders directly as inline warnings/errors.
It's a deliberately separate call from `Graph`'s own construction-time structural validation, so
you can build and inspect a half-wired, exploratory graph without it raising. Both
`compile_to_code` and `execute` run this same check internally before doing any work and raise
`GraphValidationError` if there's an error-severity diagnostic — warnings never block.

## 6. Exporting Scripts

```python
result = ef.export_script(graph, "out/", name="simple_pipeline")

print(result.script_path)        # out/simple_pipeline.py
print(result.requirements_path)  # out/requirements.txt
```

`export_script(graph, dest, *, name=None) -> ExportResult` is the I/O wrapper around
`compile_to_code`: it compiles the graph, prepends a one-line reproduce banner, and writes the
result as a standalone `.py` file into the `dest` directory (created if missing), alongside a
pinned `requirements.txt`. `name` defaults to a snake_case slug of `graph.name` (or
`"pipeline"` if the graph has none). Export is idempotent — re-running it overwrites the same
two files, so use a distinct `dest`/`name` per graph if you don't want that.

## 7. Building Graphs Programmatically

The IR models are ordinary Pydantic models, importable straight from `emergentflow.ir`. Building
a graph by hand means constructing each `Node`'s `Port`s and `Param`s explicitly, then wiring
them with `Edge`/`PortRef` — more verbose than the JSON shorthand above, but it's the same
underlying shape:

```python
from emergentflow.ir import Direction, Edge, Graph, Node, Paradigm, Param, Port, PortRef, Position

load_out = Port(id="p-load-out", name="frame", direction=Direction.OUT, data_type="DataFrame")
load_node = Node(
    id="n-load",
    type="data.load_sample",
    label="Load Iris",
    params=[Param(name="name", type_token="str", value="iris")],
    ports=[load_out],
    position=Position(x=100, y=100),
)

describe_in = Port(id="p-describe-in", name="frame", direction=Direction.IN, data_type="DataFrame")
describe_out = Port(id="p-describe-out", name="summary", direction=Direction.OUT, data_type="DataFrame")
describe_node = Node(
    id="n-describe",
    type="stats.describe",
    label="Summary Stats",
    params=[Param(name="columns", type_token="list[str]", value=None)],
    ports=[describe_in, describe_out],
    position=Position(x=300, y=100),
)

edge = Edge(
    id="e-load-describe",
    source=PortRef(node_id="n-load", port_id="p-load-out"),
    target=PortRef(node_id="n-describe", port_id="p-describe-in"),
)

graph = Graph(
    paradigm=Paradigm.FUNCTIONAL,
    name="Simple Pipeline",
    nodes={load_node.id: load_node, describe_node.id: describe_node},
    edges={edge.id: edge},
)

code = ef.compile_to_code(graph)
results = ef.execute(graph)
```

`Graph`'s structural validator runs at construction time and will reject the graph immediately
if a dict key doesn't match its value's `.id`, an edge references a nonexistent node/port, or a
source/target port has the wrong direction — so a malformed graph fails fast, at `Graph(...)`
construction, not later inside `compile_to_code`/`execute`. In practice, most graphs are built
by loading JSON (`load_graph`) or via the canvas rather than assembled node-by-node like this;
this is mainly useful for generating graphs programmatically (e.g. from a script or an agent).

## 8. The Codegen Pipeline

`compile_to_code` (and `execute`, its structural twin) composes a small, deterministic pipeline
of independent passes:

1. **Traversal** (`traversal.py`) — topological sort of the graph, raising `CycleError` if one
   is found.
2. **Wiring** (`wiring.py`) — maps each IN port to its upstream OUT port (`build_wiring_map`).
3. **Naming** (`naming.py`) — assigns a stable, readable, collision-free Python variable name to
   every OUT port, derived from the node's label (or type) and the port's name
   (`build_name_map`).
4. **Context** (`context.py`) — builds a per-node `CodegenContext` exposing `ctx.in_var(port)` /
   `ctx.out_var(port)`, so a node's `codegen` never has to know or hardcode a variable name.
5. **Assembly** (`compiler.py`) — walks the topo order calling each node's
   `codegen(node, ctx) -> CodeFragment` (an `imports` + `body` pair), de-duplicates imports
   across all fragments, and assembles the final module (or, for `execute`, calls
   `execute(node, inputs) -> dict` directly and threads each OUT port's value to its consumers).
6. **Formatting** (`formatting.py`) — a final `ruff` import-organize + format pass
   (`format_source`) so every emitted module is both import-clean and consistently styled.

## 9. Node Catalog

```python
catalog = ef.export_catalog()

print(catalog["catalog_version"])   # the catalog artifact's own version, distinct from
                                     # Graph.schema_version and each node's contract `version`
print(len(catalog["nodes"]))        # every registered node type: type, ports, params, paradigm
```

`export_catalog()` is a pure builder over the live node registry (plus the curated
estimator/chart/recommender/connector allow-lists) — no I/O. This is the artifact the canvas's
palette and schema-driven config panels consume with no Python present; it's also useful for
discovering what node types are available to wire into a graph.

## 10. In the Canvas

> **In the Canvas:** The canvas is a visual editor for graph IR. Every action (add node,
> connect edge, change params) mutates the graph JSON. Use **Export** in the toolbar to
> download the IR as JSON, and **Import** to load one back. The Code tab in the Inspector shows
> the live `compile_to_code` output updating as you edit the graph. See
> [Canvas UI Guide](canvas-ui-guide.md).

## See also

- [Getting Started](getting-started.md) — the broader SDK tour, including running graphs from
  the canvas.
- [Declarative / PyTorch](declarative-pytorch.md) — the other paradigm, for `nn.module`
  subgraphs.
