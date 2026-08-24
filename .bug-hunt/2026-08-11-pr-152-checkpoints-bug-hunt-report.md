# Bug Hunt Report: PR #152 — agent-driven graph editing via MCP with checkpoints and revert

## Summary
- Scope reviewed: the PR's backend changes — `emergentflow/collab/checkpoints.py`
  (new), `session.py` (`apply_direct_mutation` / `revert_checkpoint`),
  `mcp.py` (editing/introspection MCP tools), `mcp_bridge.py` (new stdio HTTP
  bridge), `cli.py` (`mcp` subcommand), `server/app.py` (`/apply` `/revert`
  `/checkpoints` `/mcp/*` routes) — plus the UI session store, `CheckpointPanel`,
  `sessionClient`, and `ChatModal`. The equivalent `ui/src/generated/*` contract
  artifacts were assumed correctly regenerated (covered by UI tests).
- Confirmed findings: 1 High (manifesting as 2 related defects sharing one root cause).
- Overall assessment: The checkpoint/revert machinery is well-structured, but
  `revert_checkpoint` derived the inverse mutation against the *current* (post-edit)
  graph instead of the checkpoint's pre-edit snapshot, which (a) recorded a
  semantically wrong inverse for param edits and (b) could raise `MutationError`
  *after* the session's graph/version had already been mutated for node-removal
  edits, leaving the session reverted-but-unrecorded with no event emitted. Both are
  fixed by deriving the inverse against `checkpoint.previous_graph` before any state
  mutation.

## Findings

### [HIGH] — Revert checkpoint records a wrong inverse and can corrupt session state for node-removal edits
- **Location:** `emergentflow/collab/session.py:492` (now `:495`)
- **Class:** State/consistency + logic error (wrong base graph for inversion; partial update on error path)
- **Confidence:** Confirmed
- **Description:** `revert_checkpoint` computed `inverse_mutation = invert_mutation(previous_graph, checkpoint.mutation)`, where `previous_graph` is the *current* session graph (the state *after* the forward edit was applied), and it did so *after* already setting `session.graph = checkpoint.previous_graph` and bumping `session.version`. Two consequences:
  1. **Wrong inverse recorded.** For a `set_params` edit, `invert_mutation` reads the original param value from the graph it is given. Given the post-edit graph, it found the *forward* value and stored it as the "inverse," so the REVERT checkpoint's `mutation` would re-apply the edit instead of undoing it.
  2. **Partial mutation on the error path.** For an edit that removed a node, `invert_mutation` raises `MutationError` (`cannot invert remove_nodes: node ... does not exist in the graph`) because the removed node is gone from the current graph. That raise came *after* the graph was already restored and the version bumped, but *before* the revert checkpoint was stored or the `graph_reverted` event published — leaving the session's graph reverted, its version incremented, yet with no checkpoint record and no SSE event, so the canvas never learns the graph changed.
- **Evidence / Reproduction:** A local script drove `SessionStore` directly:
  - set_param case: forward `set_params={node:{path:"a.csv"}}` (read back as `changed.csv`), then `revert_checkpoint`. The stored REVERT checkpoint's `mutation.set_params` was `{path:"changed.csv"}` (the forward value) instead of the correct inverse `{path:"a.csv"}`.
  - remove_nodes case: `add_nodes` two nodes, then `remove_nodes=[n1]`, then `revert_checkpoint` that edit → raised `MutationError: Cannot invert remove_nodes: node '...' does not exist in the graph.` After the failed revert, the session had `version` bumped to 4, the node restored in the graph, and only three checkpoints recorded (the REVERT checkpoint missing, no event published) — the exactly-broken half-applied state.
  - Both behaviors also demonstrate the correct behavior: `invert_mutation(checkpoint.previous_graph, checkpoint.mutation)` yields `{path:"a.csv"}` and completes without error.
- **Impact:** Every reverted agent param edit is recorded with a factually wrong inverse (breaks any later introspection/re-ingestion of the history), and any revert of a node-removal edit (e.g. `delete_node`/`delete_note` MCP tools) corrupts session consistency — graph rebuilt but unrecorded, no SSE `graph_reverted` event, so the UI is out of sync until a manual refresh.
- **Remediation:** Derive the inverse against the checkpoint's pre-edit snapshot, and do it **before** touching `session.graph`/`version`, so a genuinely non-invertible forward mutation raises with the session untouched:
  ```python
  inverse_mutation = invert_mutation(checkpoint.previous_graph, checkpoint.mutation)
  previous_graph = session.graph
  previous_version = session.version
  session.graph = checkpoint.previous_graph.model_copy(deep=True)
  session.version += 1
  revert_checkpoint = Checkpoint(
      kind=CheckpointKind.REVERT,
      author=checkpoint.author,
      description=f"Revert: {checkpoint.description}",
      base_version=previous_version,
      mutation=inverse_mutation,
      previous_graph=previous_graph,
      resulting_version=session.version,
  )
  ```
  Regression tests added in `tests/test_collab_checkpoints.py` (`test_revert_checkpoint_mutation_is_the_faithful_inverse` and `test_revert_remove_nodes_edit_succeeds_and_leaves_session_consistent`). The original reproduction script re-run against the fixed code now reports the correct inverse and a successful revert.

## Notes & unverified leads
- **MCP bridge stdio event-loop reuse (unverified/refuted).** `cli.py` builds the bridge server via `asyncio.run(create_bridge_mcp_server(...))` (creating its internal `httpx.AsyncClient` and doing the catalog `GET` in that loop) and then calls `mcp.run(transport="stdio")` (a second event loop). Empirically tested an `httpx.AsyncClient` doing a `GET` in one `asyncio.run` loop followed by a `POST` in a second loop — it succeeded in this environment (httpx/anyio backend), so this did not reproduce. Left as a low-confidence observation; noted in case it manifests under a different httpx/httpcore version.
- **`emergentflow mcp` with no `EMERGENTFLOW_SESSION_TOKEN`**: the bridge sends no `Authorization` header and the server routes require a configured session token only when one is set server-side; a tokenless local dev flow works. Not a defect.

## Coverage & limitations
- Review focused on the PR's new backend primitives and their HTTP/MCP/UI wiring; the full `ui/src/generated/*` schema artifacts and `mcp` route `structured_content` handling were validated via their existing passing test suites rather than re-derivation.
- The broader repo test suite beyond the collab/server-session/mutation modules was not run end-to-end (the change is isolated to `emergentflow/collab/session.py`); affected suites (321 collab+server tests, mutation tests, and 897 UI tests) all pass, as do `ruff`, `ruff format`, `mypy emergentflow/collab`, and `tsc --noEmit`.
