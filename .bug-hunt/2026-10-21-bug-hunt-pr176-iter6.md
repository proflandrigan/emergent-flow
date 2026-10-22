# Bug Hunt Report: PR #176 (iteration 6)

## Summary

**Scope:**
- `git diff main...HEAD` at 60d393b, with a focus on 60d393b: the `differsOnlyByActiveSession` intercept in `ui/src/App.tsx`, which does `pushState` plus `request`.
- A whole-PR sweep: TS view-link code, the panels, `mcp.py`/`serve()`, and the docs.

Findings from iterations 1 to 5 were not re-reported.

**Confirmed findings:** 1 (Medium 1).

**Assessment:** 60d393b works in the docked chat and in plain page content. Back/Forward, refresh, and the stale-`?session=` cases behave correctly; details are in the Notes. The one confirmed bug is that App's delegated click listener sits on `document`, while `OverlayModal` stops click propagation inside its panel. So any link rendered in an overlay never reaches the listener. This affects the expanded chat, which renders through `OverlayModal`. There, both the 60d393b fix and the earlier "re-click the current link" fix (iteration 1, LOW) do nothing.

## Findings

### [MEDIUM] — In the expanded chat (`OverlayModal`), clicking a deep link bypasses App's click handler: an active-session `view_url` still reloads the whole page, and re-clicking the current link does nothing

- **Location:**
  - `ui/src/App.tsx:283-319`: `document.addEventListener("click", onClick)` registers in the bubble phase on `document`.
  - `ui/src/ui/OverlayModal.tsx:62`: the panel has `onClick={(e) => e.stopPropagation()}`.
  - `ui/src/session/ChatModal.tsx:604-636`: the expanded view mode renders `chatBody` inside `OverlayModal`.
- **Class:** Integration / event propagation (incomplete fix for iteration 5's MEDIUM and iteration 1's LOW)
- **Confidence:** Confirmed
- **Description:** `OverlayModal` portals to `document.body`. React 18 attaches its event listeners to the portal container, here `body`. When a native click bubbles to `body`, React dispatches the panel's synthetic `onClick`. Its `stopPropagation()` also stops the native event, so the click never reaches `document`, and App's `onClick` never runs. The chat's "Expand chat" button (`chat-dock-expand`) switches to exactly this overlay. In that mode, an agent link has two broken cases:
  1. **Active-session `view_url` while the address bar lacks `?session=`** (the iteration 5 scenario). Nothing calls `preventDefault`, so the browser does a cross-document navigation. That means a full reload, the "Leave site?" prompt (because `isDirty` is true after `createAndJoin`), and loss of undo history and the chat modal. This is exactly what 60d393b set out to prevent.
  2. **Re-clicking a link to the current URL** (same search and hash). No `hashchange` fires, and the delegated re-apply never runs, so the click does nothing. This is the iteration 1 LOW, still present in this mode.

  A link to the same search with a *different* hash still works in the overlay, because `hashchange` is a window event and the propagation stop doesn't affect it.
- **Evidence / Reproduction:** A throwaway `ui/src/App.repro6.test.tsx` reuses `App.test.tsx`'s mocks and `mockHealth`. A copy is at `/tmp/claude-1000/-home-jonlandrigan-emergent-flow/d01e58aa-510b-4b83-935a-28938ee7f73c/scratchpad/iter6/App.repro6.test.tsx`. The key part:
  ```tsx
  async function openChatWithLink(expand: boolean) {
    mockHealth("ok");
    render(<App />);
    await useSessionStore.getState().createAndJoin();
    window.history.replaceState(null, "", "/");               // address bar without ?session=
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    fireEvent.click(screen.getByText("Open chat"));
    useSessionStore.setState({ chat: { backend: "claude", backend_thread_id: null,
      active_persona: null, turns: [{ id: "turn-1", backend: "claude", user_message: "add a node",
        narration: [], status: "completed", error: null,
        agent_message: `Done: [view it](${window.location.origin}/?session=app-test-session#focus=n1)` }] } } as never);
    await waitFor(() => expect(screen.getByText("view it")).toBeInTheDocument());
    if (expand) {
      fireEvent.click(screen.getByTestId("chat-dock-expand"));
      await waitFor(() => expect(screen.getByTestId("chat-expanded")).toBeInTheDocument());
    }
    const a = screen.getByText("view it").closest("a")!;
    const request = vi.spyOn(useViewLinkStore.getState(), "request");
    const click = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
    a.dispatchEvent(click);
    await new Promise((r) => setTimeout(r, 0));
    return { click, request };
  }
  // test 1: openChatWithLink(false) -> expect defaultPrevented true, request x1
  // test 2: openChatWithLink(true)  -> same expectations
  // test 3: expanded, URL already /?session=app-test-session#focus=n1, click same link -> expect request x1
  ```
  `npx vitest run src/App.repro6.test.tsx` gave:
  - Docked (control): `expand=false defaultPrevented=true requestCalls=1 url=/?session=app-test-session#focus=n1`. Passes.
  - Expanded: `expand=true defaultPrevented=false requestCalls=0 url=/`. jsdom logged `Error: Not implemented: navigation (except hash changes)`, which is its cross-document navigation path, meaning a full reload in a browser. Fails: "expected false to be true".
  - Expanded, same-hash re-click: `same-hash expanded requestCalls=0`. Fails.
- **Impact:** A user who expands the chat, which is the larger reading view for the agent's turns, gets iteration 5's behaviour back on every agent link. That means a full page reload with a leave-site prompt, and losing the open chat, undo history, and any local canvas edits that aren't in the server session. Re-clicking the current link silently does nothing.
- **Remediation:** Make `OverlayModal` close on backdrop clicks without stopping propagation. Drop the panel's `stopPropagation` and use `onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}` on the backdrop. Alternatively, register App's listener in the capture phase (`document.addEventListener("click", onClick, true)`), though that loses the `defaultPrevented` check for React handlers. Either way, add an App test that clicks a link rendered inside an `OverlayModal`.

## Notes & unverified leads

- **Back/Forward after the pushState: verified, no bug.**
  - Entries go E1 `/` → (pushState) E2 `/?session=S#focus=n1`.
  - Back to E1 fires `hashchange`, because only the fragment is compared on same-document traversal. The new hash is empty, so `request()` is a no-op and the view stays. That is the same as Back to an empty hash elsewhere, a behaviour iteration 2 already discussed. Forward fires `hashchange` and re-applies `n1`.
  - Later same-search hash links push ordinary fragment entries, and they traverse correctly. The existing App test covers the Back half.
- **Refresh after the pushState:** `?session=S#focus=n1` takes the join-on-load path (`join(S)` then `request(view)`). Correct.
- **Stale `?session=A` with active session B:**
  - This happens after joining B in-app, either through `CodingAgentsSection` "Join" or "Start chat" after an earlier session. `differsOnlyByActiveSession` compares against the active id, so a B link is intercepted and the pushState corrects the address bar. An A link (not active) navigates normally.
  - Refreshing *before* clicking any B link rejoins A. This comes from `join`/`createAndJoin` never writing the URL. It is the same on main for `open_in_ui` flows, so it is not attributed to this PR. `leave()` has no UI caller, so the case "leave, then refresh rejoins the left session" can't happen.
- **Copy link** uses the active session (`withSessionParam`), so it is unaffected by a stale address bar.
- **`OPEN_IN_UI_BASE` vs the browsing origin:**
  - Under `npm run dev` (Vite on `localhost:5173`), agent links point at `http://127.0.0.1:8765`. That is cross-origin, so they are never intercepted and they open the bundled canvas instead (dev-only).
  - Under `serve(host="0.0.0.0")`, links use `127.0.0.1`, which breaks for a browser on another machine. This is pre-existing `open_in_ui` behaviour.
  - Browsing `localhost:8765` while links say `127.0.0.1:8765` would also go cross-origin, but `serve` prints and auto-opens `127.0.0.1`.
  - None of these were reproduced as PR regressions.
- **`open_in_ui` pasted in chat (no hash):** `!anchor.hash` makes the handler return, so the click is a full reload. That is identical to main and the link isn't a view link. Not reported.
- **Python sweep:** `build_view_url`, `_with_view_url`, `view_link` and the `serve()` flag were re-read. I found nothing new; 73 related tests pass.

## Coverage & limitations

- **Reviewed:**
  - 60d393b in full, the `App.tsx` listeners and the initial-load effect;
  - `sessionStore.createAndJoin`/`join`/`leave` and their callers;
  - `CodingAgentsSection`, `OverlayModal`, `ChatModal` (docked and expanded modes), and every `stopPropagation` site in `ui/src`;
  - `viewLink.ts`, `viewLinkStore.ts`, `mcp.py`, `server/app.py` `serve()`.
- **Existing suites pass:**
  - vitest across App, Canvas, viewLink, stores, ProposalPanel, ReviewPanel and NodeContextMenu: 254 tests;
  - `tsc --noEmit` and eslint on `App.tsx` are clean;
  - pytest view-url, MCP and serve-banner: 73 tests.
- **Repro file:** removed from the tree; the copy is in the scratchpad.
- **Limitation:** jsdom doesn't perform cross-document navigation. The reload follows from `defaultPrevented=false` plus jsdom's navigation-path log, and was not run in a real browser.
