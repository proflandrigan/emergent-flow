# Bug Hunt Report: emergent-flow (full codebase)

## Summary
- Scope reviewed: entire repository at commit `5781588` (branch `time-series-modelling`) — the Python SDK
  (`emergentflow/ir`, `codegen`, `nodes/examples` in full, `ml`, `stats`, `timeseries`, `explain`, `data`
  incl. `warehouse/`, `clean`, `server`, `collab`, `connections`, `llm`, `script`, `api.py`, `types/catalog.py`)
  and the React/TypeScript canvas (`ui/src/`, focused on session/chat/SSE plumbing plus a sampling pass over
  the rest). Six parallel reviewers each ran the full Discovery → Verify loop over a disjoint slice and
  reported back only reproduced findings.
- Tooling baseline: `ruff check .` — clean. `mypy emergentflow` — clean. Full `uv run pytest -q` — all passing
  (0 failures). `npm run typecheck` / `eslint .` / `npm test` (544 tests) on `ui/` — all clean/passing.
- Confirmed findings: **0 Critical, 0 High, 4 Medium, 0 Low**.
- Overall assessment: this is an unusually well-defended codebase for its size — the ADR-0002
  compile/execute-equivalence invariant is enforced by shared helper functions rather than duplicated logic,
  so the reviewers could not find a single case where `compile_to_code` and `execute` actually diverge in
  behavior. The freshest code (the `timeseries` family added in the last three commits) held up completely;
  its own review pass already caught the bugs a fresh look would otherwise have found. All four confirmed
  bugs are one layer down from the node/codegen contract, in shared library adapters (`ml.fit_transform`,
  the four warehouse query adapters, an MCP collaboration tool, and a client-side SSE fallback) — each is a
  real, reproducible defect, but none is destructive or high-likelihood in default configurations.

## Findings

### Medium — Warehouse `truncated` flag is a false positive whenever the true result size exactly equals `max_rows`
- **Location:** `emergentflow/data/warehouse/adapters/duckdb_adapter.py:69` and identically in
  `postgres_adapter.py:98`, `bigquery_adapter.py:73`, `redshift_adapter.py:85` (root cause shared via
  `emergentflow/data/warehouse/query.py`'s `_inject_limit`)
- **Class:** Off-by-one / boundary logic error
- **Confidence:** Confirmed
- **Description:** `_inject_limit` appends `LIMIT max_rows` to the query before it reaches the adapter. Each
  adapter then sets `truncated = True` whenever `len(df) >= max_rows`. Since the database already capped the
  result at exactly `max_rows` via the injected `LIMIT`, this check can never tell "there were exactly
  `max_rows` matching rows" apart from "there were more, and we got cut off" — it fires on the boundary in
  both cases.
- **Evidence / Reproduction:** Ran `ef.data.query()` (the real caller path) against a 5-row table with
  `max_rows=5`:
  ```python
  sql = "SELECT * FROM (VALUES (1),(2),(3),(4),(5)) AS t(x)"  # exactly 5 rows total, no more
  result = ef_query(connection="x", client=FakeClient(), dialect="duckdb", sql=sql, max_rows=5)
  # rows returned: 5
  # result.truncated: True   <- wrong; the table has no more than 5 rows
  ```
  The existing test `tests/test_warehouse_adapters.py::test_execute_with_max_rows` doesn't catch this because
  it calls `adapter.execute()` directly against unlimited raw SQL over a 100-row table, so the exact-boundary
  case is never exercised. Confirmed the same off-by-one exists identically in all four adapter files.
- **Impact:** `QueryResult.truncated` is inspectable/user-facing — per its own docstring, it exists "so the
  canvas can warn... before the analyst commits" to a truncated result. Any query whose true row count happens
  to equal the configured `max_rows` produces a spurious "results were truncated" warning, misleading users
  into thinking they need pagination or a higher cap when they already have the complete result set. Affects
  all four supported dialects identically.
- **Remediation:** Request one extra row beyond the cap internally and use its presence to decide truncation.
  In `_inject_limit`, inject `max_rows + 1` rather than `max_rows`; in each adapter:
  ```python
  truncated = False
  if request.max_rows is not None and len(df) > request.max_rows:
      df = df.head(request.max_rows)
      truncated = True
  ```
  Re-run the repro above after the fix: the 5-row/`max_rows=5` case should report `truncated=False`, and a
  6-true-row/`max_rows=5` case should still report `truncated=True`.

### Medium — `ml.fit_transform` crashes with a confusing error when a `fit_transform`-archetype estimator returns a sparse matrix
- **Location:** `emergentflow/ml/__init__.py:550-556` (`fit_transform`), reachable via the
  `transform.encode_categorical` node (`emergentflow/nodes/examples/encode_categorical.py`) with
  `estimator="OneHotEncoder"`
- **Class:** API/contract misuse — untyped assumption about `.fit_transform()`'s return shape
- **Confidence:** Confirmed
- **Description:** `fit_transform()` computes `component_cols` from `transformed.shape[1]` and assigns
  `result[component_cols] = transformed`, assuming `transformed` is a dense array. `OneHotEncoder`'s
  `sparse_output` kwarg is user-overridable through the `encode_categorical` node's free-form `params` dict
  (the curated default in `emergentflow/ml/catalog.py:191-193` is `False`, but nothing in
  `_resolve_estimator_and_kwargs`'s allow-list blocks a caller from setting it to `True`). When
  `sparse_output=True`, `.fit_transform()` returns a `scipy.sparse` matrix and the multi-column assignment
  raises.
- **Evidence / Reproduction:**
  ```python
  import pandas as pd, emergentflow as ef
  df = pd.DataFrame({'cat': ['a', 'b', 'a', 'c'] * 5, 'num': range(20)})
  ef.ml.fit_transform(df, estimator='OneHotEncoder', target=None, features=['cat'],
                       params={'sparse_output': True})
  # ValueError: Columns must be same length as key
  ```
  Verified the identical crash occurs through both the `execute` path and the codegen-emitted code for an
  `EncodeCategorical` node instantiated with the same params — ADR-0002 equivalence holds (both paths fail
  the same way), but the underlying operation itself is broken for this legal, allow-listed configuration.
- **Impact:** Any user who sets `sparse_output: true` on the `encode_categorical` node — a legal, documented
  override with no restriction against it — gets an opaque `ValueError: Columns must be same length as key`
  instead of working output or a clear, typed error.
- **Remediation:** Densify the transformer output before building component columns:
  ```python
  import scipy.sparse as sp
  ...
  if sp.issparse(transformed):
      transformed = transformed.toarray()
  component_cols = [f"component_{i}" for i in range(transformed.shape[1])]
  ```
  This keeps the existing dense-array contract intact regardless of what the caller passes for
  `sparse_output`.

### Medium — `mcp.py`'s `await_verdict` blocks for the full timeout on an invalid `proposal_id` instead of failing fast
- **Location:** `emergentflow/collab/mcp.py:125-165`
- **Class:** Logic error / missing validation
- **Confidence:** Confirmed
- **Description:** `await_verdict` looks up `store.get(session_id).proposals.get(proposal_id)`, which returns
  `None` for an unknown id. The existing `proposal is not None and ...` short-circuit never fires an early
  return for this case, so execution falls into the polling loop, which can never observe a matching event
  (no such proposal exists) and blocks for the entire `timeout_seconds` window before returning
  `{"status": "timeout", ...}`.
- **Evidence / Reproduction:** Reproduced the function's exact logic in isolation against a real session:
  called it with a nonexistent `proposal_id` and `timeout_seconds=3.0`. Measured elapsed time: 3.0005s
  (matches the timeout exactly), returning a `"timeout"` status indistinguishable from a genuinely pending
  proposal.
- **Impact:** Every other lookup in this module (`get_graph`, `SessionStore.accept_proposal`, etc.) raises a
  typed error immediately for an unknown id — this is the one path that silently blocks instead. An agent
  that mistypes or races a `proposal_id` (plausible, since IDs are freshly generated strings passed across a
  tool-call boundary) stalls for up to the full default 30s timeout with a misleading "timeout" result rather
  than a fast, actionable error.
- **Remediation:** Check existence before entering the wait loop:
  ```python
  session = store.get(session_id)
  if proposal_id not in session.proposals:
      raise UnknownProposalError(f"no proposal with id {proposal_id!r} on session {session_id!r}.")
  proposal = session.proposals[proposal_id]
  if proposal.status.value != "pending":
      return {"status": proposal.status.value, "session_id": session_id, "proposal_id": proposal_id}
  ```
  (`UnknownProposalError` from `emergentflow.collab.session`, matching the exception type the rest of the
  module already lets propagate.)

### Medium — SSE polling fallback silently drops all chat updates when session `version` doesn't change
- **Location:** `ui/src/session/sessionClient.ts:311-330` (`subscribeToSessionEvents` poll fallback),
  interacting with `emergentflow/collab/chat_runner.py` (never bumps `session.version`) and
  `emergentflow/collab/session.py:276,356` (the only two places `version` is incremented — both
  graph-mutation paths, not chat)
- **Class:** Logic error / missed event class
- **Confidence:** Confirmed
- **Description:** When the browser lacks `EventSource` support, the client falls back to polling and
  synthesizes a UI event only when `session.version` changes since the last poll. Chat turns (start →
  streaming narration → completed/failed) never touch `version`, so a chat interaction produces no synthetic
  event under this fallback.
- **Evidence / Reproduction:** Vitest reproduction mocking `fetch` to return a session whose
  `chat.turns[0].status` transitions `running` → `completed` across two polls while `version` stays `0`.
  Result: the fetch mock was called 2+ times but zero events reached the subscriber
  (`received.length === 0`), confirming `handleSessionEvent` in `sessionStore.ts` is never invoked.
- **Impact:** In any environment without `EventSource` (the fallback's stated target — restrictive
  browsers/extensions/proxies, some test/SSR environments), a chat turn that starts and completes never
  updates the UI. The chat panel is stuck showing "working…" indefinitely until an unrelated action (e.g. a
  graph edit, which does bump `version`) happens to trigger a refetch.
- **Remediation:** Track a second cursor alongside `lastVersion` and synthesize an event when it changes too
  — e.g. compare a snapshot of `session.collab?.chat` (turn count + each turn's `status`) each poll:
  ```ts
  const chatSnapshot = JSON.stringify(session.collab?.chat);
  if (session.version !== lastVersion || chatSnapshot !== lastChatSnapshot) {
    onEvent(/* ... */);
  }
  lastChatSnapshot = chatSnapshot;
  ```

## Notes & unverified leads (optional)

These looked suspicious but could not be verified as reproducible bugs, or were traced and refuted. Listed so
they aren't silently lost, not because they should be treated as findings:

- **`emergentflow/codegen/declarative.py:176-187` (`_require_linear_chain`)** sums `in_count`/`out_count`
  across *all* IN/OUT ports of a node rather than per-port. A hypothetical future declarative layer with two
  independent single-source IN ports (e.g. a residual/`nn.add` merge) would be misclassified as fan-in and
  rejected even though each port is individually singly-wired. Currently unreachable — both registered
  declarative layers (`nn.linear`, `nn.relu`) have exactly one IN port. Worth a look whenever Epic 10's fuller
  layer catalog lands.
- **`emergentflow/ir/migrate.py`**: `INITIAL_SCHEMA_VERSION == CURRENT_SCHEMA_VERSION == 1`, so the one
  registered example migration (`_migrate_v0_to_v1`) is permanently dead on the real load path. Explicitly
  documented as "SYNTHETIC/ILLUSTRATIVE," so intentional — but it means the migration-chaining mechanism
  itself has never been exercised against a real multi-version graph.
- **`emergentflow/data/warehouse/adapter_client.py:65`** (`_execute_with_timeout`) uses a
  `ThreadPoolExecutor` with `cancel_futures=True`, but Python can't forcibly kill a running thread, so the
  underlying DB call keeps running in the background after `QueryTimeoutError` is raised. This is explicitly
  documented as a known limitation in `protocol.py`'s `QueryTimeoutError` docstring — not a new bug, but a
  real, acknowledged lingering-connection leak on timeout.
- **`dry_run` estimated_rows`** on the postgres/duckdb/redshift adapters returns the number of `EXPLAIN`
  *plan lines*, not an actual estimated row count. Not verified whether any downstream consumer (UI cost
  estimate display) treats this as a meaningful number versus best-effort — would need to check
  `CostEstimate.estimated_rows` usage in `ui/` to confirm impact.
- **`emergentflow/server/app.py:317`** (`_require_session_auth`) compares the bearer token with plain `!=`
  rather than `secrets.compare_digest`, a theoretical timing side-channel. Not demonstrated as exploitable
  given the server is localhost-only by default; flagging only in case session auth is ever relied on across
  an untrusted network.
- **`ParamSpec` mutable defaults** (e.g. `default=[]` on `llm_call.py`'s `messages` param,
  `eval_run.py`'s `variants` param) are a classic Python footgun, but no code path was found that mutates a
  `ParamSpec.default` in place — only ever read via `.get()`. Not pursued further without evidence of
  in-place mutation.
- **`time_weighted_aggregate`**'s `date_col` param is validated for existence but its *values* are never used
  for actual time-delta weighting — weighting is by row position only. This exactly matches its own
  docstring ("row order is assumed to already be chronological"), so it's a documented design choice, not a
  discrepancy.
- Refuted during UI review: a `QueryBuilderPreview.tsx:99` eslint `exhaustive-deps` warning (traced — false
  positive, the dependency recomputes from the same source every render); a potential XSS via
  `ReactMarkdown` rendering chat messages (refuted — no `rehype-raw`, so raw HTML isn't rendered; user
  messages are auto-escaped plain JSX text); a suspected race in `sessionStore.ts`'s SSE dedup/coalescing
  logic (traced by hand through concurrent-event orderings — sound, no bug).

## Coverage & limitations

- **Fully reviewed** (read in depth, with targeted reproductions): `emergentflow/ir/`, `emergentflow/codegen/`
  (compiler, executor, traversal, wiring, naming, context, declarative, formatting), `emergentflow/nodes/
  contract.py`, `emergentflow/clients.py`, `emergentflow/timeseries/` (all 8 ops + reference nodes),
  `emergentflow/nodes/examples/` (data/clean/transform/ml/eval/explain/llm/viz/reports/notes/script/nn
  families — ~30 of ~65 files read in full, remainder sampled by pattern given their mechanical uniformity),
  `emergentflow/data/warehouse/` (all four adapters, query.py, spec_compiler.py, credentials.py, profiles.py,
  preflight.py, adapter_client.py, protocol.py), `emergentflow/ml/__init__.py` (evaluate/train_*/predict/
  fit_transform/fit_pipeline/grid_search/cross_validate/apply_estimator/fit_and_label), `emergentflow/
  explain/`, `emergentflow/clean/`, `emergentflow/api.py`, `emergentflow/types/catalog.py`,
  `emergentflow/server/cache.py`, `emergentflow/collab/session.py`, `emergentflow/collab/mcp.py`,
  `emergentflow/collab/chat_runner.py`, `emergentflow/ir/mutation.py`, `emergentflow/collab/gates.py`,
  `emergentflow/collab/review.py`, `emergentflow/connections/profiles.py`, `emergentflow/llm/` (protocol,
  gateway, secrets, pricing, budget), `emergentflow/script/custom_code.py`, and on the UI side
  `ChatModal.tsx`, `sessionStore.ts`, `sessionClient.ts`, `OverlayModal.tsx`, `QueryBuilderPreview.tsx`.
- **Not reviewed / spot-checked only:** `emergentflow/codegen/inference.py`, `diagnostics_schema.py`,
  `export.py`; `emergentflow/ml/catalog.py` (1219 lines, spot-checked only), `ml/generator.py`,
  `data/warehouse/generator.py`/`introspect.py`/`params.py`/`replay.py`; `emergentflow/collab/knowledge.py`,
  `consult.py`, `personas.py`/`persona_defs.py`, and the individual CLI adapters (`claude_adapter.py`,
  `codex_adapter.py`, `gemini_adapter.py`, `opencode_adapter.py`) beyond their shared `base.py` contract;
  `ui/src/canvas/*` (graph rendering/drag-and-drop), most of `ui/src/store/graphStore.ts`, `ui/src/
  promptlab/*`, `ui/src/connections/*`, and `ui/src/generated/*` diffed against the live JSON Schema.
- **Stats family** (`emergentflow/stats/`) received only a light pass since it had no recent commits and
  ruff/mypy were clean on it — a deeper dedicated pass wasn't run.
- All four confirmed findings are Medium severity: none is destructive, none corrupts data, and each requires
  either a non-default configuration (`sparse_output=True`), a boundary coincidence (result count == cap), an
  invalid id from a caller, or a non-`EventSource` browser environment to trigger. None was elevated to High
  because none is reachable via default settings on the common/happy path.
