# Bug Hunt Report: PR #166 (result card node)

## Summary
- Scope reviewed: Python node + MCP tools (`result_card.py`, `collab/mcp.py`), UI store action, `ResultCardNode.tsx`, `resultCardBlocks.ts`, `reportHtml.tsx`, toolbar/canvas wiring. Ran ruff, mypy, targeted pytest, eslint, tsc, vitest (all green).
- Confirmed findings: 1 Medium
- Overall: the PR is in good shape; linters and tests pass. One undo-history defect in the Summarize action was proven.

## Findings

### MEDIUM — Summarize creates 4+ undo steps; one undo leaves a half-built card
- **Location:** `ui/src/store/graphStore.ts` (`createResultCardForSelection`)
- **Class:** State consistency / history granularity
- **Confidence:** Confirmed
- **Description:** The action composes `addNodeFromSpec`, `setParam`, `connect` (per port) and `setParam`; each pushes its own history snapshot.
- **Evidence / Reproduction:** Temporary vitest: one node `a` with one out port; call `createResultCardForSelection(["a"])`. `past` grew by 4; after a single `undo()` the card still existed with 1 edge.
- **Impact:** Ctrl+Z after "Summarize" leaves a card with no blocks (blocks_json reverted) but still wired; user needs several undos.
- **Remediation:** Capture `past` and a snapshot before the work, then reset `past` to `[...pastBefore, snapshot]` at the end so the action is one undo step. Test added in `graphStore.resultCard.test.ts`.

## Notes & unverified leads
- Removing a result block in the card editor leaves its upstream edge in place (likely by design).
- Summarize shows for selections containing only notes/layout nodes and silently does nothing (cosmetic).

## Coverage & limitations
Did not exercise the MCP tools against a live session or the exported HTML in a browser.
