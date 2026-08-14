# Remaining Work for Issue #154 — Agent Onboarding Friction

This document captures the **remaining implementation tasks** from
[issue #154](https://github.com/proflandrigan/emergent-flow/issues/154) after an initial
batch was completed in-session (see "Completed" below). Each task below includes the issue
item it addresses, the exact files to touch, and the primary agent's implementation notes
(grounded in code reads of the current HEAD) so a subsequent executor can complete them
without re-deriving context.

## Status legend

- **COMPLETE** — implemented, tested, QA'd in-session.
- **NOT STARTED** — remaining; implementation notes provided below.

---

## Completed (in-session)

| Task | Issue | What shipped |
|------|-------|--------------|
| Task 1 | #4 `connect_ports` same-name port disambiguation | `_find_port` gained a `direction` preference; `connect_ports` now resolves OUT for the source, IN for the target (`emergentflow/collab/mcp.py`). Test `test_connect_ports_prefers_out_for_source_same_named_ports`. |
| Task 2 | #2 `create_session` MCP tool | Added `create_session(graph=None)` MCP tool returning the session doc plus an `open_in_ui` URL (`http://127.0.0.1:8765/?session=<id>`) (`emergentflow/collab/mcp.py`). |
| Task 3 | #3 stdio bridge stringified dict params → 422 | `mcp_bridge._make_wrapper` now `json.loads` any arg whose schema type is `object`/`array` when it arrives as a string (helpers `_collect_schema_types`, `_complex_schema_names`) (`emergentflow/collab/mcp_bridge.py`). |

All three have passing tests and clean `ruff`/`mypy`. These are the only files changed so far
(untracked/working tree), with matching tests in `tests/test_collab_mcp.py` and
`tests/test_mcp_bridge.py`.

---

## Task 4 — Issue #5: `await_verdict` long timeouts exceed the bridge/upstream request timeout

**Status: NOT STARTED**

### Problem
`await_verdict(session_id, proposal_id, timeout_seconds=30.0)` (in
`emergentflow/collab/mcp.py`) long-polls server-side in 1s slices via `q.get(timeout=...)`;
when an agent requests a long `timeout_seconds` (e.g. 180), the call through the **stdio
bridge** fails with `Upstream request timed out, please retry` because the bridge's
`httpx.AsyncClient` has the default 5s timeout.

### Implementation notes (from reading current HEAD)
- `await_verdict` is defined at `emergentflow/collab/mcp.py:404` (body ~416-449). It already
  subscribes before checking status (correct, no race), returns immediately on a resolved
  proposal, else loops until `timeout_seconds` producing `{"status": "timeout", ...}`.
- The bridge is in `emergentflow/collab/mcp_bridge.py`. In `create_bridge_mcp_server` the
  client is created as `client = _http_client or httpx.AsyncClient()` (~line 77). This default
  client has `httpx`'s 5s default timeout — that is the hard cap that kills a long
  `await_verdict`.

### Recommended approach (do these together)
1. **Raise the bridge per-request timeout** so long-poll tools can complete. In
   `create_bridge_mcp_server`, change the default client creation to
   `httpx.AsyncClient(timeout=httpx.Timeout(...))` with a generous connect/read/pool timeout.
   The bridge process is a long-lived stdio server, so a large overall read timeout is safe.
   Reference the exact httpx version in use; a single explicit
   `timeout=120.0` or a `httpx.Timeout(connect=5, read=600, write=10, pool=10)` is
   reasonable. Note tests pass `_http_client` explicitly (an ASGI-backed client), so their
   behavior is unaffected — only the CLI-created default client changes.
2. **Cap `timeout_seconds`** in `await_verdict` itself: clamp it to a documented safe max
   (e.g. `min(timeout_seconds, 600)`) with a ValueError if negative, and document that in the
   docstring. This guarantees a caller cannot request a wait larger than the bridge limit.
3. **Do NOT chunk internally** into multiple `POST /mcp/invoke` round-trips — that changes
   the tool's contract and complicates the proposal query. A long single poll under a raised
   bridge timeout is the intended, simplest behavior.

### Tests
- `tests/test_collab_mcp.py`: add a test asserting `await_verdict` rejects a negative/zero
  `timeout_seconds` with `ValueError`, and that an already-resolved proposal returns
  immediately when the deadline is (effectively) exceeded — i.e. call with a tiny
  `timeout_seconds` on an unresolved proposal and assert `status == "timeout"` fast.
- `tests/test_mcp_bridge.py`: add a test that the default client used by
  `create_bridge_mcp_server` carries the raised read timeout (assert on the created client's
  `_transport` timeout, or refactor to expose the timeout so it's testable). At minimum,
  assert constructing the server with no `_http_client` produces a client whose timeout is
  not the 5s default.
- Run `uv run pytest tests/test_collab_mcp.py tests/test_mcp_bridge.py -q`, `uv run ruff
  check .`, `uv run mypy emergentflow`.

### Out of scope
- Do not change `/mcp/invoke`, the SSE events route, or session store subscribe/unsubscribe.

---

## Task 5 — Issue #7: `serve()` startup banner lacks the session-token hint for non-loopback

**Status: NOT STARTED** (server already prints the URL banner; the token hint is missing)

### Problem
`emergentflow serve` already prints
`Emergent Flow - serving the local canvas at {url}  (Ctrl-C to stop)` (see
`emergentflow/server/app.py`, in `serve()` around line 1362). The remaining gap from #7 is
that for a **non-loopback bind** it gives no hint about the session bearer token, so an agent
doesn't know the token to authenticate to `/sessions*`.

### Implementation notes (from reading current HEAD)
- `serve()` is `emergentflow/server/app.py:1314`. Near the end it does:
  ```python
  browse_host = "127.0.0.1" if host == "0.0.0.0" else host
  url = f"http://{browse_host}:{port}"
  print(f"Emergent Flow - serving the local canvas at {url}  (Ctrl-C to stop)")
  ```
- Earlier in `serve()`, when `host != "127.0.0.1"`, it REQUIRES a token
  (`resolved_token = session_token or os.environ.get("EMERGENTFLOW_SESSION_TOKEN")`) and
  raises if absent, then calls `configure_session_auth(required=True, token=resolved_token)`.
- So `resolved_token` is already computed only in the non-loopback branch. Thread it out so
  the final print can include a hint. Prefer restructuring minimally: after the
  `if host == "127.0.0.1" / else` block, keep a variable like `token_hint` in scope (the
  `resolved_token` is currently a local inside the `else`).

### Recommended change
After the existing auth block, set a variable usable at print time and emit an additional
line when a non-loopback bind is active, e.g.:

```python
    token_hint = ""
    if host != "127.0.0.1":
        token_hint = (
            f"  Session bearer token: {resolved_token}"
            "  (pass it to the agent as its Authorization: Bearer <token> header)"
        )
    print(f"Emergent Flow - serving the local canvas at {url}  (Ctrl-C to stop){token_hint}")
```

Make sure `resolved_token` is defined in a scope visible to this line (compute it once before
the `if/else` rather than only inside the `else` if you can — but keep the existing raise
behavior for missing token intact).

### Tests
- There is no existing unit test target for the printed banner. Add a small test if a
  harness exists for `serve()`'s print (search `tests/` for `serve(` / `capsys`). If none,
  at minimum assert via `capsys` that calling the banner construction path with a non-loopback
  host + token string includes the token. Prefer a unit test that invokes the print logic with
  monkeypatched config rather than actually binding uvicorn.
- Run `uv run ruff check .` and `uv run mypy emergentflow`.

### Out of scope
- Do not change the loopback banner text (it already satisfies "prints URL").
- Do not start/stop a live server in tests.

---

## Task 6 — Issue #1: session discovery — `POST /sessions` returns `open_in_ui`, UI **Join** button

**Status: NOT STARTED**

### Problem
An agent creates a session (via raw HTTP or the new `create_session` MCP tool) but a human
opening `http://127.0.0.1:8765` loads a blank local draft; there's no in-app affordance to
join an existing server session.

### Implementation notes (current HEAD behavior)
- **Server:** `emergentflow/server/app.py:640` `create_session` returns
  `session.model_dump(mode="json")` (no URL). The MCP `create_session` (Task 2) already adds
  `open_in_ui`; mirror that on the HTTP route so `POST /sessions` and `POST /sessions/{id}`
  responses include it too. Add `doc["open_in_ui"] = f"http://127.0.0.1:8765/?session=<id>"` in
  `_create` before returning (or a small helper `_session_json` already wraps; add the field
  in the route).
- **UI:** `ui/src/session/sessionStore.ts` `join(sessionId)` already loads a session, loads
  the IR into the graph store, subscribes to SSE, and sets `applySession`. And App.tsx already
  joins on a `?session=` query param on load.
- **UI list:** `ui/src/connections/CodingAgentsSection.tsx` already fetches `GET /sessions`
  and renders rows (`toSessionSummary`) with an **End session** button — but **no Join**
  button. Add a `Join` button per row that calls `useSessionStore.getState().join(s.id)` and
  ideally closes the connections panel so the canvas shows the joined session.

### Recommended changes
1. `emergentflow/server/app.py` `create_session` `_create`: add `open_in_ui` to the returned
   dict (same URL format as Task 2).
2. `ui/src/connections/CodingAgentsSection.tsx`: import `useSessionStore`; add a `Join` (or
   `Open`) ghost button next to the existing **End session** button that calls
   `join(s.id)` (and optionally sets `connectionsOpen` closed — check how the panel is opened
   from App.tsx; there may be a prop/`onClose` to reuse).
3. Keep the existing `End session`/delete behavior.

### Tests
- Python: extend `tests/test_server_sessions.py` (or whichever file tests `POST /sessions`)
  to assert the response contains `open_in_ui` matching `http://127.0.0.1:8765/?session=<id>`.
- UI: add/extend `ui/src/connections/CodingAgentsSection.test.tsx` to assert a Join button
  renders and calls `join`. Update `ui/src/session/sessionStore.test.ts` if needed.
- Run `uv run pytest -k sessions -q`, `uv run mypy emergentflow`, and in `ui/`:
  `npm run typecheck`, `npm run lint`, `npm test`.

### Out of scope
- Do not change `?session=` URL parsing or the draft/localStorage behavior when no session is
  joined.
- Do not add a session switcher dropdown in the main toolbar (a per-row Join button in the
  Coding Agents section is sufficient for this task).

---

## Task 7 — Issue #6: pending proposals visible on the canvas (proposals review inbox)

**Status: NOT STARTED**

### Problem
Nodes added via `propose_mutation` don't render on the canvas until accepted. There is no
mounted inbox/panel surfacing pending proposals for the human to accept/reject. Investigation
confirmed `ProposalPanel.tsx` and `GhostOverlay.tsx` exist but are **orphaned** (referenced
only by their own tests, never mounted in the app).

### Implementation notes (current HEAD)
- `ui/src/session/ProposalPanel.tsx` exports `function ProposalPanel({...})` and internally
  renders `ProposalCard`s using `computeGhostDiff(model, proposal.mutation)` to preview added
  nodes/edges on a small embedded canvas; inline Accept/Reject buttons are wired to
  `accept(proposal.id)` / `reject(proposal.id)` from `useSessionStore`. It reads proposals via
  `useSessionStore((s) => s.proposals)`.
- `ui/src/session/GhostOverlay.tsx` + `ghostDiff.ts` + `GhostOverlay.test.tsx` implement a
  canvas overlay showing ghosted (added) elements.
- App.tsx renders panels via `{connectionsOpen && (<ConnectionManagerPanel/>)}` etc. (panels
  toggled by state). There is no proposals panel currently mounted.

### Recommended approach (pick one; first is lowest-risk)
1. **Mount ProposalPanel into App.tsx** as a toggleable panel (add a `proposalsOpen` state +
  a toolbar button, mirroring how `connectionsOpen`/`runsOpen` work) so it's reachable from
  the canvas. This is the minimal wiring that makes pending proposals visible with inline
  accept/reject.
2. (Optional, follow-on) Wire `GhostOverlay` to actually ghost pending proposal nodes on the
  main canvas so a human sees the proposed additions in place while reviewing. This is more
  invasive (needs to merge ghost nodes into the rendered graph model); treat as a separate
  enhancement once the inbox is mounted.

### Tests
- Add `ui/src/session/ProposalPanel` mount test in App.tsx (assert the proposals panel renders
  proposals and accept/reject calls through). Extend `ui/src/session/ProposalPanel.test.tsx`
  to cover the mounted case if it currently only tests the component in isolation.
- Run `npm run typecheck`, `npm run lint`, `npm test` in `ui/`.

### Out of scope
- Do not change the proposal accept/reject server logic (`collab/session.py` `add_proposal`
  `/accept_proposal` already publish SSE events the store consumes).
- Do not reimplement `ghostDiff`; reuse it.

---

## Task 8 — Issue #8: persist agent-initiated runs + return a real `run_id` + surface on canvas

**Status: NOT STARTED**

### Problem
When an agent executes a session (`POST /sessions/{id}/execute` or `execute_session_tool`),
`run_id` comes back `None`, the run is not persisted to the run store, the session document
carries no run/result state, and no SSE run event is emitted — so a human watching the canvas
sees nothing change and `get_results(run_id)` has nothing to read.

### Implementation notes (current HEAD)
- `emergentflow/server/service.py` `execute_session(session_id, payload)` (~line 1021) calls
  `execute_graph({"graph": graph_dict, **scope})` and returns its result **without persisting
  to the run store** and without emitting SSE run events.
- `emergentflow/server/runs.py` provides `RunStore.save(run_data, graph_data, payloads_data)
  -> run_id` and `get_default_runs()`. `mcp.py`'s `get_results`/`get_metric` already read from
  `get_default_runs()` — they just have nothing because session runs aren't saved.
- The session store publishes SSE events via `SessionStore._publish(session_id, event)`
  (`emergentflow/collab/session.py`), and the canvas subscribes via
  `ui/src/session/sessionClient.ts` `subscribeToSessionEvents`. Event type unions live in
  `emergentflow/collab/mcp.py` (runtime) and generated
  `ui/src/generated/session_event.ts`.
- `execute_graph` result shape is `{"payload_version", "results", "statuses"}`.

### Recommended approach
1. In `emergentflow/server/service.py`, refactor the tail of `execute_session` (and/or the
   shared `execute_graph`) to:
   - Build `run_data = {"started_at", "duration_ms", "node_count", "tag", "graph_name",
     "payload_version", "statuses"}`,
   - Build `graph_data = session.graph.model_dump(mode="json")` and
     `payloads_data = results`,
   - Call `run_id = get_default_runs().save(run_data, graph_data, payloads_data)`,
   - Return `{"payload_version", "results", "statuses", "run_id": run_id, ...}`.
   - Optionally stash a `last_run: {run_id, statuses}` digest on the session document
     (`collab/session.py` `GraphSession` — but note the epic invariant that collab state lives
     BESIDE the graph; prefer emitting an SSE event over mutating the session model if schema
     churn is a concern).
   - Emit SSE run events on the session channel (e.g. a single `run_completed` frame carrying
     `run_id`, `statuses` summary) via `store`/`_publish`, so subscribed canvases trigger a
     refresh. Keep it additive — do not break the existing `graph_changed` contract.
2. Add the new event type(s) to the runtime union (`emergentflow/collab/mcp.py`'s
   `_SessionEventType` if one exists, or wherever event `type` strings are validated — likely
   a schema in `emergentflow/collab/` serialized to `ui/src/generated/session_event.ts`).
3. Regenerate UI types per CLAUDE.md: `uv run python scripts/export_ui_contracts.py` then
   `npm run gen:types` (and `scripts/check_ui_boundary.py`).
4. On the canvas, handle the new event so a subscribed session refreshes results. The browser's
   own `/execute/stream` holds outputs client-side; for agent runs, the minimal acceptable win
   is that `get_results(run_id)` works and the session refreshes on the new SSE event.

### Tests
- `tests/test_server_runs.py` + a new `tests/test_server_execute_session_run.py` (or extend
  `tests/test_server_sessions.py`): assert that after `POST /sessions/{id}/execute`, a real
  `run_id` is returned, `get_default_runs().get(run_id)` succeeds, and `get_results`/`get_metric`
  can read it back.
- `tests/test_collab_mcp.py`: assert `execute_session_tool` returns a non-null `run_id` and
  that a subsequent `get_results` works.
- SSE: assert a `run_completed` (or similar) event is published to a subscribed queue.
- Run `uv run pytest -q`, `uv run mypy emergentflow`, `uv run ruff check .`, and the UI gates.

### Out of scope
- Do not move node execution into a subprocess here (that is a separate #9/#10 remediation).
- Do not change the `/execute/stream` browser path.

---

## Task 9 — Issue #9: `item_knn_cf` (and `user_knn_cf`) OOM from dense n×n allocations

**Status: NOT STARTED**

### Problem
`recommend.catalog._fit_item_knn_cf` (catalog.py ~1384) and `_fit_user_knn_cf` (~1240)
materialize several dense `n×n` float64 arrays (via `_similarity_matrix`,
`_common_counts`, `_top_k_sparse`), which OOMs the in-process server at tens-of-thousands of
items/users (SIGKILL, kills all sessions).

### Implementation notes (current HEAD)
- `emergentflow/recommend/catalog.py`:
  - `_similarity_matrix(matrix, similarity)` (1176) — cosine via `cosine_similarity` (returns
    dense or sparse? cosine_similarity on sparse returns numpy/scipy — verify; Jaccard branch
    does `(binary @ binary.T).todense()` → dense n×n).
  - `_common_counts(matrix)` (1210) — `np.asarray((binary @ binary.T).todense())` → dense n×n.
  - `_top_k_sparse(sim, k, common, min_common)` (1216) — `masked = sim.copy()` (third dense
    n×n) and a pure-Python per-row `argsort` loop (slow).
  - `_fit_item_knn_cf` (1384) and `_fit_user_knn_cf` (~1240) call all three.
- `FittedRecommender.model["similarity"]` must remain a scipy **sparse** CSR (the recommend
  functions read `sim_row.indices`/`.data`), so the fix must produce a sparse top-k matrix.

### Recommended approach (block-wise / keep sparse, never materialize dense n×n)
1. **Jaccard / `_common_counts`:** avoid `.todense()`. Compute `common = (binary @ binary.T)`
   keeping it sparse (or compute only the intersection counts needed). Matrix multiply on a
   CSR stays sparse; only rows with overlap produce nonzeros.
2. **Top-k neighbors per block:** replace `_top_k_sparse`'s dense `sim.copy()` + per-row
   `argsort` with a block-wise pass over the sparse similarity matrix: for each block of rows,
   extract the block's nonzeros into a dense (block × n) array only for that block, call
   `np.argpartition` on the valid entries, keep the top-k, and write results into the output
   CSR. This bounds peak memory to one block at a time instead of the whole n×n.
3. **Consumers:** `_recommend_item_knn_cf` / `_recommend_user_knn_cf` already operate on the
   sparse `similarity` — ensure they still receive a valid sparse CSR after the refactor.
4. Keep `k`, `similarity`, and `min_common_*` semantics identical for existing tests.

### Tests
- Existing `tests/test_recommend_*.py` must stay green (algorithm equivalence, not just
  memory). Specifically the KNN fit/recommend paths.
- Add a regression test that `_fit_item_knn_cf`/`_fit_user_knn_cf` return a sparse
  `similarity` (assert `sparse`/csr not dense) and that the threshold path respects
  `min_common`.
- Memory is hard to assert in CI; at least assert no `.todense()` call path is taken and the
  fitted model's `similarity` is a `scipy.sparse` csr_matrix. Run
  `uv run pytest tests/test_recommend_*.py -q`, `uv run ruff check .`,
  `uv run mypy emergentflow`.

### Out of scope
- Do not implement a worker/subprocess executor here (documented as follow-up; see Task 11).
- Do not change the `similar_items`/`recommend` result formats.

---

## Task 10 — Issue #10: `compare` (and full-metrics `evaluate`) OOM via `diversity` O(U²) + defaults

**Status: NOT STARTED**

### Problem
`recommend.compare` (which calls `evaluate(rec, test, k=k)` with `metrics=None`, i.e. all 10
metrics) and any `evaluate` with default `metrics=None` blow up at realistic user counts.
`evaluate`'s `_auc_at_k` is already a per-user top-k metric (not a dense all-item matrix), but
**`diversity`** computes pairwise similarity over ALL users — O(U²) → ~15B pairs at 123k users,
which is the real server killer inside `compare`/full-`evaluate`.

### Implementation notes (current HEAD)
- `emergentflow/recommend/__init__.py`:
  - `evaluate(...)` (369): computes `diversity` at ~lines 495-508 as pairwise `set` comparisons
    over `user_sets` (all users with recs) — `for i,j` nested over `len(user_sets) ** 2`.
  - `compare(...)` (529): calls `evaluate(rec, test_interactions, k=k)` with no `metrics`,
    computing all 10, and re-fits an auto popularity baseline. It has NO `metrics` param.
- `metrics.py` has `_auc_at_k` (per-user). So AUC is not the dense killer here; `diversity` is.

### Recommended approach
1. **Add a `metrics` param to `compare`** (defaulting to a cheap top-k subset, matching the
   issue's "default to the cheap top-k set"). Pass it through to each `evaluate` call. Preserve
   backward compatibility for callers that pass no `metrics` by choosing a sensible default —
   the issue suggests top-k metrics: `["precision_at_k","recall_at_k","ndcg_at_k","map_at_k",
   "hit_rate"]`. Document the default change in the docstring.
2. **Make `diversity` non-quadratic.** Replace the all-pairs user-set loop with an
   approximation or a vectorized/chunked estimate that stays correct for the common case:
   - Sample a bounded number of user pairs (deterministic seed) — document that diversity is
     estimated on a sample at scale; or
   - Chunk users and compute pairwise within/across a bounded window so peak work is bounded.
   Constrain the nested loop so it cannot iterate `U²` pairs regardless (cap the number of
   pairs considered, deterministically).
3. Ensure `evaluate` with the default `metrics=None` still works but bounds `diversity` so a
   full-metrics call cannot OOM.

### Tests
- `tests/test_recommend_evaluate.py`: add a test that `compare(test_interactions, recommenders,
  k=k, metrics=[...])` honors the subset and that `compare` without `metrics` still returns all
  (or the chosen default) columns without hanging on a synthetic many-user fixture.
- Add a test that `diversity` on a fixture with many users completes quickly (bound the pair
  count) and returns a value in `[0,1]`.
- Existing `test_recommend_compare`/evaluate tests must stay green; adjust any asserting the
  exact default column set of `compare` to match the new default metrics list.
- Run `uv run pytest tests/test_recommend_*.py -q`, `uv run ruff check .`,
  `uv run mypy emergentflow`.

### Out of scope
- Do not remove `mean_auc_at_k`/`coverage`/`novelty`/`diversity` from `evaluate` — just bound
  `diversity` and add a `metrics` override to `compare`.
- Do not change `recommend()`.

---

## Task 11 — OOM sweep + remediation-strategy doc (cross-cutting)

**Status: NOT STARTED**

### Goal
Audit the whole `emergentflow` codebase (not just `recommend`) for other potential memory
blowups and write a `docs/` remediation-strategy guide. The driver behind the user's ask:
*"being able to run and have multiple models within a single canvas is important"* — i.e. the
ability to fit/score several recommenders (or several models) on one canvas via `compare`
without the server dying on a single allocation. This task should (a) enumerate the hazards
and (b) document remediation the project can adopt.

### What to write
Create `docs/memory-and-scale-remediation.md` covering:
1. **The failure mode:** in-process synchronous execution means a single node's allocation
   spike OOM-kills the whole `serve` process (and every session, since sessions are in-memory).
2. **Known hotspots (verified by reading HEAD):**
   - `recommend.catalog._fit_item_knn_cf` / `_fit_user_knn_cf` (Task 9): dense n×n
     `similarity`/`common`/top-k.
   - `recommend` `evaluate` `diversity` O(U²) pairwise (Task 10).
   - Audit other families for similar dense-array patterns: pairwise similarity code
     (`emergentflow/ml/`? `emergentflow/stats/`?), any `.todense()` calls on sparse matrices,
     `cosine_similarity` over big matrices, `pd.concat` in loops, full-matrix
     `np.linalg`/`SVD` on large inputs, embedding matrices (`emergentflow/embed/`),
     `sentence-transformers` local models, graph layouts that materialize full adjacency.
   - Grep targets: `.todense()`, `cosine_similarity`, `argsort` loops, `np.fill_diagonal`,
     `@` on big sparse products, `pd.concat`, `np.linalg.svd`/`np.linalg.eigh`,
     `np.zeros((n, n))`.
3. **Remediation strategies (document, and note which are adopted vs proposed):**
   - Block-wise / top-k-sparse similarity (Task 9) — recompute per block, keep sparse.
   - Bounded/approximate system metrics (Task 10) — cap pair counts, add `metrics` overrides.
   - **Pre-flight memory guard:** estimate `n_users x n_items` (or `n x n`) footprint before a
     node's fit/score and refuse (typed error) or warn + require an explicit opt-in/item cap,
     instead of a SIGKILL. Design the threshold + error type (e.g. a new
     `RecommendationScaleError` in `emergentflow/recommend/errors.py` or reuse
     `InvalidRecommenderParamsError`).
   - **Subprocess/worker isolation** with a memory ceiling so one node's blowup returns an
     error status rather than killing the server and other sessions (aligns with Epic 6
     sandboxing). Note this as the long-term fix; document the seam it should live behind.
   - **Session persistence / snapshots** to disk so an unexpected process death doesn't lose
     in-progress graphs (ties to #8). Document the current in-memory `SessionStore` limitation.
   - **Multi-model compare at scale:** because `compare` runs each reporter's full `evaluate`,
     document how the Task 10 `metrics` default + Task 9 sparse fit combine to allow several
     recommenders on one canvas; recommend defaulting `compare` to per-model top-k evaluate,
     then a bounded full-metric pass only when requested.
4. A triage table: hazard → affected node/family → severity → recommended fix → tracked-as.

### Deliverable
- The `docs/memory-and-scale-remediation.md` doc (primary).
- Optionally add a lightweight pre-flight guard in `recommend/__init__.py` if it's small and
  low-risk (estimate n² footprint for item/user KNN and raise a typed, actionable error with an
  item cap). This is optional to avoid scope creep; the doc is the required deliverable.

### Tests
- If a guard is added, add a test asserting the typed error is raised above the threshold.
- Otherwise, no code tests; verify the doc builds (markdown lint if the repo has one) and reads
  accurately against the code.

### Out of scope
- Do not implement the subprocess executor (document it only).
- Do not convert the in-memory session store to persistent storage (document it only).

---

## Task 12 — Docs: "agent quickstart" (final)

**Status: NOT STARTED**

### Goal
Add an **agent quickstart** guide documenting the exact happy path that prevents the friction
in #154: `serve` → register MCP → `create_session` (→ open-in-UI URL) → read `/catalog` →
build via tools → `/validate` → `execute` → read metrics.

### What to write
Create `docs/agent-quickstart.md` (or append to `docs/agent-integration.md` — check which is
more natural; there is already a `docs/agent-integration.md` and
`agents/emergent-flow-collaborator.md`). It must cover:
- Starting the server (`emergentflow serve` / `emergentflow lab`) and reading the startup
  banner (incl. the loopback vs non-loopback token guidance from Task 5).
- Registering the MCP bridge (`.mcp.json` stdio entry for `emergentflow mcp`).
- `create_session` → the `open_in_ui` URL (Task 2) and the `?session=<id>` convention (Task 1
  of the issue).
- Reading `/catalog`.
- Building via tools: `add_node` (including dict `params`/`position` now handled by Task 3),
  `connect_ports` (with the direction disambiguation of Task 1).
- `validate_graph_tool` / `/validate`, `execute_session_tool`, then
  `get_results(run_id)`/`get_metric` (which will work once Task 8 persists runs).
- A note on `await_verdict` timeout limits (Task 4) and on `compare` costing (Task 10).

### Notes
- This should reflect the actual code once Tasks 4-10 are done, so write it AFTER the code
  changes are committed, or clearly mark the parts that depend on pending tasks.
- Include a concrete example flow end to end (the issue mentions a
  teacher→article popularity-baseline recommender as a real worked example).

---

## Cross-cutting reminders
- Per `CLAUDE.md`: if IR models, node `spec`, or mutation/session-event schemas change,
  regenerate contracts via `uv run python scripts/export_ui_contracts.py` + `npm run
  gen:types`, and run `scripts/check_ui_boundary.py`.
- Gates: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy emergentflow`,
  `uv run pytest`. UI: `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.
- Never add `torch`/`implicit`/etc. to the core; keep lazy imports.