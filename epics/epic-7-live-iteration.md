# Epic 7 — Live Iteration & Visual Results

> **Repo ↔ roadmap numbering.** This file is repo **Epic 7**. It covers the happy-path slices
> of three roadmap epics:
> - **Roadmap Epic 6** (Backend Execution Runtime) — remaining repo Epic 4 stories: FastAPI
>   upgrade, streaming progress, run granularity.
> - **Roadmap Epic 7** (DAG Caching & Incremental State Management) — on-disk execution cache.
> - **Roadmap Epic 8** (Result Rendering & In-Node Visualization) — figure/HTML payload kinds,
>   Inspector Results tab.
>
> The node library (repo Epic 6 / roadmap Epic 4) widened the catalog to a real end-to-end
> DS/ML pipeline. This epic makes that pipeline feel *live*: visual outputs render in the
> canvas, long jobs stream progress instead of freezing, and tweaking one node only re-runs
> what changed.

**Phase:** 2 (Living Bridge — happy-path local slice).
**Lives in:** `emergentflow/server/` (Stories 1, 3, 5, 6) + `ui/` (Stories 2, 4, 5) + `emergentflow/` payload contract (Story 1).
**Coupling:** the canvas never imports `emergentflow`; results flow over the `/execute` REST+SSE endpoints as the existing payload contract (extended here with `image` and `html` kinds).
**Dependencies:** repo Epics 1–6 complete. The payload contract (`server/payload.py`), `PayloadView.tsx`, `executionStore.ts`, and `EfNode.tsx` result panel all landed in earlier epics and are the foundation this epic builds on.
**Blocks:** roadmap Epic 10 (DL shape inference needs a live server that streams); roadmap Epic 11 (GenAI token-flow viz needs streaming).

---

## Where things stand entering this epic

Several pieces are already in place and are **not** re-built here:

- `server/payload.py` — `to_payload()` handles `DataFrame`, scalars, dataclasses, Pydantic,
  JSON containers, and unknown types. Contract version is `1`.
- `ui/src/inspector/PayloadView.tsx` — renders `scalar`, `text`, `table`, `record`, `json`,
  `unsupported`. Deliberately kept raw (the comment says "rich tables/charts are roadmap
  Epic 8 — this is deliberately raw output").
- `ui/src/canvas/nodes/EfNode.tsx` — already has a collapsible `▸/▾ results` toggle that
  renders all OUT-port payloads via `PayloadView`; status coloring (green/red/grey) already
  works.
- `ui/src/io/IRToolbar.tsx` + `irFile.ts` — Export/Import IR JSON is fully functional
  (project persistence is done at the canvas level).
- `ui/src/store/executionStore.ts` — tracks `results: Record<nodeId, Record<portName,
  Payload>>` and `statuses: Record<nodeId, NodeRunStatus>`.
- The server is still stdlib `http.server` (synchronous, no streaming).

---

## Definition of Done (epic-level)

- [ ] A matplotlib figure, a pandas Series, and a sweetviz/ydata-profiling HTML report each
  render visually inside the canvas without a workaround.
- [ ] The Inspector has a **Results tab** that shows all output-port payloads for the selected
  node — users never have to hunt for the in-node toggle.
- [ ] `emergentflow serve` boots a **FastAPI/Uvicorn** server; the four existing endpoints
  (`/compile`, `/validate`, `/execute`, `/healthz`) are unchanged in contract.
- [ ] Executing a graph streams per-node progress back to the canvas in real time — the UI
  never shows a frozen "Running…" state for more than one node's execution time.
- [ ] A **"Run to here"** button on any node executes only that node's upstream chain, enabling
  fast iteration on downstream nodes without re-running the full pipeline.
- [ ] Changing a node's parameters and re-running only re-executes that node and its
  dependents; upstream nodes that haven't changed serve their result from cache. A 💾 badge
  distinguishes cached from freshly-executed nodes.
- [ ] All four CI gates pass (`ruff`, `mypy`, `pytest`, `vitest`). No regressions against the
  existing golden corpus or the acceptance demo.

---

## Story 1 — Visual payload extensions

> `to_payload()` currently returns `{"kind": "unsupported"}` for matplotlib figures, and
> returns a bare `{"kind": "scalar"}` for a pandas Series (casting it via `repr`). These are
> the most common visual outputs from DS/ML nodes.

**Python / server side (`emergentflow/server/payload.py`, `PAYLOAD_CONTRACT_VERSION` → 2):**

- [ ] **Matplotlib figure → PNG.** Detect `matplotlib.figure.Figure` (lazy import; never
  import matplotlib at module load): call `fig.savefig(buf, format="png", bbox_inches="tight")`,
  base64-encode the bytes, return `{"kind": "image", "mime": "image/png", "data": "<b64>",
  "width": int, "height": int}`. The figure is **not** closed by `to_payload`; the caller owns
  it. Cap image data at 2 MB; return `{"kind": "unsupported", ...}` if the PNG exceeds the cap.
- [ ] **Pandas Series → table.** A `pd.Series` is column-shaped data; render it like a
  single-column DataFrame (`{"kind": "table", ...}`) with the series name as the column header,
  capped at `MAX_HEAD_ROWS`.
- [ ] **HTML string → embeddable report.** When `to_payload` receives a string that starts
  with `<!DOCTYPE html` or `<html` (case-insensitive), emit `{"kind": "html", "value":
  "<the full html>", "truncated": false}` (no `MAX_TEXT_CHARS` cap — reports can be 3–5 MB;
  the canvas decides how to render them). Strings that don't look like HTML continue to use
  the existing `scalar`/`text` path.
- [ ] Bump `PAYLOAD_CONTRACT_VERSION` to `2` and document the two new kinds in the module
  docstring.
- [ ] Add unit tests for each new kind (figure, Series, HTML string) in
  `tests/test_server_payload.py`.

**Canvas side (`ui/src/inspector/PayloadView.tsx`, `ui/src/store/execution.ts`):**

- [ ] Extend the `Payload` union type with `ImagePayload` and `HtmlPayload`.
- [ ] `PayloadView` handles `image`: renders an `<img src={"data:image/png;base64," + data} …>`
  constrained to `max-width: 100%; max-height: 300px`.
- [ ] `PayloadView` handles `html`: renders an `<iframe srcdoc={value} sandbox=""
  style={{width:"100%", height:400, border:"none"}} />`. The `sandbox=""` attribute blocks
  scripts, navigation, and form submission — the report is display-only.
- [ ] Vitest snapshot or render tests for both new variants.

---

## Story 2 — Inspector Results tab

> The in-node `▸/▾ results` toggle works but requires zooming in and expanding each node
> individually. A dedicated Results tab in the Inspector gives instant access to the selected
> node's outputs without hunting around the canvas.

- [ ] Add a `"results"` tab to `Inspector.tsx` (third tab: Config | Code | **Results**).
- [ ] The Results tab shows all OUT-port payloads for the selected node, each labelled by port
  name, rendered via `PayloadView`.
- [ ] Empty states:
  - No node selected → "Select a node to see its results."
  - Node selected, no results yet → "No results — run the graph first."
  - Node executed with an error → show the error string from `statuses[nodeId]`.
- [ ] A "last run: Ns ago" timestamp in the tab header (derived from a `lastRunAt: number`
  field added to `ExecutionStore`).
- [ ] Vitest tests for each empty state and the payload-populated state.

---

## Story 3 — FastAPI server upgrade

> The stdlib `http.server` is synchronous and single-threaded. A 30-second random-forest
> training call blocks the entire server — no `/healthz` pings, no parallel compile calls.
> FastAPI + Uvicorn gives async I/O, proper error handling, and the SSE endpoint Story 4 needs.

**`emergentflow/server/` changes:**

- [ ] Add `fastapi` and `uvicorn[standard]` to `pyproject.toml` (optional dep group
  `server`; already implicit since `emergentflow serve` is the product). Pin minimum versions.
- [ ] Rewrite `app.py` as a FastAPI `app` with `@app.post` / `@app.get` handlers. Keep the
  exact same URL paths and JSON shapes so the canvas needs no changes:
  - `POST /compile` → `CompileResponse`
  - `POST /validate` → `ValidateResponse`
  - `POST /execute` → `ExecuteResponse` (sync for now; Story 4 adds SSE)
  - `GET /healthz` → `{"status": "ok"}`
- [ ] Rewrite `service.py` helpers as async-safe pure functions (they already call pure SDK
  functions, so this is mostly `async def` + `run_in_executor` for the CPU-bound execute call
  to keep the event loop free).
- [ ] Add `GET /reports/{report_hash}` endpoint: the execute path stores HTML blobs in a
  temporary dir keyed by `sha256(html_bytes)[:16]`; this endpoint serves them with
  `Content-Type: text/html`. The canvas can use this as an alternative to `srcdoc` for
  large reports.
- [ ] Update `emergentflow/cli.py` `serve` command to call `uvicorn.run(app, host=..., port=...)`.
- [ ] Update `tests/test_server.py` to use `httpx.AsyncClient` (FastAPI's test client). All
  existing round-trip tests must still pass.

---

## Story 4 — Streaming execution progress

> With the FastAPI server in place, add an SSE stream so the canvas shows per-node progress
> in real time instead of a frozen "Running…" state until the whole graph finishes.

**Server side:**

- [ ] Add `POST /execute/stream` that accepts the same body as `/execute` and returns
  `text/event-stream`. The event protocol is simple:
  ```
  data: {"type": "node_start",  "node_id": "...", "label": "..."}
  data: {"type": "node_ok",     "node_id": "...", "elapsed_ms": 123, "results": {...}}
  data: {"type": "node_error",  "node_id": "...", "elapsed_ms": 123, "error": "..."}
  data: {"type": "run_complete","total_ms": 456}
  data: {"type": "run_error",   "error": "..."}
  ```
- [ ] The existing `/execute` endpoint stays unchanged (canvas Story 8-era non-streaming path
  remains valid; streaming is opt-in).
- [ ] Add server-side tests for the SSE event sequence on a two-node graph.

**Canvas side:**

- [ ] Replace the `ExecutionToolbar.tsx` `/execute` fetch with `/execute/stream` using the
  browser's `EventSource` API (or `fetch` + `ReadableStream` for POST — `EventSource` is
  GET-only; use `fetch` + `getReader()` for SSE over POST).
- [ ] `executionStore` gains `setNodeStart(nodeId)` and uses `setResult`/`setError` per-node
  as events arrive, so `EfNode` status colors update in real time.
- [ ] Progress counter in `ExecutionToolbar`: "Running node 2 of 5 (LoadCSV…)" using a
  `progress: {current: number, total: number, label: string} | null` field in the store.
- [ ] Vitest: mock the SSE stream and assert per-event store updates.

---

## Story 5 — Run granularity: "Run to here"

> Running the full pipeline to inspect an intermediate result is wasteful once caching
> exists (Story 6). "Run to here" executes only the subgraph up to and including a target node.

**Server side:**

- [ ] Extend the `/execute` (and `/execute/stream`) request body with two optional fields:
  ```json
  { "graph": ..., "run_mode": "all" | "to_here", "target_node_id": "..." }
  ```
  Default: `run_mode = "all"`, `target_node_id = null`.
- [ ] In `service.py`, when `run_mode == "to_here"`, prune the topo-sorted execution list to
  only the nodes that are ancestors of (and including) `target_node_id`. Use the existing
  `traversal.py` topo-sort and wiring; add a `ancestors_of(graph, node_id) -> set[str]`
  helper in `traversal.py`.
- [ ] Test: a three-node chain where "run to here" on the middle node skips the third.

**Canvas side:**

- [ ] Add a right-click context menu to `EfNode`: single item "Run to here ▸". On click,
  `POST /execute/stream` with `run_mode: "to_here", target_node_id: <this node's id>`.
- [ ] The existing "Execute" toolbar button continues to use `run_mode: "all"`.
- [ ] Vitest: assert the context menu item fires the correct request body.

---

## Story 6 — DAG caching & incremental execution

> The "edit one param → full re-run" cycle is the biggest productivity bottleneck on
> non-trivial datasets. A hash-keyed on-disk cache lets the server skip unchanged upstream
> nodes entirely.

**Design decisions (settle before implementing):**

- [ ] **Hash inputs:** `sha256(canonical_json(node_params) + sorted(upstream_output_hashes) +
  emergentflow.__version__)`. "Canonical JSON" is `json.dumps(params, sort_keys=True,
  separators=(",", ":"))`. The upstream hash of a node is the hash of *its own hash plus its
  upstream hashes*, so the hash transitively covers the entire upstream chain.
- [ ] **Artifact store:** `.ef-cache/` in the current working directory (where
  `emergentflow serve` was started). Configurable via `--cache-dir` CLI flag. Each artifact
  is a single file: `<hash>.pkl` for Python objects (pickle), with a `<hash>.meta.json`
  sidecar holding the node id, label, SDK version, and a timestamp. `torch` objects use
  `safetensors` if available, falling back to pickle.
- [ ] **Eviction:** LRU by `mtime`. On startup (or on demand), if the cache dir exceeds a
  configurable `--cache-max-mb` (default 500 MB), evict the oldest artifacts until under the
  cap.
- [ ] **What is never cached:** nodes that explicitly declare `cacheable = False` on their
  `NodeDefinition`. Deferred: non-deterministic LLM nodes (roadmap Epic 11).

**Python / server side:**

- [ ] Implement `emergentflow/server/cache.py`: `ExecutionCache` with `get(hash) ->
  dict[str, Any] | None` and `put(hash, outputs: dict[str, Any])`. Encapsulates artifact
  serialization, the `.meta.json` sidecar, and LRU eviction.
- [ ] Wire into the execute path in `service.py`: before executing a node, compute its hash,
  check the cache. On hit, use stored outputs and mark `status = "cached"`. On miss, execute
  and store.
- [ ] Extend the per-node status type to include `"cached"` (alongside existing `"ok"`,
  `"error"`, `"skipped"`).
- [ ] Add `POST /cache/clear` endpoint: removes all files from the cache dir.
- [ ] Property tests (`pytest`): (a) identical graph → identical hashes; (b) changing any
  param → different hash; (c) changing SDK version → different hash; (d) a second run with an
  unchanged upstream returns `status: "cached"` for that node.

**Canvas side:**

- [ ] `NodeRunStatus` type gains `"cached"`.
- [ ] `borderColorFor` in `EfNode.tsx` maps `"cached"` → a muted teal (e.g. `#0288d1`) to
  distinguish from fresh `"ok"` (green).
- [ ] Add a 💾 badge (small icon, bottom-right of node) when status is `"cached"`.
- [ ] Add a "Clear cache" button to `ExecutionToolbar` (calls `POST /cache/clear`, then
  re-enables the Execute button).
- [ ] Vitest: cached status renders the teal border and 💾 badge.

---

## Notes / Risks

- **`safetensors` vs. pickle for sklearn models.** Sklearn models don't have a native
  safetensors serializer; pickle is the standard. Accept this for the local app (trusted
  code, Jupyter trust model per ADR 0013 §A6). Document the pickle dependency in a comment on
  `ExecutionCache`; the hosted sandbox (roadmap Epic 6 hosted) will need a different
  serialization strategy.
- **Matplotlib `show()` / `plt.gcf()` pattern.** Node `execute()` functions must return the
  figure explicitly (as a port output) for `to_payload` to see it. The `report.py` node
  already returns HTML as a string. Audit `evaluate.py` and any stat-test nodes that call
  `plt.show()` instead of returning the figure; update them to return the `Figure` object.
- **`srcdoc` size limit.** Browsers have a practical `srcdoc` limit around 2 MB. The
  `/reports/<hash>` endpoint (Story 3) is the fallback for larger reports — `PayloadView`
  should use `srcdoc` below 1 MB and an `<iframe src="/reports/<hash>">` above it. Wire the
  report hash into the HTML payload if Story 3 is shipped first.
- **Cache correctness is a trust issue.** A stale cache hit (same hash, wrong result) is
  worse than a cache miss. Invest in the property tests before shipping to users. Prefer false
  cache-miss (re-run unnecessarily) over false cache-hit (serve wrong result).
- **Sequencing:** Stories 1 and 2 are independent of each other and of the server upgrade.
  Story 3 (FastAPI) is a prerequisite for Stories 4 (streaming) and 5 (run granularity via
  the SSE body extension). Story 6 (caching) requires Stories 3 + 5 (it needs the server's
  execute path to exist in its FastAPI form, and it adds the `"cached"` status the run-
  granularity tests rely on). Recommended order: 1 → 2 (parallel) → 3 → 4 → 5 → 6.
- **The stdlib server is still used in tests.** `tests/test_server.py` currently imports the
  stdlib handler directly. Story 3 must migrate these tests to FastAPI's `TestClient` /
  `httpx.AsyncClient`; the test file will be largely rewritten.
