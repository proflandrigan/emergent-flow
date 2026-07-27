# Runbook — Launching & Using the App

This is the practical "how do I run this thing" doc. For what the pipeline demonstrates, see
[acceptance-demo.md](./acceptance-demo.md); for the architecture, see the [README](../README.md)
and [ADR 0013](./adr/0013-single-repo-bundled-ui-topology.md).

## 1. Install

From a clone, using [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --locked
```

This installs the pinned dev environment, including the `server` extra (FastAPI/Uvicorn) and
the test/lint toolchain. If you're installing the published package instead of working in the
repo, the server transport is optional and must be requested explicitly:

```bash
pip install emergentflow           # SDK only — ef.compile_to_code / ef.execute, no canvas
pip install 'emergentflow[server]' # + emergentflow serve
```

A bare install without the `server` extra still works for `import emergentflow as ef` /
codegen use; `emergentflow serve` will print an install hint and exit 1 if FastAPI/Uvicorn
are missing rather than a raw traceback.

The canvas UI (`ui/`) is prebuilt and bundled into the wheel at `emergentflow/_static/` — you
do not need Node.js installed to *use* the app, only to *develop* the UI (see §5).

## 2. Launch

```bash
uv run emergentflow serve
```

`lab` is an alias for `serve` (the JupyterLab-style launch verb):

```bash
uv run emergentflow serve --no-browser --port 8765
```

Flags:

| Flag | Default | Purpose |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8765` | Bind port |
| `--no-browser` | off | Don't auto-open a browser tab |
| `--cache-dir` | `.ef-cache` (cwd) | On-disk execution cache location |
| `--cache-max-mb` | `500` | LRU cache size cap |

This boots a Uvicorn server serving both the REST/SSE API and the bundled canvas at `/`.
Verify it's up:

```bash
curl http://127.0.0.1:8765/healthz   # {"status":"ok"}
```

Stop it with Ctrl-C (or kill the process if backgrounded).

## 3. Using the canvas

Open `http://127.0.0.1:8765/` (auto-opens unless `--no-browser`). The layout, left to right:

- **Palette** (left) — search/click a node to add it to the canvas at an auto-offset position.
  Click-to-add only; there's no drag-and-drop from the palette.
- **Canvas** (center) — drag nodes to reposition, drag from an OUT port (right side) to an IN
  port (left side) to connect. Right-click a node for **Run to here**, which executes only that
  node's upstream chain.
- **Inspector** (right) — three tabs for the selected node:
  - **Config** — the node's parameter form.
  - **Code** — live-compiled Python for the current graph (`ef.compile_to_code` output).
  - **Results** — the selected node's last-execution output per OUT port, or the error message
    if it failed.

Header toolbar (left to right):

- **Export / Import** — save the current graph as IR JSON, or load one back in. Use this for
  project persistence — there's no server-side save yet.
- **Download .py** — compiles the current graph server-side and downloads the generated
  `graph.py`.
- **Execute** — runs the whole graph via streaming SSE; each node's border color and the
  header's "Running node N of M" progress update live as results arrive, instead of freezing
  until the whole graph finishes.
- **Clear cache** — empties the on-disk execution cache (`--cache-dir`).
- **Undo / Redo** — canvas edit history (`Cmd/Ctrl-Z` / `Cmd/Ctrl-Shift-Z` also work, except
  inside text inputs where native undo applies instead).

Per-node feedback:
- Border color: grey = not run, green = ok, blue = **cached** (also shown as a 💾 badge —
  served from the execution cache rather than freshly executed), red = error, light grey =
  skipped.
- A **▸ results** toggle appears directly on a node once it has output — expands an inline
  preview of each OUT port's payload without needing the Inspector.
- Re-running after only changing one node's parameters re-executes just that node and its
  downstream dependents; untouched upstream nodes serve cached results (this is the DAG
  incremental-execution behavior from Epic 7 Story 6).

## 4. Try it without the UI (API / CLI)

The four REST endpoints are stable regardless of frontend:

```bash
# Validate a graph (structural + edge-compatibility diagnostics)
curl -X POST http://127.0.0.1:8765/validate \
  -H "Content-Type: application/json" --data @examples/functional_pipeline.json

# Execute a graph, get back per-node payloads
curl -X POST http://127.0.0.1:8765/execute \
  -H "Content-Type: application/json" --data @examples/functional_pipeline.json

# Compile a graph to a runnable Python script (no execution)
curl -X POST http://127.0.0.1:8765/compile \
  -H "Content-Type: application/json" --data @examples/functional_pipeline.json
```

Ready-made example graphs live in `examples/` (`functional_pipeline.json`,
`declarative_module.json`, `acceptance_demo/pipeline.json`). `/execute/stream` is the same as
`/execute` but as Server-Sent Events, used by the canvas's Execute button for live progress.

Or skip the server entirely and drive the SDK directly in Python:

```python
import emergentflow as ef
import json

graph = json.load(open("examples/functional_pipeline.json"))
results = ef.execute(graph)          # in-process reference interpreter
code = ef.compile_to_code(graph)     # equivalent generated Python (ADR 0002)
```

The acceptance demo (`examples/acceptance_demo/demo.py`) is the canonical worked example —
`python examples/acceptance_demo/demo.py` runs an 8-node pipeline end to end and writes an
HTML report.

> **Shaping data for recommenders:** see [Recommender data prep](./recommender-data-prep.md) for a
> packed-lists → two-tower walkthrough.

## 5. Developing the UI directly (optional)

Only needed if you're editing `ui/` source rather than just using the app:

```bash
cd ui
npm ci
npm run dev        # Vite dev server with hot reload, proxies API calls to :8765
```

Run `uv run emergentflow serve` in another terminal first so the dev server has an API to talk
to. `npm run build` produces the production bundle consumed by `emergentflow serve`
(`emergentflow/_static/`).

## 6. Verifying your environment

The full CI gate set, runnable locally:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy emergentflow
uv run pytest

cd ui
npm ci
npm run lint
npm run typecheck
npm run build
npm test
```

All of the above are green on `main` as of Epic 7 (live iteration: streaming execution, DAG
caching, visual results).
