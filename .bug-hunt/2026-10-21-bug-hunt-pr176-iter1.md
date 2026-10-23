# Bug Hunt Report: PR #176 (iteration 1)

## Summary

**Scope:** `git diff main...HEAD` on `feature/canvas-deep-links`. Covered: `ui/src/io/viewLink.ts` (parse/format), `ui/src/store/viewLinkStore.ts` (pending slots, `copyViewLink`), the deep-link apply effect and "Copy link" entry points in `ui/src/canvas/Canvas.tsx`, `NodeContextMenu.tsx`, `ProposalPanel.tsx`, `ReviewPanel.tsx`, App mount/hashchange wiring in `ui/src/App.tsx`, `traceStore.setLens`, `build_view_url` / `_with_view_url` / `view_link` in `emergentflow/collab/mcp.py`, the `serve()` banner/flag in `emergentflow/server/app.py`, and the agent docs.

**Confirmed findings:** 4 (High 1, Medium 2, Low 1).

**Assessment:** The hash grammar holds up. Python `build_view_url` → TS `parseViewHash` round-trips correctly, including ids that contain `~ , & = # %`, spaces and non-ASCII text (checked). Malformed input is handled safely. The bugs sit at the edges, where links are produced and where they meet existing view features. Links copied in the canvas pick up the wrong session (or none). Links into a collapsed group or a composite subgraph resolve to nothing useful. Clicking the same link a second time does nothing.

## Findings

### [HIGH] — "Copy link" builds the URL from `window.location.search`, not the active session, so the link drops the session or names the wrong one
- **Location:** `ui/src/io/viewLink.ts:155-160` (`buildViewUrl`), called from `ui/src/store/viewLinkStore.ts:94` (`copyViewLink`)
- **Class:** State desync (URL vs store)
- **Confidence:** Confirmed
- **Description:** `buildViewUrl` concatenates `location.origin + pathname + search + hash`. Nothing in the UI ever writes `?session=` into the URL: `grep replaceState|pushState` finds no hits in `ui/src`. Two in-app paths join a session without changing `location.search`:
  - `ChatModal`'s "Start chat" → `sessionStore.createAndJoin()`
  - `CodingAgentsSection` → `sessionStore.join(id)`

  In either case every "Copy link" button produces a link with no session or a stale one. This covers the proposal card, the review thread, the trace banner and the node context menu. The proposal and review buttons only render while a session is active, so those links are always meant for a session.
- **Evidence / Reproduction** (vitest, run under `ui/`):
  ```ts
  test("REPRO 1a: copied link omits the active session when it was created in-app", async () => {
    window.history.replaceState(null, "", "/");
    useSessionStore.setState({ sessionId: "sess-B", status: "connected" });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const url = await copyViewLink({ proposal: "p1" });
    expect(url).toContain("session=sess-B");
  });
  test("REPRO 1b: copied link carries a stale ?session after switching sessions", async () => {
    window.history.replaceState(null, "", "/?session=sess-A");
    useSessionStore.setState({ sessionId: "sess-B", status: "connected" });
    // ...same clipboard stub...
    const url = await copyViewLink({ proposal: "p1" });
    expect(url).toContain("session=sess-B");
  });
  ```
  Observed:
  - 1a: `http://localhost:3000/#proposal=p1`. No session. The recipient's App never calls `join`, shows "Not in this session: proposal "p1"", and opens an empty modal, because `ProposalPanel` returns null without a session.
  - 1b: `http://localhost:3000/?session=sess-A#proposal=p1`. The link opens the wrong session.
- **Impact:** The main human→human sharing path is broken in the common in-app chat flow. Proposal and review links never work there, and focus/reach links open a blank local canvas or a different session's graph.
- **Remediation:** In `copyViewLink`, build the search from the session store instead of the current URL, for example:
  ```ts
  const sid = useSessionStore.getState().sessionId;
  const search = sid ? `?session=${encodeURIComponent(sid)}` : "";
  const url = buildViewUrl(state, { origin: location.origin, pathname: location.pathname, search });
  ```
  Optionally also `history.replaceState` the `?session=` param inside `createAndJoin`/`join`, so a refresh keeps the session.

### [MEDIUM] — `#focus=<id>&reach=…` on a node hidden in a collapsed group dims the whole canvas and highlights nothing
- **Location:** `ui/src/canvas/Canvas.tsx:599` (`setReach(pendingView.reach)` with raw focus ids); reach computation at `ui/src/canvas/Canvas.tsx:209` (`computeReach(selectedNodeIds, …)`)
- **Class:** Interaction with collapsed groups / existing trace feature
- **Confidence:** Confirmed
- **Description:** `applyCollapsedGroups` removes collapsed members from `rawNodes`, and their edges are re-anchored onto the group node. The route mode maps endpoints through `visibleId()` to handle this, and #175 fixed the same problem for route-pick. The deep-link path does not:
  - it selects the hidden member id;
  - it calls `setReach`;
  - `computeReach` then starts from an id that is not in `nodeIds` and has no edges.

  Collapse state is per viewer, so an agent's `add_node`/`set_param` `view_url` (`focus=<node>`) cannot know the node is hidden. The same applies to links sent by a human whose groups are expanded.
- **Evidence / Reproduction:**
  ```tsx
  test("REPRO 2", async () => {
    const a = add(0, 0); const b = add(200, 0); const c = add(400, 0);
    link(a, b); link(b, c);
    const groupId = useGraphStore.getState().groupSelection([b, c])!;
    useCollapseStore.getState().setCollapsed(groupId, true);
    const { container } = render(<Canvas />);
    act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${c}&reach=up`)));
    await waitFor(() => expect(useTraceStore.getState().mode).toBe("reach"));
    expect(traceOf(container, a)).toBe("traced");
  });
  ```
  Observed:
  - Banner: "Tracing upstream reach".
  - `a`: `data-trace="dimmed"`.
  - The collapsed group node has class `ef-trace-dimmed`.
  - The whole canvas is dimmed, and the focused node is invisible and selected.
- **Impact:** A link meant to show "here is what feeds this node" shows an all-dimmed canvas with nothing highlighted. Plain `focus` links also select an invisible node, and centring falls back to the member's raw position.
- **Remediation:** In the apply effect, map each focus id to its visible representative before selecting and tracing: `const vis = (id) => { const g = nodes[id]?.groupId; return g && collapsedGroupIds.has(g) ? g : id; }`. Alternatively, expand the containing group with `useCollapseStore.getState().setCollapsed(groupId, false)` before applying, which is probably the better UX for "land on the change". Apply the same mapping in `computeReach`'s roots for consistency.

### [MEDIUM] — "Copy link to node" / trace-banner "Copy link" inside a composite subgraph produces a link that can never resolve
- **Location:** `ui/src/canvas/Canvas.tsx:843` (`onCopyLink={() => void copyViewLink({ focus: [contextMenu.nodeId] })}`), `ui/src/canvas/Canvas.tsx:630` (`traceLink`), against `ui/src/canvas/Canvas.tsx:567` (the apply path clears the subgraph and resolves ids against top-level `nodes` only)
- **Class:** Producer/consumer contract mismatch
- **Confidence:** Confirmed
- **Description:** The context menu and the trace banner are still available while browsing a composite's subgraph, and they copy subgraph-local node ids. The apply effect, however, treats every id as top-level: it calls `useSubgraphStore.clear()` and then looks the id up in `useGraphStore.nodes`. The copied link therefore always reports the node as missing. Opening it also throws the user out of the subgraph they were in.
- **Evidence / Reproduction:** A graph with composite `comp1` containing subgraph node `n1`:
  ```tsx
  fireEvent.dblClick(container.querySelector('[data-testid="composite-node"]')!); // enter subgraph
  fireEvent.contextMenu(container.querySelector('.react-flow__node[data-id="n1"]')!);
  fireEvent.click(await screen.findByTestId("node-context-menu-copy-link"));
  const url = writeText.mock.calls[0][0];               // "http://localhost:3000/#focus=n1"
  act(() => useViewLinkStore.getState().request(parseViewHash(new URL(url).hash)));
  ```
  Observed:
  - notice `Not in this graph: node "n1"`
  - breadcrumbs `0` (subgraph exited)
  - selection `{}`
- **Impact:** A "Copy link" action the UI offers is guaranteed to produce a dead link.
- **Remediation:** Either:
  - hide or disable "Copy link to node" and the banner "Copy link" when `isInSubgraph` (`onCopyLink={isInSubgraph ? undefined : …}`, and `traceLink` returns null when `isInSubgraph`); or
  - extend the grammar with a composite path, e.g. `sub=<compositeId>[~<compositeId>]`, and have the apply effect push those breadcrumbs instead of clearing them.

### [LOW] — Clicking the same deep link a second time does nothing (the hash is never cleared, so no `hashchange` fires)
- **Location:** `ui/src/App.tsx:262-266` (hashchange listener); nothing clears `location.hash` after a view is applied
- **Class:** Stale state / event-driven re-apply
- **Confidence:** Confirmed
- **Description:** In-app links work only through `hashchange`. Chat messages render as plain `<a>` via ReactMarkdown and navigate in the same tab, so when the URL's path and search match, only the hash changes. Once a link like `#focus=n-scale` has been applied, the hash stays in the URL. If the user pans away or clears the trace and then clicks the same link again, the URL does not change and no event fires. This also happens when an agent re-posts the same `view_url` after a second edit to the same node.
- **Evidence / Reproduction:**
  ```ts
  let n = 0; window.addEventListener("hashchange", () => n++);
  window.location.hash = "#focus=a"; await tick();
  window.location.hash = "#focus=a"; await tick();
  // n === 1 (second identical navigation fires no event)
  ```
  Observed: count `1`. This matches the HTML spec: `hashchange` fires only when the fragment changes.
- **Impact:** Re-clicking a link appears to do nothing. Agents repeatedly point at the same node, so this will come up.
- **Remediation:** After `request(...)` consumes the hash, both on mount and in `onHashChange`, clear it with `history.replaceState(null, "", location.pathname + location.search)`. The next click on the same link then changes the URL again. Alternatively, intercept same-origin anchor clicks in `ChatModal` (a `components={{ a }}` override) and call `request(parseViewHash(new URL(href).hash))` directly.

## Notes & unverified leads
- **Round-trip encoding verified correct.** I ran Python `build_view_url('s', focus=['a~b,c&d=e#f %ü','x'], reach='upstream', route=['r~1','r,2'], lens=['st~ats'], edge='e&1', proposal='p#1', review='r=1')` through TS `parseViewHash`. Every field decoded to the original value. Not a bug.
- **`build_view_url(route="ab")`** (a bare string) is accepted as `route=a~b`, because `list("ab")` splits it into characters. It is unreachable via MCP, since the `view_link` schema types `route` as `list[str]`, and internal callers never pass a string. Not reported.
- **Lens validation uses the catalog from `useCatalog()`.** The catalog starts as the static fallback and is later replaced by the live `/catalog`. If the live server catalog had families the static one lacks, and a lens link were applied before the fetch resolved, those families would be dropped with a "Not in this graph" notice. Not reproduced; today's static catalog matches.
- **`hashchange` during an in-flight `join()`.** The handler calls `request()` without waiting for the session graph. The pending view could be applied to the pre-join graph and report false "missing" ids. Plausible but not reproduced.
- **Duplicate toast text.** After "Copy link", a subsequent unknown-id notice is appended ("Link copied; Not in this graph: …"), because `addNotice` concatenates onto the 4 s-lived "Link copied" notice. Cosmetic.
- **`CANVAS_ATTACHED`** is set only by `serve()`. Running the app with `uvicorn emergentflow.server.app:create_app` (no `serve()`) would make `/mcp/invoke` tools omit `view_url` even though they share the canvas store. This is consistent with the docs, which say "inside `emergentflow serve`".

## Coverage & limitations
- I wrote and ran throwaway vitest repros (deleted afterwards; a copy is kept outside the repo at `/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/viewLinkRepro.test.tsx`) and ran Python snippets via `uv run`. No source files were modified.
- Not exercised in a real browser: actual clipboard permission flows, real React Flow `fitBounds` geometry, and cross-origin `127.0.0.1` vs `localhost` navigation.
- Not covered: the MCP-over-HTTP bridge end to end with a live server, and the ProposalPanel/ReviewPanel scroll behaviour beyond reading the code.
