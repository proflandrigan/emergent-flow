# Bug Hunt Report: Emergent Flow canvas (`ui/src/`)

## Summary
- **Scope reviewed:** `ui/src/canvas/` (layout, toReactFlow, Canvas, overlays, minimap, context menu), `ui/src/store/` (graphStore, executionStore, validationStore, selectionStore, subgraphStore, flowStore, useLiveValidation, ir/fromIR), `ui/src/session/` (sessionStore, sessionClient SSE/poll, ChatModal, store hooks), `ui/src/execution/` (runsStore, runsClient, runCompare), `ui/src/connections/`, `ui/src/inspector/` (widgets, ConfigForm, CodePanel, CodeEditor, StepsPanel), `ui/src/exec/` (runGraph, sse), `ui/src/io/`, `ui/src/promptlab/`, `ui/src/theme/`.
- **Confirmed findings:** 1 Medium, 1 Low.
- **Overall assessment:** The canvas is unusually defensive — group/layout math (`separateOverlappingNodes`, `layeredLayout`, `computeGroupBounds`, `toAbsolutePosition`, `applyGroupNesting`), SSE parsing (`sse.ts`), debounced compile/validate effects, and single-flight session-event coalescing are all genuinely correct on inspection and under repro. The two confirmed bugs are both **async-staleness**: a store with no cancellation/ordering guard for out-of-order detail fetches, and an SSE *polling fallback* that structurally cannot surface `run_completed`.

## Findings

### [MEDIUM] — Out-of-order async resolution lets a stale run detail overwrite the user's latest selection
- **Location:** `ui/src/execution/runsStore.ts:40-51` (`selectRun`) and `:54-63` (`selectCompareRun`)
- **Class:** Race condition / stale async state
- **Confidence:** Confirmed (reproducing vitest)
- **Description:** `selectRun` awaits `getRun(runId)` and then unconditionally `set({ selectedRunId: runId, selectedRunDetail: detail })`. There is no cancellation token, no request sequence number, and no stale-frame guard. If the user clicks run **B** shortly after run **A**, and **A's** (earlier) HTTP response resolves *after* **B's**, the store is left showing **A** — the opposite of what the user last clicked. `selectCompareRun` (lines 54-63) has the identical defect and is strictly worse: it does not even set/clear the shared `loading` flag, so the compare checkbox never shows progress and the wrong row's detail is bound to the comparison.
- **Evidence / Reproduction:** Transient vitest `ui/src/__repro__/stale_race.test.ts` (created, run, deleted) driving the real store with two deferred `getRun` promises:
  - `selectRun("runA")` (deferred), then `selectRun("runB")` (deferred).
  - Resolve **B** first → store shows `runB`. ✓
  - Resolve **A** (the earlier, slower request) → `useRunsStore.getState().selectedRunId === "runA"`.
  - The assertion `expect(selectedRunId).toBe("runB")` **failed** with `expected 'runA' to be 'runB'`.
  - i.e. the user last clicked B but the Runs panel highlights and shows run A's detail (and, with a compare row selected, the comparison is computed against the wrong detail).
- **Impact:** Clerically wrong run selection under realistic timing (two quick clicks with variable latency, or an agent-triggered `fetchRuns` racing a manual selection). Wrong "Run Details" and wrong A/B comparison are shown to the user.
- **Remediation:** Guard against out-of-order completion, e.g. a monotonic request token:
  ```ts
  let detailSeq = 0;                       // module-level per store
  async selectRun(runId) {
    if (runId === null) { detailSeq++; set({ selectedRunId: null, selectedRunDetail: null }); return; }
    const seq = ++detailSeq;
    set({ loading: true, error: null });
    try {
      const detail = await getRun(runId);
      if (seq !== detailSeq) return;       // a newer request superseded this one
      set({ selectedRunId: runId, selectedRunDetail: detail, loading: false });
    } catch (err) {
      if (seq !== detailSeq) return;
      set({ error: ..., loading: false });
    }
  }
  ```
  Apply the same `seq` guard to `selectCompareRun`.

### [LOW] — SSE polling fallback never surfaces `run_completed`, so the Runs panel can go stale after an agent run
- **Location:** `ui/src/session/sessionClient.ts:409-444` (`poll`), consumed by `ui/src/session/sessionStore.ts:200-203`
- **Class:** Missing event (SSE/polling contract mismatch) / stale state
- **Confidence:** Confirmed (reproducing vitest)
- **Description:** When `EventSource` is unavailable, `subscribeToSessionEvents` falls back to polling `GET /sessions/{id}`. The fallback explicitly synthesizes only two event types — `graph_replaced` (on a `version` bump) and `chat_narration_added` (on a chat-state change). `sessionStore.handleSessionEvent` handles `run_completed` by calling `useRunsStore.fetchRuns()` to refresh an open Runs panel, but the poll loop has **no code path that ever emits `run_completed`**, so an agent-initiated run makes the server persist the run + bump the session version, the poll re-fires and synthesizes `graph_replaced`, and the Runs panel is never told a run completed.
- **Evidence / Reproduction:** Transient vitest `ui/src/session/__repro__poll.test.ts` (real timers, `delete globalThis.EventSource` to force the poll path, `pollIntervalMs: 10`, server snapshots v1 → v2):
  - `emitted` after ~90 ms and `sub.close()`: `[ 'graph_replaced' ]`.
  - So the poll path *is* functional (it detected the version bump and synthesized `graph_replaced`), yet `emitted` never contains `run_completed`.
  - Assertion `expect(emitted).toContain("run_completed")` **failed** — `expected [ 'graph_replaced' ] to include 'run_completed'`.
- **Impact:** Environment-dependent (browsers ship `EventSource`, so the primary path is used there; the fallback applies in SSR/test environments or non-EventSource clients). In those environments an agent-completed run leaves the Runs panel stale until some other event triggers a refetch.
- **Remediation:** Have the poll loop synthesize `run_completed` when it detects a bump that the server attributes to a completed run, or have the poll refetch runs on every version bump:
  ```ts
  if (lastVersion !== null && session.version !== lastVersion) {
    onEvent({ type: "graph_replaced", session_id: sessionId, version: session.version });
    onEvent({ type: "run_completed", session_id: sessionId, version: session.version });
  }
  ```
  (the `run_completed` consumer only calls `fetchRuns()`, so it is idempotent and safe to emit on any bump).

## Notes & unverified leads
These looked suspicious but could **not** be corroborated as bugs; all are labelled unconfirmed:
- **`graphStore.groupNodes` NaN coords** (`graphStore.ts:739-741`): `positions.map(p => p.x)` has no empty-guard, so `nodeIds` all resolving to missing nodes yields `Math.min(...[]) === Infinity`. **Refuted as reachable** — `groupNodes` has no UI caller (the canvas uses `groupSelection`, which filters to real nodes), so it cannot be triggered; `ir.ts`'s `fromIR` equivalent (lines 191-192) is guarded.
- **`useLiveValidation` / `CodePanel` / `StepsPanel` out-of-order compile-validate race**: all use a `cancelled` flag that correctly drops stale responses.
- **`handleSessionEvent` single-flight coalescing**: correct on trace; `queuedEvent` only ever keeps the latest, and each refresh re-fetches full state.
- **`splitHighlightedByLine`** (CodePanel): traced a multi-line span through open/close tag stack — output is correct.
- **Group drag / `toAbsolutePosition` / `applyGroupNesting` math**: `computeGroupBounds` has an explicit empty-array guard; relative↔absolute conversion is internally consistent.
- **`separateOverlappingNodes` / `layeredLayout`**: cascade/taken-set logic correctly avoids collisions and terminates (bounded by `ids.length`).
- **`useRunsStore.fetchRuns` loading flag churning against `selectRun`**: real but cosmetic (brief list flicker), not a correctness defect.

## Coverage & limitations
- Static analysis + `tsc --noEmit` (clean) + eslint (not re-run exhaustively) + targeted `vitest` repros against the real store/client modules; the full dev server was not launched.
- `.bug-hunt/` not previously present; report saved as `.bug-hunt/2026-08-14-bug-hunt-report.md`.
- Areas inspected but not deep-dive-probed at runtime: catalog `useCatalog`, `IRToolbar` import/save flows, `QueryBuilderPreview`, `CompareGrid`, `PromptLabPanel` dataset wiring, and `ui/src/ui/*` primitives — none of these surfaced a reproducible defect in review.