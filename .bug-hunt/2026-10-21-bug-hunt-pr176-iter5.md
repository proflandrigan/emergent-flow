# Bug Hunt Report: PR #176 (iteration 5)

## Summary

**Scope:** `git diff main...HEAD` at 3524f0e. Covered:
- the echo-guard machinery in `ui/src/canvas/Canvas.tsx`;
- `App.tsx` hash, click and pending-panel wiring;
- `viewLink.ts`, `viewLinkStore.ts`, `traceStore.setLens`;
- `ProposalPanel`, `ReviewPanel`, `NodeContextMenu`;
- `emergentflow/collab/mcp.py` (`build_view_url`, `_with_view_url`, `view_link`) and the `serve()` flag in `server/app.py`;
- the agent docs.

Findings from iterations 1 to 4 were not re-reported.

**Confirmed findings:** 1 (Medium 1).

**Assessment:** The echo guard is now correct as far as I can trace it, and I found no new canvas-side bugs. The one confirmed bug is in the main agent flow. Every `view_url` the in-app chat agent pastes differs from the page URL in its `?session=` query, so clicking it reloads the whole page instead of re-applying the hash in place.

## Findings

### [MEDIUM] — Clicking a `view_url` in the in-app chat reloads the whole page (with a "Leave site?" prompt), because the page URL never carries `?session=`
- **Location:**
  - `ui/src/App.tsx:260-293`: the hash and click listeners only handle same-search links.
  - `ui/src/session/sessionStore.ts:305-316`: `createAndJoin` never writes `?session=` into the URL.
  - `emergentflow/collab/mcp.py`: `build_view_url` always emits `<base>/?session=<id>#…`.
- **Class:** Integration / navigation (URL vs store desync)
- **Confidence:** Confirmed
- **Description:** The in-app chat is the main place deep links are clicked, and it starts its session with "Start chat", which calls `ChatModal`, then `createAndJoin()`. That call loads the session graph but leaves `location.search` empty. The chat agent runs inside `emergentflow serve`, where `CANVAS_ATTACHED` is true, and the docs (§7) tell it to paste the tool's `view_url`, which looks like `http://127.0.0.1:8765/?session=<id>#focus=<node>`. `ReactMarkdown` renders this as a plain `<a href>` with no `target`. When the user clicks it:
  1. App's delegated `onClick` sees `anchor.hash !== here.hash` and returns. It leaves the link to `hashchange`.
  2. The link differs from the page URL in its query (`?session=<id>` vs `""`). Under the HTML navigation rules that is not a fragment navigation, so no `hashchange` fires. The browser loads a new document.
  3. `createAndJoin`'s `loadIR` set `useFlowStore.isDirty = true` through `startDirtyTracking`, so `beforeunload` first shows the "Leave site? Changes may not be saved" prompt.
  4. After the reload, `?session=` makes App call `join()`, which reloads the server graph, and only then applies the hash. The chat modal is closed, the undo history is gone, and any local canvas edit that isn't in the server session is discarded. Nothing in `ui/src` calls `pushLocalGraph`/`replaceSessionGraph`.

  The App code comment ("Deep links clicked inside the app (chat, reviews) change only the hash") only holds when the page was opened from an agent's `open_in_ui` URL. It does not hold for the built-in chat flow.
- **Evidence / Reproduction:** A throwaway vitest file in `ui/src/` uses `App.test.tsx`'s mocks and `mockHealth`. A copy is at `/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/iter5/App.repro5.test.tsx`.
  ```tsx
  test("REPRO iter5: in-app chat view_url click is a full navigation, not a hash change", async () => {
    mockHealth("ok");
    render(<App />);
    await useSessionStore.getState().createAndJoin();          // "Start chat" path
    expect(useSessionStore.getState().sessionId).toBe("app-test-session");
    expect(window.location.search).toBe("");                    // address bar has no ?session=
    console.log("isDirty after createAndJoin:", useFlowStore.getState().isDirty);
    const href = `${window.location.origin}/?session=app-test-session#focus=n1`; // view_url shape
    const request = vi.spyOn(useViewLinkStore.getState(), "request");
    const a = document.createElement("a"); a.href = href; document.body.appendChild(a);
    fireEvent.click(a); a.remove();
    await new Promise((r) => setTimeout(r, 20));
    expect(request).toHaveBeenCalledTimes(1); // expected: applied in place
  });
  ```
  Observed (`npx vitest run src/App.repro5.test.tsx`):
  - `isDirty after createAndJoin: true`
  - jsdom logged `Error: Not implemented: navigation (except hash changes)` from `navigateFetch`. That is jsdom's full-document navigation path, not its fragment path.
  - `request calls: 0 pendingCanvas: null`, and the assertion fails with "expected "request" to be called 1 times, but got 0 times". In a real browser this is a full page load.
- **Impact:** Every agent link in the built-in chat (the "end each turn with a focused link" flow the PR adds) costs the user a page reload. Each click first shows a leave-page prompt, and the reload closes the chat and drops undo history and any local canvas edits not in the server session. The view does land eventually, after the reload.
- **Remediation:** In `createAndJoin`/`join`, write the session into the URL with `history.replaceState(null, "", withSessionParam(location.search, session.id) + location.hash)`. This also fixes refresh. Alternatively, in App's `onClick`, intercept same-origin, same-path links whose `?session=` equals the active `sessionId`: call `preventDefault()`, then `history.pushState` and `request(parseViewHash(anchor.hash))`.

## Notes & unverified leads

- **Echo guard re-verified, no bug.**
  - On mount, `flowReady` is false, so the deep-link effect does nothing. The disarm effect running on mount is harmless.
  - In a commit where both `collapsedGroupIds` and `pendingView` change, the disarm effect is declared earlier, so it runs first and the arm that follows survives. That ordering is correct.
  - The arm is set during the effect of commit N. `replaceSelection` triggers commit N+1, and React Flow's `SelectionListener` reports in a later commit, so the arm is in place before the echo.
  - The store refs check holds: `replaceSelection`, `setNodeSelected` and `clear` all create new `nodes`/`edges` objects, so any intervening selection change makes `armed.nodes !== sel.nodes`.
  - `renderedSelection` matches what React Flow renders. Group nodes are only `selected` when their own id is selected (`toRFNode(n, !!selNodes[n.id])`), hidden members are filtered exactly as `applyCollapsedGroups` does (direct `groupId` only), and re-anchored edges keep their ids.
  - The deep-link effect re-runs on `visibleId` changes but returns early, because `consumeCanvas` nulled `pendingView`.
- **Deep link applied mid-collapse.** For this to break, a `hashchange` would have to land between the collapse commit and React Flow's later report. I couldn't construct that in practice. Even then, the collapse's report would be authoritative, which is the intended behaviour. Not reported.
- **Possible amplifier, not verified.** If the user browses the canvas through a different host alias than the serve bind (for example `localhost` vs `127.0.0.1`), the link also crosses origins, so localStorage autosave differs. Not reproduced.
- **"Reviews" overflow item without a session** opens an empty modal. This matches the existing "Review proposals" item. Not reported.
- **Python.** `build_view_url(route="ab")` called directly from Python would split the string into `a~b`. MCP validates `route: list[str]`, so agents can't hit this. Not reported.
- **Docs vs behaviour.** The §7 grammar table, the encoding and the `view_link` return shape all match the code. Apart from the finding above, both docs pages describe `view_url` gating accurately.

## Coverage & limitations

- **Reviewed:** the full PR diff (TS, Python, docs), `selectionStore`, `toReactFlow` collapse helpers, `sessionStore.createAndJoin`/`join`, `flowStore.startDirtyTracking`, `ChatModal` link rendering (ReactMarkdown, no `target`) and the `/mcp/invoke` bridge wiring.
- **Existing suites pass:**
  - vitest: `App.test.tsx`, `Canvas.test.tsx`, `viewLink.test.ts` and `src/store/*`, 223 tests;
  - pytest: `test_collab_view_url.py`, `test_collab_mcp.py`, `test_server_serve_banner.py`, 73 tests.
- **Repro file:** removed from the tree; the copy is kept in the scratchpad.
- **Limitation:** jsdom doesn't implement cross-document navigation, so the reload and the `beforeunload` prompt follow from the HTML navigation rules plus the observed `isDirty = true` and jsdom's navigation path. I did not run them in a real browser.
