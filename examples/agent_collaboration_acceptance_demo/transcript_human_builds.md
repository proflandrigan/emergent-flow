# Human builds, agent reviews — call sequence transcript

This file is a **human-readable rendering** of the exact call sequence
`tests/test_acceptance_demo_human_builds.py::test_human_builds_and_agent_reviews_then_fixed_graph_compiles_and_executes`
executes and asserts against. The pytest file is the authoritative, CI-enforced source of truth;
this transcript documents the flow for reference.

The "agent" is the test itself — a plain HTTP client (FastAPI `TestClient`) playing the
`data_modeller` persona following the Review workflow in
[`agents/emergent-flow-collaborator.md`](../../agents/emergent-flow-collaborator.md), and the
human too is just the test applying the fix. No LLM, no live network.

---

### 1. Human creates a session with a single-node ingest using a stale encoding

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
          {"name": "encoding", "type_token": "str", "value": "latin-1", "default": "utf-8"}
        ],
        "ports": [
          {"id": "p1", "name": "frame", "direction": "out", "data_type": "DataFrame", "cardinality": "one"}
        ],
        "position": {"x": 0.0, "y": 0.0},
        "group_id": null
      }
    },
    "edges": {}
  }'
# {"id":"sess-xyz789","graph":{...},"version":0,"proposals":{}}
```

### 2. The reviewer posts an INFO finding (observation, no fix needed)

```bash
curl -s -X POST http://127.0.0.1:8765/sessions/sess-xyz789/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "author": "data_modeller",
    "findings": [
      {
        "severity": "info",
        "code": "grain_check",
        "message": "Single-node ingest -- grain is trivially one row per source row.",
        "node_id": "n1",
        "source": "data_modeller"
      }
    ]
  }'
# {"id":"rev-1","author":"data_modeller","findings":[{"severity":"info","code":"grain_check","message":"Single-node ingest -- grain is trivially one row per source row.","node_id":"n1","source":"data_modeller"}],"comments":[],"fix":null,"status":"open"}
```

The thread is `open`, `fix` is `null` — this is purely informational.

### 3. The reviewer posts a WARNING finding with a mechanical fix attached

The `data_modeller` persona flags the stale `encoding` and attaches a `GraphMutation` that
changes `n1`'s `encoding` param to `"utf-8"`.

```bash
curl -s -X POST http://127.0.0.1:8765/sessions/sess-xyz789/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "author": "data_modeller",
    "findings": [
      {
        "severity": "warning",
        "code": "encoding_stale",
        "message": "encoding is pinned to latin-1; recommend utf-8.",
        "node_id": "n1",
        "source": "data_modeller"
      }
    ],
    "fix": {
      "base_version": 0,
      "set_params": {"n1": {"encoding": "utf-8"}},
      "description": "Pin CSV encoding to utf-8 explicitly",
      "author": "data_modeller"
    }
  }'
# {"id":"rev-2","author":"data_modeller","findings":[{"severity":"warning","code":"encoding_stale","message":"encoding is pinned to latin-1; recommend utf-8.","node_id":"n1","source":"data_modeller"}],"comments":[],"fix":{"base_version":0,"set_params":{"n1":{"encoding":"utf-8"}},...},"status":"open"}
```

This thread carries a `fix` — the canvas's "Apply fix" button can turn it into a proposal with
zero additional server calls.

### 4. The human replies on the warning thread

```bash
curl -s -X POST http://127.0.0.1:8765/sessions/sess-xyz789/reviews/rev-2/comments \
  -H 'Content-Type: application/json' \
  -d '{
    "author": "human",
    "text": "Good catch, applying now."
  }'
# {"id":"rev-2","author":"data_modeller","findings":[...],"comments":[{"author":"human","text":"Good catch, applying now."}],"fix":{...},"status":"open"}
```

### 5. The human turns the fix into a proposal (ordinary proposal machinery)

No separate "apply" endpoint — the fix's `GraphMutation` object is posted directly as a proposal:

```bash
curl -s -X POST http://127.0.0.1:8765/sessions/sess-xyz789/proposals \
  -H 'Content-Type: application/json' \
  -d '{
    "base_version": 0,
    "set_params": {"n1": {"encoding": "utf-8"}},
    "description": "Pin CSV encoding to utf-8 explicitly",
    "author": "data_modeller"
  }'
# {"id":"prop-1","status":"pending","diagnostics":{"diagnostics":[],"edge_compatibility":{}},...}
```

Clean diagnostics — the fix is valid.

### 6. The human accepts the proposal

```bash
curl -s -X POST http://127.0.0.1:8765/sessions/sess-xyz789/proposals/prop-1/accept
# {"id":"sess-xyz789","version":1,"graph":{"nodes":{"n1":{"params":[{"name":"encoding","value":"utf-8"},...]}},...}}
```

Version incremented to 1; `n1`'s `encoding` param is now `"utf-8"`.

### 7. The fixed graph re-validates clean

```bash
curl -s -X POST http://127.0.0.1:8765/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "paradigm": "functional",
    "nodes": { "n1": { ... "encoding": "utf-8" ... } },
    "edges": {}
  }'
# {"diagnostics":{"diagnostics":[],"edge_compatibility":{}}}
```

### 8. The fixed graph compiles to ruff-clean Python

```bash
curl -s -X POST http://127.0.0.1:8765/compile \
  -H 'Content-Type: application/json' \
  -d '{
    "paradigm": "functional",
    "nodes": { "n1": { ... "encoding": "utf-8" ... } },
    "edges": {}
  }'
# {"code":"import emergentflow as ef\n\n\ndef main():\n    frame = ef.data.load_csv('examples/vertical_slice/sample.csv', encoding='utf-8')\n    return {'n1': {'frame': frame}}\n"}
```

The emitted module passes `ast.parse` and `ruff check --stdin-filename generated.py -`.

### 9. The fixed graph executes to real results

```bash
curl -s -X POST http://127.0.0.1:8765/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "paradigm": "functional",
    "nodes": { "n1": { ... "encoding": "utf-8" ... } },
    "edges": {}
  }'
# {"statuses":{"n1":{"status":"ok"}},"results":{"n1":{"frame":{"kind":"table",...}}}}
```

The single load_csv node succeeded — the CSV loaded with the corrected encoding.
