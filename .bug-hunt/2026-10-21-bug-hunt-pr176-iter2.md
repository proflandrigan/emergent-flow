# Bug Hunt Report: PR #176 (iteration 2)

## Summary

**Scope:** `git diff main...HEAD` on `feature/canvas-deep-links`, focusing on the iteration-1 fix commit d9a5b5d:
- `withSessionParam` / `copyViewLink` session id
- `visibleId` in the reach roots and in the deep-link apply effect
- hiding Copy link in subgraphs
- `clearViewHash` in `App.tsx`

I also re-checked the Python `build_view_url` against the TS parser.

**Confirmed findings:** 2 (Medium 1, Low 1). Both are regressions introduced by d9a5b5d.

**Assessment:**
- The session-param fix and the subgraph Copy-link hiding hold up.
- The collapsed-group fix replaces the linked node in the **selection** with the group id. That id is wrong as soon as the group is expanded or the link is re-shared.
- Clearing the hash with `replaceState` leaves behind history entries that do nothing when you press Back.

## Findings

### [MEDIUM] — Deep-link focus is rewritten to the collapsed group id: expanding the group, or re-sharing the link, gives an all-dimmed reach trace
- **Location:** `ui/src/canvas/Canvas.tsx` deep-link apply effect: `const focus = [...new Set(pendingView.focus.filter(knownNode).map(visibleId))];` followed by `replaceSelection(focus, …)`. The banner link reads the selection in `traceLink` (`{ focus: selectedNodeIds, reach: traceDirection }`).
- **Class:** Regression (lossy id mapping stored in persistent state)
- **Confidence:** Confirmed
- **Description:** In d9a5b5d, `visibleId` maps the linked member id to its collapsed group id **before** the selection is set, so the original node id is lost. The fix also maps reach roots through `visibleId` inside the `trace` memo, so the mapping in the selection was not needed to make the trace work.

  A group node that is not collapsed has no edges, because edges attach to its members. Once the group is no longer collapsed, a reach rooted at the group highlights nothing. This shows up in two ways:
  1. **Same user.** The user lands on `#focus=<member>&reach=up` with the group collapsed, then expands the group to look at the node. The selection is still the group, and the whole canvas goes dimmed. The banner still reads "Tracing upstream reach". Before the fix, the selection was the member, and expanding the group traced correctly.
  2. **Re-shared link.** The banner "Copy link" now produces `#focus=<groupId>&reach=up`, not the member id. Collapse state is per viewer, so a recipient whose group is expanded gets an all-dimmed canvas.
- **Evidence / Reproduction:** Vitest, run in the "Canvas deep links" describe of `Canvas.test.tsx` with its `add`/`link`/`traceOf` helpers. A copy is at `/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/iter2/iter2Repro.test.tsx`.
  ```tsx
  test("REPRO A", async () => {
    const a = add(0, 0); const b = add(200, 0); const c = add(400, 0);
    link(a, b); link(b, c);
    const groupId = useGraphStore.getState().groupSelection([b, c])!;
    useCollapseStore.getState().setCollapsed(groupId, true);
    const { container } = render(<Canvas />);
    act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${c}&reach=up`)));
    await waitFor(() => expect(traceOf(container, a)).toBe("traced"));
    act(() => useCollapseStore.getState().setCollapsed(groupId, false)); // user expands the group
    await waitFor(() => expect(container.querySelector(`.react-flow__node[data-id="${c}"]`)).not.toBeNull());
    expect(traceOf(container, c)).toBe("traced");   // FAILS: "dimmed"
  });
  test("REPRO B", async () => {
    // same graph, group collapsed, clipboard stubbed
    act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${c}&reach=up`)));
    await waitFor(() => expect(traceOf(container, a)).toBe("traced"));
    fireEvent.click(await screen.findByTestId("trace-banner-copy-link"));
    const url = writeText.mock.calls[0][0];
    expect(url).toContain(`focus=${c}`);            // FAILS
  });
  ```
  - **REPRO A at HEAD:**
    - selection is `{<groupId>: true}` and mode is `reach`
    - a, b and c are all `dimmed`
    - banner: "Tracing upstream reach"
  - **REPRO A at cd08845 (before the fix):** a, b and c are all `traced`. I ran this in a temporary worktree, waiting on `mode === "reach"` because the first assertion is the iter-1 bug.
  - **REPRO B at HEAD:**
    - the copied URL is `…/#focus=<groupId>&reach=up`
    - after applying it with the group expanded, a, b and c are all `dimmed` and the selection is `{<groupId>: true}`
- **Impact:** The fix creates the opposite of the iter-1 bug. A user who lands on a change and opens the group to look at it gets a fully dimmed canvas. Links re-shared from the banner no longer point at the node the agent named.
- **Remediation:** Keep the raw linked ids in the selection: `replaceSelection(pendingView.focus.filter(knownNode), …)`. The `trace` memo already maps reach roots through `visibleId`, so keep `visibleId` only for the centring targets. Alternatively, expand the containing group when the link is applied (`useCollapseStore.getState().setCollapsed(groupId, false)`), so that nothing has to be mapped.

### [LOW] — `clearViewHash` uses `replaceState`, so Back no longer moves between deep-link views; each clicked link leaves a history entry that does nothing
- **Location:** `ui/src/App.tsx` `clearViewHash()`, called from `onHashChange`
- **Class:** Regression (browser history)
- **Confidence:** Confirmed
- **Description:** Clicking an in-app link pushes `…?session=s#focus=a`. The handler then replaces that entry with `…?session=s`. After N link clicks there are N extra history entries, all with the same URL as the base. Moving between entries with the same URL fires `popstate` but no `hashchange`, so pressing Back changes neither the URL nor the view. Before d9a5b5d, Back went to the previous `#focus=…` entry, `hashchange` fired, and the earlier view was re-applied.
- **Evidence / Reproduction:** Vitest in jsdom. The handler does exactly what `onHashChange` does to the URL. A copy is at `/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/iter2/iter2History.test.ts`.
  ```ts
  window.addEventListener("hashchange", () => {
    window.history.replaceState(window.history.state, "", location.pathname + location.search);
  });
  history.replaceState(null, "", "/?session=s");
  location.hash = "#focus=a"; await tick();
  location.hash = "#focus=b"; await tick();
  history.back(); await tick();   // href: /?session=s  (no hashchange)
  history.back(); await tick();   // href: /?session=s  (no hashchange)
  ```
  - `history.length` grew by 2.
  - Both Back presses left the URL at `http://localhost:3000/?session=s`.
  - The event log shows only `popstate` after the two link clicks and no `hashchange`, so `onHashChange` never runs on Back.
- **Impact:** After following several agent links in chat, Back does nothing visible once per link clicked before it leaves the page. Before the fix, Back stepped through the earlier views.
- **Remediation:** Make the same link re-clickable without rewriting history. Intercept clicks on same-document view links, for example with a delegated `click` listener or a `components={{ a }}` override in `ChatModal`: when `href` has the same origin, path and search and a view hash, call `preventDefault()` and `request(parseViewHash(new URL(href).hash))`, and leave `location.hash` alone. Alternatively, clear the hash only on mount and keep it on `hashchange`.

## Notes & unverified leads
- **Hash cleared before join (design trade-off, not reported).** On mount, `clearViewHash()` runs before `join()`. If `join` fails, for example because the server is restarting, the view is dropped and the address bar no longer holds it, so a refresh after the server recovers joins the session without the deep-link target. Before the fix, a refresh retried the full link. Proven by reading the code; I judged it a trade-off rather than a defect.
- **StrictMode double mount (checked, not a bug).** In dev, StrictMode runs the mount effect twice: the second run sees an empty hash and calls `join` again. The empty `request` is a no-op, and `loadIR` does not clear the selection or trace stores, so the view survives.
- **Nested groups (pre-existing, not reported).** `visibleId` resolves only one level, which matches `applyCollapsedGroups` and `reanchorEdgesForCollapsedGroups`. A member of an inner group inside a collapsed outer group is mishandled the same way by the existing collapse rendering. That predates this PR.
- **`withSessionParam` (checked).** It keeps other query params and replaces or removes `session`. `URLSearchParams` encodes spaces as `+`, and App reads the param back with `URLSearchParams`, so the round trip is consistent. Python `build_view_url` leaves `session_id` unencoded, as it did before. Session ids are UUID-like.
- **Python ↔ TS (checked).** `reach` aliases normalise to the same three values. `lens` and `focus` dedup happens in TS only, which is harmless. `connect_ports`' `focus=[src,tgt]&edge=` is applied as selection plus edge. No mismatch found.
- **Reach dedup.** `[...new Set(selectedNodeIds.map(visibleId))]` only changes roots for hidden members. When nothing is collapsed, selection semantics are unchanged.

## Coverage & limitations
- I ran the throwaway vitest repros and then deleted them from the repo. Copies are in `/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/iter2/`. I checked the behaviour before the fix in a temporary git worktree at cd08845, which has since been removed. No source files were modified.
- Not exercised in a real browser: actual history and Back UX, and clipboard permission. The history behaviour was checked in jsdom and follows the HTML spec: `hashchange` fires only when the fragment differs.
- I did not re-run the Python suite. The Python changes since iter 1 are unchanged, and I re-checked them by reading the code.
