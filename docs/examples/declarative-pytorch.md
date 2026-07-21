# Declarative PyTorch Models

Build PyTorch `nn.Module` models as visual graphs. A narrow seam supporting linear chains of
layers, compiled into proper `nn.Module` classes.

## 1. The Declarative Paradigm

Every Emergent Flow graph declares a `paradigm`:

- **FUNCTIONAL** (default) — a flat DAG of `ef.*` calls, assembled in deterministic
  topological order. This is what every other guide in this section uses.
- **DECLARATIVE** — an `nn.module` node that owns a *subgraph* of layer nodes, compiled into
  a real PyTorch `nn.Module` subclass rather than a flat sequence of function calls.

`compile_to_code` and `execute` both dispatch on `graph.paradigm`, so the same two entry
points you already use for functional pipelines also drive declarative graphs — no separate
API.

The declarative seam (`emergentflow/codegen/declarative.py`) is intentionally narrow:

- Only two layer types are wired up: `nn.linear` and `nn.relu`.
- The `nn.module` node's subgraph must be a **single linear chain** — one layer feeding the
  next, no branching, no fan-in/fan-out, no skip connections.
- `torch` is an *optional* dependency, not installed by default.

A single shared validation function, `_prepare_declarative`, gates both `compile_to_code` and
`execute` for declarative graphs, so the two paths accept and reject exactly the same graphs
with exactly the same errors (ADR 0002 equivalence, applied to this seam).

## 2. Graph Structure (JSON)

A declarative graph has `"paradigm": "declarative"` at the top level. The `nn.module` node
carries no ports or params of its own — it owns a `subgraph`, which is itself a nested
`Graph` (nodes + edges) holding the layer chain. Each layer node declares its params as typed
`Param` entries; `nn.linear` requires both `in_features` and `out_features` (there's no shape
inference yet — see [Current Limitations](#5-current-limitations)).

Here's a trimmed two-layer network — `Linear(128, 64) -> ReLU -> Linear(64, 10)` — matching
`examples/declarative_module.json` in the repo:

```json
{
  "schema_version": 1,
  "paradigm": "declarative",
  "name": "Declarative Module Example",
  "nodes": {
    "n-module": {
      "id": "n-module",
      "type": "nn.module",
      "label": "SimpleClassifier",
      "paradigm": "declarative",
      "params": [],
      "ports": [],
      "subgraph": {
        "schema_version": 1,
        "paradigm": "declarative",
        "name": "SimpleClassifier body",
        "nodes": {
          "n-linear1": {
            "id": "n-linear1",
            "type": "nn.linear",
            "label": "Linear 128→64",
            "paradigm": "declarative",
            "params": [
              {"name": "in_features", "type_token": "int", "value": 128},
              {"name": "out_features", "type_token": "int", "value": 64}
            ],
            "ports": [
              {"id": "p-linear1-in", "name": "x", "direction": "in", "data_type": "Tensor"},
              {"id": "p-linear1-out", "name": "out", "direction": "out", "data_type": "Tensor"}
            ]
          },
          "n-relu": {
            "id": "n-relu",
            "type": "nn.relu",
            "label": "ReLU",
            "paradigm": "declarative",
            "params": [],
            "ports": [
              {"id": "p-relu-in", "name": "x", "direction": "in", "data_type": "Tensor"},
              {"id": "p-relu-out", "name": "out", "direction": "out", "data_type": "Tensor"}
            ]
          },
          "n-linear2": {
            "id": "n-linear2",
            "type": "nn.linear",
            "label": "Linear 64→10",
            "paradigm": "declarative",
            "params": [
              {"name": "in_features", "type_token": "int", "value": 64},
              {"name": "out_features", "type_token": "int", "value": 10}
            ],
            "ports": [
              {"id": "p-linear2-in", "name": "x", "direction": "in", "data_type": "Tensor"},
              {"id": "p-linear2-out", "name": "out", "direction": "out", "data_type": "Tensor"}
            ]
          }
        },
        "edges": {
          "e-linear1-relu": {
            "id": "e-linear1-relu",
            "source": {"node_id": "n-linear1", "port_id": "p-linear1-out"},
            "target": {"node_id": "n-relu", "port_id": "p-relu-in"}
          },
          "e-relu-linear2": {
            "id": "e-relu-linear2",
            "source": {"node_id": "n-relu", "port_id": "p-relu-out"},
            "target": {"node_id": "n-linear2", "port_id": "p-linear2-in"}
          }
        }
      }
    }
  },
  "edges": {}
}
```

Note the shape: nesting uses `Node.subgraph` (a full nested `Graph`), not parent/child id
references — the same mechanism the canvas uses for any collapsible node group. The
top-level graph's own `edges` map is empty because the only top-level node is the
`nn.module` container itself; all the wiring lives inside its subgraph.

## 3. Compiling to Code

```python
import emergentflow as ef
from emergentflow.ir.serialize import load_graph

graph = load_graph("examples/declarative_module.json")
code = ef.compile_to_code(graph)
print(code)
```

This emits a proper `nn.Module` subclass — `__init__` assigns one `self.<attr>` per layer in
topological order, and `forward` threads a single rolling variable through each layer call:

```python
"""Generated by Emergent Flow. Do not edit by hand."""

import torch.nn as nn


class SimpleClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.linear_12864 = nn.Linear(128, 64)
        self.relu = nn.ReLU()
        self.linear_6410 = nn.Linear(64, 10)

    def forward(self, x):
        x = self.linear_12864(x)
        x = self.relu(x)
        x = self.linear_6410(x)
        return x
```

The class name comes from the `nn.module` node's `label` (`"SimpleClassifier"`, used verbatim
since it's already a valid identifier); per-layer attribute names are derived from each
layer's label/type, disambiguated on collision.

## 4. Executing

```python
# Requires torch to be installed (not a package dependency)
# uv pip install torch
results = ef.execute(graph)
```

Unlike a functional graph, `execute` on a declarative graph doesn't run a forward pass over
real data. It builds a **structural twin** of the compiled module — the same layer types,
params, and order, assembled as an `nn.Sequential` with freshly (randomly) initialized
weights — and returns an inspectable summary keyed by the `nn.module` node's id:

```python
{"n-module": {"layers": ["Linear(in_features=128, out_features=64, bias=True)", "ReLU()", "Linear(in_features=64, out_features=10, bias=True)"]}}
```

This keeps `execute`'s return value serializable and inspectable (a live `nn.Module` is
neither), while still letting you confirm the compiled architecture matches what you wired up
in the canvas. Because weights are freshly initialized rather than loaded from a checkpoint,
equivalence between the compiled class and `execute`'s result is **structural** (same
architecture), not numerical.

## 5. Current Limitations

- Only `nn.linear` and `nn.relu` layer types are supported.
- Only single linear chains — no branching, no fan-in/fan-out, no skip connections. Exactly
  one `nn.module` node per graph, owning exactly one connected chain of layers.
- `nn.linear` requires both `in_features` and `out_features` explicitly; there's no
  shape-inference from upstream layers yet.
- `torch` must be installed separately (`uv pip install torch`) — it's not a package
  dependency, and both `compile_to_code` and `execute` raise `CodegenError` on unsupported
  shapes (agent/LangGraph node types, multiple `nn.module` nodes, an empty subgraph, invalid
  layer params, or a non-linear-chain subgraph) before ever touching torch.
- No training loop — the seam compiles the architecture; training is user code.

## 6. In the Canvas

> **In the Canvas:** Switch the graph paradigm to **DECLARATIVE** in the toolbar. Add an
> `nn.module` node as the container, then add `nn.linear` and `nn.relu` nodes inside it.
> Connect layers in sequence. The Code tab shows the compiled `nn.Module` class updating live
> as you wire layers. See [Canvas UI Guide](canvas-ui-guide.md).
