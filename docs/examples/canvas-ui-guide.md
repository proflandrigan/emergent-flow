# Canvas UI Guide

The visual canvas for building and executing pipelines without writing code. The canvas is a
React app served by `emergentflow serve`; it talks to the server only over localhost REST/SSE
and never imports the `emergentflow` Python package (ADR 0013). See
[Getting Started](getting-started.md) for installation and your first SDK pipeline.

## 1. Launching the Server

```bash
emergentflow serve                     # opens browser at http://127.0.0.1:8765
emergentflow serve --no-browser        # headless
emergentflow serve --port 9000         # custom port
emergentflow lab                       # alias for serve
```

| Flag | Default | Purpose |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8765` | Bind port |
| `--no-browser` | off | Don't auto-open a browser tab |
| `--cache-dir` | `.ef-cache` (under the current working directory) | On-disk execution cache location |
| `--cache-max-mb` | `500` | Execution cache size cap in MB, LRU-evicted above this |

This boots a Uvicorn server serving both the REST/SSE API and the bundled canvas at `/`. Verify
it's up:

```bash
curl http://127.0.0.1:8765/healthz    # {"status":"ok"}
```

Stop it with Ctrl-C. Note: binding to any host other than `127.0.0.1` requires a session bearer
token (via `EMERGENTFLOW_SESSION_TOKEN`) before the agent-collaboration `/sessions/*` routes
will accept requests — the localhost default keeps them open, matching every other route's
trusted-local-app model.

## 2. Canvas Layout

#### Palette (left panel)
- Search or click a node type to add it to the canvas at an auto-offset position
- Nodes are organized by family (data, clean, stats, ml, viz, etc.)
- Click-to-add only — there's no drag-and-drop from the palette

#### Canvas (center)
- Drag nodes to reposition
- Drag from an OUT port (right side of a node) to an IN port (left side) to connect
- Right-click a node for **Run to here** (executes only that node's upstream chain)

#### Inspector (right panel)
Three tabs for the selected node:
- **Config** — parameter form (e.g., file path, target column, estimator type)
- **Code** — live-compiled Python for the current graph (`ef.compile_to_code` output, updates
  as you edit)
- **Results** — last execution output per OUT port, or the error message if it failed

## 3. Toolbar

The header toolbar has two direct button groups plus an overflow ("...") menu for less
frequent actions:

| Button | Action |
|---|---|
| Export | Save the current graph as an IR JSON file (`graph.json`) |
| Import | Load an IR JSON file back onto the canvas |
| Download .py | Compile the current graph server-side and download the generated `graph.py` |
| Execute | Run the whole graph via streaming SSE (`/execute/stream`) |
| Clear cache | Empty the on-disk execution cache |
| Undo / Redo | Canvas edit history (`Cmd/Ctrl-Z` / `Cmd/Ctrl-Shift-Z`; native undo applies instead inside text inputs) |

The overflow menu additionally holds theme switching, **Manage connections**, **Browse
schema**, and **Start chat** / **Open chat** (see §7 and §8 below) — these are one level down
from the primary toolbar since they're used less often than Export/Execute.

There is no server-side save yet — Export is how you persist a graph between sessions.

## 4. Building a Pipeline

Step-by-step walkthrough:

1. **Add a data source**: Click `load_sample` in the palette. In the Config tab, set `name` to
   `"iris"`.
2. **Add a cleaning step**: Click `impute_missing`. Drag from `load_sample`'s `frame` OUT port
   to `impute_missing`'s `frame` IN port.
3. **Add analysis**: Click `describe`. Connect `impute_missing` → `describe`.
4. **Add a model**: Click `fit_estimator` (or `train_classifier`-style node). Connect the data
   source. Configure `estimator` and `target` in Config.
5. **Execute**: Click **Execute** in the toolbar. Watch node borders change color, and the
   header's "Running node N of M" progress update live, as each node completes.

## 5. Execution Feedback

#### Node Border Colors
| Color | Meaning |
|---|---|
| Grey | Not yet run |
| Green | Completed successfully |
| Blue | Served from cache (also shows a cached badge) |
| Red | Error |
| Light grey | Skipped |

#### Incremental Execution
Re-running after changing one node's parameters re-executes only that node and its downstream
dependents. Untouched upstream nodes serve cached results — this is DAG-aware incremental
execution backed by the on-disk execution cache (`--cache-dir`).

#### Inline Results
A **▸ results** toggle appears on each node once it has output — expands an inline preview of
each OUT port's payload without needing the Inspector.

## 6. REST API (Headless Use)

The same operations available in the canvas can be driven via REST — every request carries the
whole graph IR, and every route is stateless:

```bash
# Validate a graph
curl -X POST http://127.0.0.1:8765/validate \
  -H "Content-Type: application/json" --data @my_graph.json

# Execute a graph
curl -X POST http://127.0.0.1:8765/execute \
  -H "Content-Type: application/json" --data @my_graph.json

# Compile to Python (no execution)
curl -X POST http://127.0.0.1:8765/compile \
  -H "Content-Type: application/json" --data @my_graph.json

# Get the node catalog
curl http://127.0.0.1:8765/catalog

# Get the IR JSON Schema
curl http://127.0.0.1:8765/schema
```

`/execute/stream` is the SSE variant of `/execute` — it's what the canvas's Execute button
uses under the hood for live per-node progress.

## 7. Connection Manager

The canvas includes a connection manager for configuring data warehouse and LLM connections:
- Access it via the header's overflow menu (**Manage connections**)
- Profiles are stored in `~/.config/emergentflow/connections.toml` — coordinates and auth
  metadata only, never a credential value
- Test a connection before wiring a node to it

```bash
# List connections via API
curl http://127.0.0.1:8765/connections

# Test a connection
curl -X POST http://127.0.0.1:8765/connections/my_postgres/test
```

**Browse schema**, next to it in the same menu, lets you explore a warehouse connection's
relations/columns before building a query node against it.

## 8. Agent Collaboration (Optional)

The canvas includes an in-app agent chat panel for AI-assisted graph building, opened from the
header's overflow menu (**Start chat** / **Open chat**):
- Agents can propose graph mutations that you review before applying
- Supports Claude, Gemini, Codex, and OpenCode adapters
- Completely optional — the canvas works without agents, and no session is opened unless you
  start one

See the [Agent Integration guide](../agent-integration.md) for the full agent-facing protocol.

## 9. Developing the UI

For contributors editing the React source:
```bash
cd ui
npm ci
npm run dev          # Vite dev server with hot reload, proxies API calls to :8765
```
Run `emergentflow serve` in another terminal so the dev server has an API to talk to.

## 10. Tips

- **Export your work** — there's no server-side save yet; use Export to save your graph as JSON
- **Keyboard shortcuts** — Undo: `Cmd/Ctrl-Z`, Redo: `Cmd/Ctrl-Shift-Z` (except inside text
  inputs, where native undo applies)
- **Example graphs** — `examples/functional_pipeline.json` and `examples/declarative_module.json`
  ship with the repo; Import them to get started quickly
