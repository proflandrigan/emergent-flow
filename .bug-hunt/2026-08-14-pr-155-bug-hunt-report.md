# Bug Hunt Report: PR #155 — Reduce agent-onboarding friction and fix OOM at scale

- **Target:** `proflandrigan/emergent-flow` PR #155 (branch `feat/agent-onboarding-and-oom`)
- **Date:** 2026-08-14

## Summary

- Scope reviewed: the full PR #155 diff — `emergentflow/recommend/` (block-wise top-K KNN
  fitters, footprint pre-flight guard, bounded `diversity`, `compare` metrics param),
  `emergentflow/collab/` (new `create_session` MCP tool, direction-aware `connect_ports`,
  `await_verdict` timeout handling, stdio-bridge JSON-string reparse, `record_run` /
  `run_completed` event), `emergentflow/server/` (`open_in_ui` links, `run_id` plumbing,
  session-run publish), and the `ui/` changes (`run_completed` consumption, Join button,
  Review proposals panel, event-schema/TS artifacts).
- Confirmed findings: none (0 Critical, 0 High, 0 Medium, 0 Low).
- Overall assessment: This is a well-tested PR whose highest-risk change — replacing a dense
  n×n similarity matrix with a block-wise top-K implementation — is provably numerically
  identical to the previous dense version across every similarity metric and shape I could
  exercise. The three defects surfaced during the PR's own review were already fixed and
  committed on this branch HEAD (`83627d5`). My hunt ran the differential/probing checks and
  the focused test suites; I found no additional reproducible defect worth a finding.

The PR already carries a follow-up commit (`83627d5 "fix PR #155 follow-up bugs"`) fixing
three verified defects: a raw `TypeError` from `int(None)` when `max_footprint_bytes=None`,
a hardcoded `127.0.0.1:8765` in session `open_in_ui` links, and the UI not consuming the
`run_completed` event. Those are documented here for traceability even though they are no
longer actionable (already fixed).

## Findings

### [Info — already fixed in HEAD] — `max_footprint_bytes=None` crashed KNN fits (TypeError)
- **Location:** `emergentflow/recommend/catalog.py:1198` (`_enforce_knn_footprint`)
- **Class:** Null dereference / wrong-default
- **Confidence:** Confirmed (fixed in `83627d5`)
- **Description:** The param's documented contract default is `None`, but the first draft used
  `params.get("max_footprint_bytes", _DEFAULT_MAX_KNN_FOOTPRINT_BYTES)`, which still returns
  `None` when the caller *explicitly* passes `{"max_footprint_bytes": None}`, then evaluated
  `int(None)` → `TypeError`, surfacing as a server 500 for a legitimate call.
- **Evidence / Reproduction:** Reproduced by fitting `user_knn_cf`/`item_knn_cf` with
  `params={"k": 2, "max_footprint_bytes": None}` → `TypeError: int() argument must be ...`.
  Now covered by `tests/test_recommend_collaborative_catalog.py::test_knn_cf_max_footprint_bytes_none_uses_default`.
- **Impact:** A documented, valid param combination crashed both KNN fits.
- **Remediation (applied):** Guard the lookup before coercing:
  `cap = params.get("max_footprint_bytes"); if cap is None: cap = _DEFAULT_MAX_KNN_FOOTPRINT_BYTES`.

### [Info — already fixed in HEAD] — Hardcoded `:8765` in session `open_in_ui` link
- **Location:** `emergentflow/server/app.py:652` and `emergentflow/collab/mcp.py:104`
- **Class:** Hardcoded configuration
- **Confidence:** Confirmed (fixed in `83627d5`)
- **Description:** `POST /sessions` and the MCP `create_session` tool built
  `open_in_ui` from a literal `http://127.0.0.1:8765`, so a server bound to any other
  port produced a dead browser link.
- **Evidence / Reproduction:** Tests in `83627d5` set `OPEN_IN_UI_BASE` to a different port and
  assert the link follows it; `serve()` now overwrites the shared base with the real bind.
- **Remediation (applied):** Shared, module-level `emergentflow.collab.mcp.OPEN_IN_UI_BASE`
  that `serve()` sets to the actual bind host/port before any session is created.

### [Info — already fixed in HEAD] — UI ignored `run_completed` SSE event
- **Location:** `ui/src/session/sessionStore.ts`
- **Class:** Missing event handling / stale UI
- **Confidence:** Confirmed (fixed in `83627d5`)
- **Description:** Agent-initiated session runs persisted a real run and published
  `run_completed` with a `run_id`, but the canvas's event handler ignored it, so an open
  Runs panel never surfaced the new run without a manual refresh.
- **Evidence / Reproduction:** `ui/src/session/sessionStore.test.ts` added in `83627d5` asserts
  `fetchRuns` fires on a `run_completed` event.
- **Remediation (applied):** Handle `event.type === "run_completed"` in `handleSessionEvent`
  by refreshing `useRunsStore`.

## Notes & unverified leads (none reported; leads checked and refuted)

These are the suspicious spots I chased and REFUTED with evidence — recorded so no one re-reports
them as bugs:

- **Block-wise KNN (`_build_knn_similarity`) vs old dense `_similarity_matrix`/`_top_k_sparse`:**
  Ran a differential script comparing old vs new CSR outputs across cosine/pearson/jaccard, all
  `k` in {1,2,5}, `min_common` in {1,2}, shapes `(7,5),(10,8),(1,3),(3,3),(300,20)` with
  `block_rows=3` (forcing real blocking). **All equal** — bit-exact top-k sets and values.
  Additionally exercised degenerate shapes (`(0,5)` and `(1,5)`): shape `(0,0)` and `(1,1)`
  nnz=0, no crash.
- **Pearson centering in blocks:** the full matrix is centered once (`centered_full`) and each
  block computes `cosine_similarity(centered_full[start:end], centered_full)` — identical rows
  to the dense version. Refuted.
- **`_bounded_diversity` divide-by-zero:** for `n<2` returns `0.0`; for `n > 200` the sample is
  size 200 so the pairwise loop always has ≥1 pair. No `len(similarities)==0` path. Refuted.
- **`compare` default metrics:** default excludes `diversity` (intentional, documented); columns
  are guarded (`if "mean_ndcg_at_k" in comparison.columns`). `_DEFAULT_COMPARE_METRICS` is a
  module list passed to `evaluate`, which only does `set(metrics)` — never mutated. Refuted.
- **Footprint guard:** `None → 2 GiB default`; a `300×300` matrix doesn't raise;
  a tiny `max_footprint_bytes=100` does raise `RecommendationScaleError`. Edge arithmetic in the
  error message (`cap / 1024**3`) is fine for small ints. Refuted.
- **MCP bridge JSON-string reparse:** introspected the server's real FastMCP schemas — `params`,
  `position`, `graph` render as `anyOf:[{type:"object"},{type:"null"}]`, which
  `_complex_schema_names` correctly flags via `anyOf` descent. `set_param`/`value` renders as
  `{}` (no type) so it is not reparsed — but this predates the PR and is not a regression.
- **`await_verdict`:** negative `timeout_seconds` raises `ValueError`; capped at 600; loop
  re-checks deadline with `q.get(timeout=min(1.0, remaining))`. Refuted.
- **Direction-aware `connect_ports` / `_find_port`:** prefers exact name+direction, falls back to
  same-name; FixMe for `clean.explode_lists`'s in/out `frame` ports. Refuted.
- **`run_completed` schema/TS:** schema `type` enum and TS `Type` union both add
  `run_completed`; `run_id?: string|null` present on both. Consistent. Refuted.
- **Server `_save_run_record`/`execute_graph`/`execute_session`:** `save()` returns the
  generated `run_id`; partial scopes/save-failure return `None`; the session-execute path
  publishes `run_completed` only when a real `run_id` exists, wrapped in
  `contextlib.suppress`. Refuted.

## Coverage & limitations

- Reviewed every source file in the PR diff and ran the focused suites:
  `test_recommend_collaborative_catalog.py`, `test_recommend_evaluate.py`,
  `test_collab_mcp.py`, `test_mcp_bridge.py`, `test_collab_contracts.py`,
  `test_server_execute_session_run.py`, `test_server_serve_banner.py`,
  `test_server_sessions.py` — all green (215 tests), plus `ruff check` and `mypy` clean on all
  changed modules.
- Not exhaustively exercised: live end-to-end agent chat through a real FastMCP client over TCP
  (tests use the ASGI transport); the 600 s `await_verdict` timeout was verified only by
  inspection, not by waiting it out; the `proxy_forwarded`/auth paths and the UI build
  (`npm run build`) were not run.
- The two untracked files `docs/issue-154-remaining-tasks.md` and `docs/ml_feature_addons_1.md`
  in the working tree are unrelated to this PR and were excluded from review.