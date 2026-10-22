# Bug Hunt Report: PR #176 (iteration 8)

## Summary

**Scope:**
- `git diff main...HEAD` at 0d2a845, focusing on that commit's deferral of click-path `request(view)` calls to a `setTimeout(0)` macrotask (`requestAfterClick` in `ui/src/App.tsx`).
- Questions examined:
  - Can a deferred request race a `hashchange`-driven request or a session join/switch?
  - Do rapid double-clicks misbehave?
  - Can the pushState branch double-apply alongside `hashchange` or `popstate`?
- Then a final whole-PR sweep.

Findings from iterations 1 to 7 were not re-reported.

**Confirmed findings:** none.

**Assessment:** in a real Chromium, 0d2a845 fixes the iteration 7 LOW, including the two variants iteration 7 did not run: result-card links and the `differsOnlyByActiveSession` pushState branch inside a card. No ordering, double-apply or stale-view problem could be produced.

## Findings

No confirmed findings.

## Notes & unverified leads

### Real-browser check of 0d2a845

- **Setup:**
  - Ran `uv run emergentflow serve --no-browser`, plus a Vite dev server on port 5199 at HEAD.
  - Created a session with `examples/functional_pipeline.json` plus two extra nodes:
    - a `notes.markdown` node with `[reach anova](#focus=n-anova&reach=up)` and `[impute](#focus=n-impute)`;
    - a `reports.result_card` node with `[sess anova](/?session=<sid>#focus=n-anova&reach=up)` and `[card load](#focus=n-load)`.
  - Drove the page with Playwright's `locator.click`.
- **Scripts:** `/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/iter8/mkgraph.py` and `/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/iter8/scen.cjs`.
- **Results:**
  - **A. Note reach link, clicked 3 times:** `n-anova` was selected after every click, and the note and card stayed `ef-trace-dimmed`. The iteration 7 regression is gone.
  - **B. Result-card plain link, clicked twice:** `n-load` was selected both times.
  - **C. Active-session link inside the card with the address bar at bare `/`:**
    - Click 1 pushed `/?session=…#focus=n-anova&reach=up`, selected `n-anova`, and did not reload (`window.__marker` survived, no `beforeunload`).
    - Click 2 hit the same-hash branch and `n-anova` stayed selected.
  - **D. Double-click on a note link:** the first click navigates (`hashchange`) and the second hits the same-hash deferred branch. Both apply the same view, so the result is idempotent and `n-impute` was selected. The double-click then puts the note into edit mode, which is NoteNode's normal double-click behaviour and the same on main.
  - **E. Two different links clicked back to back with no wait** (same-hash then new-hash, and the reverse): the final selection was always the last link clicked. With the hash link first, the deferred timer queued by click 1 has fired long before click 2's `hashchange` task. Getting a stale apply would need two clicks inside the same ~0-4 ms timer window, which no human click can do.
  - **F. Back/Forward after the C pushState:** each step re-applied its entry's view through `hashchange`. There was no double apply.

### Double-apply analysis

The same-hash branch is the only one that does not `preventDefault`. A fragment navigation to the identical URL fires no `hashchange`, so only the deferred request applies.

The pushState branch calls `preventDefault`, and `pushState` fires neither `hashchange` nor `popstate`. Nothing in `ui/src` listens for `popstate` (checked with grep), so a `popstate` fired by a fragment navigation would be harmless anyway.

The different-hash branch defers nothing and leaves the apply to `onHashChange`. So each click applies its view at most once.

### Session switch between click and timer (not reproducible)

- The pushState branch reads the active session id at click time, and the timer fires about one task later.
- No UI control both carries a deep link and joins or switches a session.
- A switch inside that window would need an unrelated task, such as an SSE message, to land within milliseconds and also change `sessionId`. That is theoretical, and it was not reported.
- Even if it happened, Canvas resolves ids against the graph present at apply time and reports unknown ids through the "Not in this graph" notice. A wrong focus would not be applied silently.

### Timer cleanup

- The effect has `[]` deps, so pending timers are cleared only on unmount.
- In StrictMode, the dev double-mount cleanup clears timers from the first mount, which cannot have any yet.
- The new test `unmounting before the deferred request fires drops it` covers the unmount case.

### Whole-PR sweep

Nothing new beyond iterations 1 to 7. The areas re-checked were:
- `viewLink.ts`, `viewLinkStore.ts`, `traceStore.ts`;
- Canvas deep-link apply effect, NodeContextMenu;
- ProposalPanel and ReviewPanel links;
- `mcp.py` `build_view_url`, `serve()` banner, and the docs.

## Coverage & limitations

- **UI gates:** `npx vitest run` passed (111 files, 1089 tests), and `npm run typecheck` and `eslint src/App.tsx` were clean.
- **Python:** pytest on `test_collab_view_url.py`, `test_collab_mcp.py` and `test_server_serve_banner.py` gave 73 passed. `ruff check` was clean on the touched modules.
- **Browser coverage:** Chromium only, through Playwright. Firefox and Safari ordering of timer versus navigation tasks was not tested; the deferral relies only on `setTimeout` running after the current click task, which every browser guarantees.
- **Untested:** the expanded-chat (`OverlayModal`) links were not re-driven in the real browser this iteration. They share the same capture listener and `requestAfterClick` path, and jsdom covers them.
- **Cleanup:** all servers started for this check were stopped, and no source files were modified.
