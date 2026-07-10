# Agent builds, human accepts — call sequence transcript

This file is a **human-readable rendering** of the exact call sequence
`tests/test_acceptance_demo_agent_builds.py::test_agent_builds_describe_and_chart_pair_and_human_accepts`
executes and asserts against. The pytest file is the authoritative, CI-enforced source of truth;
this transcript documents the flow for reference.

The "agent" is the test itself — a plain HTTP client (FastAPI `TestClient`) following the
protocol documented in [`agents/emergent-flow-collaborator.md`](../../agents/emergent-flow-collaborator.md).
No LLM, no live network.

---

### 1. Create a session seeded with `load_csv → describe`

```bash
curl -s -X POST http://127.0.0.1:8765/sessions \
  -H 'Content-Type: application/json' \
  -d '{
    "paradigm": "functional",
    "nodes": {
      "n1": {
        "id": "n1",
        "type": "data.load_csv",
        "label": "Load CSV",
        "paradigm": "functional",
        "params": [
          {"name": "path", "type_token": "str", "value": "examples/vertical_slice/sample.csv", "default": null},
          {"name": "encoding", "type_token": "str", "value": "utf-8", "default": "utf-8"}
        ],
        "ports": [
          {"id": "p1", "name": "frame", "direction": "out", "data_type": "DataFrame", "cardinality": "one"}
        ],
        "position": {"x": 0.0, "y": 0.0},
        "group_id": null
      },
      "n2": {
        "id": "n2",
        "type": "stats.describe",
        "label": "Describe",
        "paradigm": "functional",
        "params": [
          {"name": "columns", "type_token": "list[str]", "value": null, "default": null}
        ],
        "ports": [
          {"id": "p2-in", "name": "frame", "direction": "in", "data_type": "DataFrame", "cardinality": "one"},
          {"id": "p2-out", "name": "summary", "direction": "out", "data_type": "DataFrame", "cardinality": "one"}
        ],
        "position": {"x": 260.0, "y": 0.0},
        "group_id": null
      }
    },
    "edges": {
      "e1": {
        "id": "e1",
        "source": {"node_id": "n1", "port_id": "p1"},
        "target": {"node_id": "n2", "port_id": "p2-in"}
      }
    }
  }'
# {"id":"sess-abc123","graph":{"nodes":{"n1":{...},"n2":{...}},"edges":{"e1":{...}},...},"version":0,"proposals":{}}
```

### 2. Agent discovers the session via `GET /sessions`

```bash
curl -s http://127.0.0.1:8765/sessions
# {"sessions":[{"id":"sess-abc123","graph":{...},"version":0,"proposals":{}}]}
```

### 3. Agent reads `/catalog` — discovers `stats.describe` and `viz.plot` are available

```bash
curl -s http://127.0.0.1:8765/catalog
# {"catalog_version":1,"nodes":[{"type":"data.load_csv","params":[...],"ports":[...]},{"type":"stats.describe","params":[...],"ports":[...]},{"type":"viz.plot","params":[...],"ports":[...]}, ...]}
```

### 4. Agent builds the extended graph and pre-flights it with `/validate`

The agent proposes adding `n3` (a second `stats.describe` reading from the same `n1` CSV)
and `n4` (`viz.plot` consuming `n3`'s summary) — a parallel describe + series chart pair.

```bash
curl -s -X POST http://127.0.0.1:8765/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "paradigm": "functional",
    "nodes": {
      "n1": { ... "data.load_csv" ... },
      "n2": { ... "stats.describe" ... },
      "n3": {
        "id": "n3",
        "type": "stats.describe",
        "label": "Describe (extension)",
        "paradigm": "functional",
        "params": [
          {"name": "columns", "type_token": "list[str]", "value": null, "default": null}
        ],
        "ports": [
          {"id": "p3-in", "name": "frame", "direction": "in", "data_type": "DataFrame", "cardinality": "one"},
          {"id": "p3-out", "name": "summary", "direction": "out", "data_type": "DataFrame", "cardinality": "one"}
        ],
        "position": {"x": 520.0, "y": 0.0},
        "group_id": null
      },
      "n4": {
        "id": "n4",
        "type": "viz.plot",
        "label": "Plot",
        "paradigm": "functional",
        "params": [
          {"name": "chart", "type_token": "str", "value": "histogram", "default": null},
          {"name": "encoding", "type_token": "dict[str, any]", "value": {"x": "score"}, "default": {}},
          {"name": "options", "type_token": "dict[str, any]", "value": {}, "default": {}}
        ],
        "ports": [
          {"id": "p4-in", "name": "frame", "direction": "in", "data_type": "DataFrame", "cardinality": "one"},
          {"id": "p4-out", "name": "plot", "direction": "out", "data_type": "PlotSpec", "cardinality": "one"}
        ],
        "position": {"x": 520.0, "y": 160.0},
        "group_id": null
      }
    },
    "edges": {
      "e1": {"id": "e1", "source": {"node_id": "n1", "port_id": "p1"}, "target": {"node_id": "n2", "port_id": "p2-in"}},
      "e2": {"id": "e2", "source": {"node_id": "n1", "port_id": "p1"}, "target": {"node_id": "n3", "port_id": "p3-in"}},
      "e3": {"id": "e3", "source": {"node_id": "n3", "port_id": "p3-out"}, "target": {"node_id": "n4", "port_id": "p4-in"}}
    }
  }'
# {"diagnostics":{"diagnostics":[],"edge_compatibility":{"e1":true,"e2":true,"e3":true}}}
```

Clean diagnostics — the graph type-checks.

### 5. Agent previews the compiled code with `/compile`

```bash
curl -s -X POST http://127.0.0.1:8765/compile \
  -H 'Content-Type: application/json' \
  -d '{ "paradigm": "functional", "nodes": { ... the same full candidate ... }, "edges": { ... } }'
# {"code":"import emergentflow as ef\n\n\ndef main():\n    ef.data.load_csv(...)\n    ...\n"}
```

### 6. Agent submits the proposal as a `GraphMutation`

```bash
curl -s -X POST http://127.0.0.1:8765/sessions/sess-abc123/proposals \
  -H 'Content-Type: application/json' \
  -d '{
    "base_version": 0,
    "add_nodes": [
      {
        "id": "n3",
        "type": "stats.describe",
        "label": "Describe (extension)",
        "paradigm": "functional",
        "params": [
          {"name": "columns", "type_token": "list[str]", "value": null, "default": null}
        ],
        "ports": [
          {"id": "p3-in", "name": "frame", "direction": "in", "data_type": "DataFrame", "cardinality": "one"},
          {"id": "p3-out", "name": "summary", "direction": "out", "data_type": "DataFrame", "cardinality": "one"}
        ],
        "position": {"x": 520.0, "y": 0.0},
        "group_id": null
      },
      {
        "id": "n4",
        "type": "viz.plot",
        "label": "Plot",
        "paradigm": "functional",
        "params": [
          {"name": "chart", "type_token": "str", "value": "histogram", "default": null},
          {"name": "encoding", "type_token": "dict[str, any]", "value": {"x": "score"}, "default": {}},
          {"name": "options", "type_token": "dict[str, any]", "value": {}, "default": {}}
        ],
        "ports": [
          {"id": "p4-in", "name": "frame", "direction": "in", "data_type": "DataFrame", "cardinality": "one"},
          {"id": "p4-out", "name": "plot", "direction": "out", "data_type": "PlotSpec", "cardinality": "one"}
        ],
        "position": {"x": 520.0, "y": 160.0},
        "group_id": null
      }
    ],
    "add_edges": [
      {
        "id": "e2",
        "source": {"node_id": "n1", "port_id": "p1"},
        "target": {"node_id": "n3", "port_id": "p3-in"}
      },
      {
        "id": "e3",
        "source": {"node_id": "n3", "port_id": "p3-out"},
        "target": {"node_id": "n4", "port_id": "p4-in"}
      }
    ],
    "description": "Add parallel describe + series histogram chart",
    "author": "emergent-flow-collaborator"
  }'
# {"id":"prop-1","status":"pending","diagnostics":{"diagnostics":[],"edge_compatibility":{"e1":true,"e2":true,"e3":true}},"base_version":0,...}
```

The server validated the proposal on submission — clean diagnostics, status `pending`.

### 7. The human accepts the proposal

```bash
curl -s -X POST http://127.0.0.1:8765/sessions/sess-abc123/proposals/prop-1/accept
# {"id":"sess-abc123","version":1,"graph":{"nodes":{"n1":{...},"n2":{...},"n3":{...},"n4":{...}},"edges":{"e1":{...},"e2":{...},"e3":{...}},...},"proposals":{}}
```

Version incremented from 0 to 1; the accepted graph now has all four nodes.

### 8. Accepted graph compiles to ruff-clean Python

```bash
curl -s -X POST http://127.0.0.1:8765/compile \
  -H 'Content-Type: application/json' \
  -d '{
    "paradigm": "functional",
    "nodes": { "n1": ..., "n2": ..., "n3": ..., "n4": ... },
    "edges": { "e1": ..., "e2": ..., "e3": ... }
  }'
# {"code":"import emergentflow as ef\n\n\ndef main():\n    ...\n"}
```

The emitted module passes `ast.parse` and `ruff check --stdin-filename generated.py -`.

### 9. Accepted graph executes to real results

```bash
curl -s -X POST http://127.0.0.1:8765/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "paradigm": "functional",
    "nodes": { "n1": ..., "n2": ..., "n3": ..., "n4": ... },
    "edges": { "e1": ..., "e2": ..., "e3": ... }
  }'
# {"statuses":{"n1":{"status":"ok"},"n2":{"status":"ok"},"n3":{"status":"ok"},"n4":{"status":"ok"}},"results":{"n1":{"frame":{"kind":"table",...}},"n2":{"summary":{"kind":"table",...}},"n3":{"summary":{"kind":"table",...}},"n4":{"plot":{...}}}}
```

Every node executed successfully (`"status": "ok"`). The load CSV, both describe summaries,
and the histogram chart all returned real, inspectable artifacts.
