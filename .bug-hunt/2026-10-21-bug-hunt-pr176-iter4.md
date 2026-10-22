# Bug Hunt Report: PR #176 (iteration 4)

## Summary

Scope: `git diff main...HEAD`, focusing on fix commit 93fe033. That commit added the one-shot
`deepLinkEchoRef` guard in `onSelectionChange` and the new `onPaneClick` in
`ui/src/canvas/Canvas.tsx`. I also re-read the MCP `view_url`/`view_link` code, the
Proposal/Review "Copy link" buttons, `traceStore.setLens`, `viewLinkStore`, and the docs.

One LOW finding is confirmed. The guard is armed whether or not React Flow actually echoes the
deep-link selection. When no echo comes, the arm stays live, and a later collapse of a group around
a still-visible focused node gets swallowed. The two leads from the brief are answered below, and
neither is a bug:

- **Multiple echoes:** a combined nodes-and-edge deep link produces one echo, not two.
- **Interference:** `onPaneClick` doesn't interfere with connection drags, box selection, context
  menus or route picking.

The existing `Canvas.test.tsx` passes (46 tests).

## Findings

### [LOW] — The echo guard stays armed when React Flow sends no echo, so a later collapse around a focused visible node doesn't deselect it

- **Location:** `ui/src/canvas/Canvas.tsx`. The arm is set in the deep-link apply effect
  (`deepLinkEchoRef.current = focus.some((id) => visibleId(id) !== id) ? {…} : null`). It is
  consumed in `onSelectionChange`.
- **Class:** State desync / logic error. The one-shot guard assumes an echo that doesn't always
  arrive.
- **Confidence:** Confirmed

**Description.** The apply effect arms `deepLinkEchoRef` whenever the linked focus includes a node
hidden in a collapsed group. It assumes React Flow will send exactly one echo report, which then
disarms it. But React Flow's `SelectionListener` only reports when its own set of selected ids
changes. If the visible part of the linked selection is already what React Flow has selected,
nothing is reported and the arm stays set. One way to get there: the user has `a` selected and
clicks `#focus=a,c`, where `c` is hidden.

The store objects don't change after that, so the next report still matches the arm. Suppose the
user then collapses the group that contains `a`. React Flow reports `{nodes: [], edges: []}`. That
equals the "rendered subset", which is now `[]` because `a` is hidden too, so the report is ignored.
`a` and `c` both stay selected, even though both are hidden.

The same collapse clears the selection when the echo did arrive, for example when some other node
`z` was selected before the link. That is the behaviour 93fe033 intends ("collapsing a group around
the selected node deselects it again").

**Evidence / Reproduction.** I wrote a throwaway vitest file and ran it with
`npx vitest run src/canvas/Iter4.repro.test.tsx`, using real React Flow and the same store setup
as `Canvas.test.tsx`. A copy is saved at
`/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/iter4/Iter4.repro.test.tsx`.

```tsx
const scenario = async (prior: "a" | "z") => {
  const z = add(0, 600);
  const a = add(0, 0);
  const a2 = add(0, 200);
  const b = add(400, 0);
  const c = add(600, 0);
  const g1 = useGraphStore.getState().groupSelection([b, c])!;   // c will be hidden
  const g2 = useGraphStore.getState().groupSelection([a, a2])!;  // a's group, expanded
  useSelectionStore.getState().clear();
  useCollapseStore.getState().setCollapsed(g1, true);
  const { container, unmount } = render(<Canvas />);
  const priorId = prior === "a" ? a : z;
  act(() => useSelectionStore.getState().replaceSelection([priorId]));
  await waitFor(() => expect(container.querySelector(`.react-flow__node[data-id="${priorId}"]`)).toHaveClass("selected"));
  act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${a},${c}`)));
  await tick();
  const afterLink = sel();
  fireEvent.click(container.querySelector(
    `.react-flow__node[data-id="${g2}"] [data-testid="group-node-collapse-toggle"]`) as HTMLElement);
  await waitFor(() => expect(container.querySelector(`.react-flow__node[data-id="${a}"]`)).toBeNull());
  await tick();
  const afterCollapse = sel();
  unmount();
  return { afterLink, afterCollapse, expectedLink: [a, c].sort() };
};

test("R2 control: prior selection z (echo consumed) -> collapsing a's group clears", async () => {
  const r = await scenario("z");
  expect(r.afterLink).toEqual(r.expectedLink);
  expect(r.afterCollapse).toEqual([]);
});

test("R2 stale arm: prior selection a (no echo) -> collapsing a's group should clear too", async () => {
  const r = await scenario("a");
  expect(r.afterLink).toEqual(r.expectedLink);
  expect(r.afterCollapse).toEqual([]);
});
```

Results:

- Control (the prior selection was `z`): **passes**. `afterLink = [a, c]`, `afterCollapse = []`.
- Stale arm (the prior selection was `a`): **fails**. `afterLink = [a, c]` and
  `afterCollapse = [a, c]` (`AssertionError: expected [ …(2) ] to deeply equal []`).

The deep link leaves the store in the same state in both runs. The only difference is whether
React Flow had a reason to report, and that difference changes how the same collapse behaves.

**Impact.** This is limited and recoverable. After a deep link names a visible node the user had
already selected plus a hidden member, collapsing that visible node's group leaves both hidden
nodes selected:

- Selection-driven actions keep acting on nodes the user can't see. Ctrl+C, the U/D/R traces, the
  Group toolbar count and the reach-trace roots all use them.
- A pane click still clears the selection through the new `onPaneClick`.
- Plain editing that doesn't involve a deep link is not affected.

**Remediation.** Arm only when an echo is actually expected. Compare the rendered subset of the new
selection with what React Flow currently has selected (for example from the previous store
selection filtered through `visibleId`), and arm only if they differ. Alternatively, drop the arm
after the next commit, for example by clearing it in a `requestAnimationFrame` or effect after the
apply, so a missing echo can't leave it live. Add a regression test for "link `#focus=a,c` while `a`
is selected → collapse `a`'s group → selection clears".

## Notes & unverified leads

- **Multiple echoes: checked, no bug.** `#focus=a,c&edge=e`, where `e` is visible, `a` is visible,
  `c` is hidden and `z` was selected before the link, produces one combined report. The selection
  ends as `{a, c}` plus edge `{e}` (test R1 in the scratchpad file passes). React Flow's
  `SelectionListener` reports on mount and then only when the selected-id set changes, and the
  mount report fires before `onInit` sets `flowReady`, so it can't consume the arm. StrictMode's
  double effects run only on mount, while `flowReady` is still false, so the deep-link effect does
  nothing there.
- **Link applied before React Flow mounts, or after a session join.** The effect is gated on
  `flowReady`, which is set in `onInit`, and re-runs when `nodes` changes. After `join()`,
  `loadIR` runs before `request(view)`, so the ids resolve against the loaded graph.
- **`onPaneClick` interference: checked, none found.**
  - React Flow 12.11.1 skips `onPaneClick` after a selection drag
    (`selectionInProgress`) and after a connection that ends on the pane.
  - Node context menus don't fire pane clicks.
  - The handler does nothing unless a hidden id is selected, so route picking and ordinary pane
    clicks behave as on main.
  - `selectionOnDrag` is inert here because `panOnDrag` defaults to `true`, so plain pane clicks go
    through React Flow's `onClick`.
- **Empty Shift+drag box select.** With only hidden nodes selected, an empty marquee leaves the
  selection in place. React Flow's `resetSelectedElements` changes nothing, so it doesn't report,
  and `onPaneClick` is suppressed after a selection drag. On main, an empty marquee clears a visible
  selection. I did not reproduce this in jsdom, and a pane click recovers.
- **Hidden selected edge.** `#edge=<id>` for an edge whose two endpoints are inside the same
  collapsed group can stay selected in the store, and `onPaneClick` only checks nodes. Nothing
  reads `selectionStore.edges` except edge rendering, so I found no user-visible effect. Not
  reported.
- **Python/MCP.** `build_view_url` encoding (`quote(safe="")` plus `~`) round-trips through the
  `parseViewHash` decoding of `,` and `~` separators. `view_url` is gated on `CANVAS_ATTACHED`,
  which `serve()` sets. The HTTP bridge forwards to `/mcp/invoke` inside the serve process, so the
  docs are right that bridge and in-app-chat calls get `view_url`. No issues.
- **Proposal/Review copy buttons, `setLens`, `viewLinkStore`.** `join()` loads proposals and
  reviews before `request(view)`, so the "Not in this session" notice doesn't fire falsely.
  `copyViewLink` uses the active `sessionId`. `setLens` dedups the families and resets on an empty
  list. No issues. (There is a cosmetic `}:ReviewPanelProps` spacing nit, not reported.)

## Coverage & limitations

- Reviewed:
  - the full PR diff stat;
  - the `Canvas.tsx`, `App.tsx`, `mcp.py`, `server/app.py`, `viewLink.ts`, `viewLinkStore.ts`,
    `traceStore.ts`, `ProposalPanel.tsx`, `ReviewPanel.tsx` and `NodeContextMenu.tsx` diffs;
  - the agent docs;
  - React Flow 12.11.1's `SelectionListener`, pane click and pointer handlers, and selection store
    actions;
  - `mcp_bridge.py`.
- Verified with vitest against HEAD (93fe033). The throwaway test file has been removed, and the
  copy is kept at the scratchpad path above. The existing `Canvas.test.tsx` passes (46 tests).
- jsdom doesn't measure layout, so real node clicks and box selects weren't simulated. The
  selection was set through the store, and collapse and pane clicks were real DOM events.
