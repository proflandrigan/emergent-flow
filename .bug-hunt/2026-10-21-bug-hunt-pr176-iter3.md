# Bug Hunt Report: PR #176 (iteration 3)

## Summary

Scope: `git diff main...HEAD`, with most attention on fix commit 932a5e3 (the raw-focus-id selection,
the `onSelectionChange` echo guard in `Canvas.tsx`, and the delegated same-hash click listener in
`App.tsx`). One finding confirmed: the echo guard also fires during ordinary editing, outside deep
links. If a selected node ends up hidden in a collapsed group, it stays selected and a pane click
can no longer clear it. This is a regression against d9a5b5d. The click listener held up under
every case I checked. Existing `App.test.tsx` and `Canvas.test.tsx` pass (61 tests).

## Findings

### [MEDIUM] — Collapsing a group that contains the selected node no longer deselects it, and a pane click can't clear it afterwards

- **Location:** `ui/src/canvas/Canvas.tsx`, `onSelectionChange` (the `selectionEchoRef` guard,
  `if (selected.some((id) => visibleId(id) !== id)) { … if (same(nodeIds, shownNodes) && same(edgeIds, shownEdges)) return; }`)
- **Class:** Regression / state desync (the selection store and React Flow's selection disagree)
- **Confidence:** Confirmed

**Description.** The guard is meant to ignore React Flow's echo after a deep link selects a node
that is hidden in a collapsed group. But it decides based on the current selection alone and does
not check where that selection came from, so it also catches a common action: select a member
node, then click the group's collapse chevron. The chevron calls `stopPropagation` and is marked
`nodrag`, so the click does not select the group. When the member disappears from the rendered
nodes, React Flow reports `{nodes: [], edges: []}`. On d9a5b5d that report cleared the selection.
Now the guard treats it as an echo (`shownNodes` is `[]`, which equals `nodeIds`) and returns, so
the hidden member stays selected in `useSelectionStore`.

Nothing in React Flow can clear it after that. React Flow already has nothing selected, so a pane
click (`resetSelectedElements`) or an empty box-select changes nothing. React Flow's
`SelectionListener` only fires when its own selected-id set changes, so `onSelectionChange` is
never called again. Escape only resets the trace. The only way out is to select some visible
element. The same stuck state follows any `#focus=` deep link to a hidden member: once the link is
applied, a pane click doesn't deselect.

**Evidence / Reproduction.** I wrote a throwaway vitest file and ran it with
`npx vitest run src/canvas/HiddenSel.repro.test.tsx` (real React Flow, same setup as
`Canvas.test.tsx`). A copy is saved at
`/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/iter3/HiddenSel.repro.test.tsx`.

```tsx
test("REPRO: collapsing a group whose member is selected, then clicking the pane, clears the selection", async () => {
  const add = (x: number, y: number) => useGraphStore.getState().addNodeFromSpec(loadCsv, { x, y });
  const a = add(0, 0);
  const b = add(200, 0);
  const c = add(400, 0);
  const groupId = useGraphStore.getState().groupSelection([b, c])!;
  useSelectionStore.getState().clear();
  const { container } = render(<Canvas />);
  const cEl = await waitFor(() => {
    const el = container.querySelector(`.react-flow__node[data-id="${c}"]`);
    if (!el) throw new Error("no c");
    return el as HTMLElement;
  });
  act(() => useSelectionStore.getState().replaceSelection([c]));   // user selects member c
  await waitFor(() => expect(cEl).toHaveClass("selected"));
  fireEvent.click(container.querySelector(                          // user clicks collapse chevron
    `.react-flow__node[data-id="${groupId}"] [data-testid="group-node-collapse-toggle"]`) as HTMLElement);
  await waitFor(() => expect(container.querySelector(`.react-flow__node[data-id="${c}"]`)).toBeNull());
  await new Promise((r) => setTimeout(r, 50));
  console.log("after collapse:", JSON.stringify(useSelectionStore.getState().nodes));
  fireEvent.click(container.querySelector(".react-flow__pane") as HTMLElement); // user clicks empty canvas
  await new Promise((r) => setTimeout(r, 50));
  console.log("after pane click:", JSON.stringify(useSelectionStore.getState().nodes));
  expect(Object.values(useSelectionStore.getState().nodes).some(Boolean)).toBe(false);
});
```

Results:

- HEAD (932a5e3): **fails**. `after collapse: {"node-…":true}`, then `after pane click: {"node-…":true}`.
- d9a5b5d (git worktree, same test): **passes**. `after collapse: {}`, then `after pane click: {}`.

A second test, REPRO2, selects a hidden member with `#focus=<c>` and then clicks the pane. On HEAD
the selection still holds `{c: true}`. This variant can't be compared with d9a5b5d, which selected
the group id instead.

**Impact.** The Inspector (`selectedNodeId(selNodes)`) keeps showing a node the user can't see and
can't deselect by clicking empty canvas. Selection-driven actions still act on that hidden node:
Ctrl+C copies it, U/D/R start traces rooted at it, the Group/Ungroup enablement counts it, and
Shift+E asks React Flow to fit a node id that isn't rendered. Before 932a5e3, collapsing a group
dropped its hidden members from the selection, which matched what React Flow shows.

**Remediation.** Scope the guard to the deep-link case. For example, set a one-shot ref in the
deep-link apply effect, or record the ids it selected, and ignore only the next matching echo. Or
handle pane clicks and empty box-selects explicitly with an `onPaneClick={() => clearSelection()}`
(plus the box-select equivalent), and keep the old "React Flow is authoritative" behaviour for
selections that didn't come from a deep link. Add a regression test for "select member → collapse
group → pane click clears".

## Notes & unverified leads

- **StrictMode double mount (dev only).** Now that the hash is no longer cleared, the second
  StrictMode run of the mount effect re-parses the same hash and calls `request(view)` again; with
  `?session=`, it also queues a second `join().then(request)`. `request` is idempotent and
  `addNotice` drops a repeated identical message, so I saw no wrong behaviour. Not reported.
- **Same-hash click listener.** Checked these cases and found no issues:
  - Encoding: `anchor.hash` and `location.hash` both come from the URL serializer, and wherever
    the strings differ the browser sees a different fragment and fires `hashchange`, so the view
    is applied exactly once either way.
  - `target="_blank"` is skipped. Modifier keys and middle-click are skipped.
  - React `preventDefault` is respected because React's root listener runs before the document
    listener.
  - `href="#"` and non-view fragments parse as empty, so nothing happens.
  - Links with a different hash return early and are left to `hashchange`, so there is no double
    apply.
  - Chat, note and result-card markdown renders plain `<a>` without `target`, so in-app deep
    links reach the listener.
- **`download` / `rel` anchors.** `<a download href="#focus=x">` would also re-apply the view
  instead of being ignored. No such anchor exists in the app. Theoretical only.
- **Undo/redo and deletion with a hidden selected node.** If the hidden node is removed (for
  example undoing its creation), `activeNodes[id]` is undefined, so `visibleId(id) === id`, the
  guard switches off and React Flow's report applies normally. Undoing the grouping makes the node
  visible and still selected, which is consistent. No issue found.
- **Edge interplay.** Clicking any visible edge or node while a hidden node is selected gives a
  React Flow selection different from the shown subset, so it replaces the selection correctly.
  Only an empty React Flow selection gets stuck, as in the finding above.

## Coverage & limitations

- Reviewed the full `git diff main...HEAD` stat, the 932a5e3 diff in detail (`App.tsx`,
  `Canvas.tsx`, tests), React Flow 12.11.1's `SelectionListener` / pane-click source, `GroupNode`
  collapse toggle, `viewLinkStore`, and how chat/markdown renders links.
- Verified with vitest against HEAD and against a d9a5b5d worktree. All throwaway test files and
  the worktree have been removed. The repro copy is kept in the scratchpad path above.
- jsdom doesn't measure nodes, so a real node *click* couldn't be simulated. The selection was set
  through the store, which is equivalent to React Flow's click result. Pane click and collapse
  toggle are real DOM events. Browser-only behaviour (Back/Forward, same-fragment navigation not
  firing `hashchange`) was reasoned from the HTML spec, not run in a real browser.
- Python/MCP changes (`emergentflow/collab/mcp.py`, `server/app.py`) were not re-examined this
  iteration beyond what earlier iterations covered.
