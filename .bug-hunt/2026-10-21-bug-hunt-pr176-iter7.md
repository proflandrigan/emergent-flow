# Bug Hunt Report: PR #176 (iteration 7)

## Summary

**Scope:**
- `git diff main...HEAD` at 68426b9, focusing on the consequences of moving App's delegated deep-link click listener to the capture phase on `document`.
- Checked: links inside CodeMirror, NoteNode and ResultCardNode markdown on the canvas, exported report HTML, the inspector, and the docked and expanded chat; StrictMode and double registration.
- Then a whole-PR sweep: `mcp.py`/`app.py`, viewLink, viewLinkStore, traceStore, Canvas, App, the panels, NodeContextMenu, and the docs.

Findings from iterations 1 to 6 were not re-reported.

**Confirmed findings:** 1 (Low 1). It is a regression introduced by 68426b9, reproduced in a real Chromium against the running app, with the commit before it (60d393b) as the control.

## Findings

### [LOW] — Re-clicking a deep link inside a canvas note or result card now selects the card instead of the linked node, and a `reach` trace re-roots on the card

- **Location:**
  - `ui/src/App.tsx:288-311`, where `onClick` calls `useViewLinkStore.getState().request(view)` synchronously.
  - `ui/src/App.tsx:316`, where `document.addEventListener("click", onClick, true)` registers it in the capture phase.
  - The deep-link apply effect in `ui/src/canvas/Canvas.tsx:616-693`.
- **Class:** Event ordering regression (side effect of the 68426b9 capture-phase change)
- **Confidence:** Confirmed
- **Description:** With a real user click, the browser runs a microtask checkpoint after each event listener callback.
  1. The capture-phase listener calls `request(view)` in two branches:
     - the same-search, same-hash re-click branch;
     - the `differsOnlyByActiveSession` pushState branch.
  2. React treats that zustand update as a discrete `click` update (SyncLane). It renders and flushes the Canvas deep-link effect in the microtask right after the listener. So `replaceSelection([focus])` and `setReach` run **before** React's root listener has dispatched the click to React Flow's `NodeWrapper`.
  3. React Flow's node `onClick` (`handleNodeClick`) then runs on the note or result card that contains the link. That node is no longer selected, so React Flow selects it and deselects every other node.
  4. The card ends up selected, not the linked node. Because the reach trace roots at the selection, the trace now traces the card.

  Before 68426b9, the listener was in the bubble phase on `document`, so it ran after React Flow's handler and the deep link won.

  The first click on a link that changes the hash is unaffected, because it is applied through `hashchange`, which is a later task. Only the in-capture `request` branches regress.
- **Evidence / Reproduction:**
  - **Setup:**
    - Ran `emergentflow serve --no-browser`.
    - Ran Vite dev servers for HEAD (68426b9, port 5199) and a throwaway worktree at 60d393b (port 5198).
    - Created a session by POSTing `/sessions` with `examples/functional_pipeline.json` plus a `notes.markdown` node `n-note`. Its content is `See [the anova](#focus=n-anova&reach=up)`.
    - Drove Chromium with Playwright's `page.click` on the note's `<a>` twice.
  - **Scripts:** copies are in `/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/iter7/`: `mkgraph2.py`, `reach_link.cjs`, plus the focus-only variant `mkgraph.py` and `note_link.cjs`. The core of the click script:
    ```js
    await page.goto(`${base}/?session=${sid}`);
    await page.waitForSelector('.react-flow__node[data-id="n-note"]');
    for (const n of [1, 2]) {
      await page.click('.react-flow__node[data-id="n-note"] a');
      await page.waitForTimeout(700);
      console.log(`after click ${n}:`, JSON.stringify(await state())); // selected ids, trace classes, hash
    }
    ```
  - **Output at HEAD (68426b9):**
    ```
    after click 1: {"selected":["n-anova"],"classes":{...,"n-note":"ef-trace-dimmed"},"hash":"#focus=n-anova&reach=up"}
    after click 2: {"selected":["n-note"], "classes":{...,"n-note":"ef-trace-traced"},"hash":"#focus=n-anova&reach=up"}
    ```
  - **Control at 60d393b (bubble phase), same script and session:**
    ```
    after click 1: {"selected":["n-anova"],"classes":{...,"n-note":"ef-trace-dimmed"},...}
    after click 2: {"selected":["n-anova"],"classes":{...,"n-note":"ef-trace-dimmed"},...}
    ```
  - **Focus-only variant** (`#focus=n-anova`, `note_link.cjs`): HEAD gave `click 1 → ['n-anova']`, then `click 2 → ['n-note']` and `click 3 → ['n-note']`. 60d393b gave `['n-anova']` on every click.
  - **Why jsdom misses it:** jsdom's `fireEvent.click` is a script-dispatched event. Microtask checkpoints only happen once the stack is empty, so no checkpoint runs between listeners and the existing vitest suite cannot see this ordering. All 443 tests pass.
- **Impact:** A link in a note or result card is the natural way to write a "see the model" pointer on the canvas. Clicking it a second time (the iteration 1 "re-click the current link" case) gives the wrong result:
  - the inspector shows the card, not the linked node;
  - a `reach` link shows the card's (empty) reach;
  - the trace banner's "Copy link" then copies a link to the card.

  The `differsOnlyByActiveSession` branch calls `request` in capture the same way, so it should behave the same when the link is clicked inside a card. That variant was not run separately. The chat panels are unaffected, because they are not React Flow nodes.
- **Remediation:** Keep `preventDefault` and `pushState` synchronous in the capture listener, but defer the apply to a later task, the way `hashchange` already arrives: `window.setTimeout(() => useViewLinkStore.getState().request(view), 0)`. A microtask is not enough. Add a Playwright-style or manual check; a jsdom test cannot reproduce the ordering, though one could at least assert that `request` runs after the click dispatch.

## Notes & unverified leads

- **CodeMirror (`ui/src/inspector/CodeEditor.tsx`):** CodeMirror renders no `<a href>`, and the SQL/Python content is plain text. There is no `contentEditable` with anchors anywhere else. Not affected.
- **Other anchors in the app:** there are no JSX `<a>` elements outside tests. Every anchor comes from `ReactMarkdown`: the chat, NoteNode, ResultCardNode, and `reportHtml`. So losing the `defaultPrevented` signal from React handlers under capture affects nothing today.
- **Note and result-card editing modes:** these render a `<textarea>`, so there are no anchors to click.
- **Drag that ends on a link:** after a drag, d3-drag adds a window *capture* click suppressor (`preventDefault` plus `stopImmediatePropagation`). That runs before the `document` capture listener, so a drag release on a link is never treated as a link click. This matches the bubble-phase behaviour.
- **Exported report HTML (`ui/src/io/reportHtml.tsx`):** it is a standalone document with no App listener. Links behave as plain navigation, the same as on main.
- **Double registration:**
  - In StrictMode, the effect cleanup removes the listener with the same `capture=true` flag, so there is no leaked second listener.
  - The only other `document` click listeners are the menu closer (`App.tsx:213`), Canvas `closeContextMenu` and `IRToolbar`. None of them handle links.
  - The same-search, different-hash branch returns without applying, so `hashchange` applies once.
- **Session id in `build_view_url`:** the session id is not percent-encoded. That is pre-existing `open_in_ui` behaviour, and session ids are UUIDs. Not reported.
- **Whole-PR sweep:** nothing new found beyond the earlier iterations.

## Coverage & limitations

- **Reviewed:**
  - `App.tsx` listeners (68426b9) and the Canvas deep-link effect;
  - NoteNode, ResultCardNode, ChatModal, OverlayModal, CodeEditor and reportHtml;
  - every `stopPropagation` and `document` click-listener site;
  - the `mcp.py` diff.
- **Tests run:**
  - vitest across App, the canvas directory, viewLink, the stores, ProposalPanel and ReviewPanel: 41 files, 443 tests, all passing;
  - pytest view-url, MCP and serve-banner: 73 passing.
- **Real-browser repro:** Playwright Chromium against the Vite dev server plus `emergentflow serve`. The servers and the throwaway worktree were removed afterwards, and no source files were modified.
- **Not run separately:**
  - the `differsOnlyByActiveSession` branch inside a card;
  - result-card links. These share `NodeWrapper` and the same code path as notes, but were not reproduced.
