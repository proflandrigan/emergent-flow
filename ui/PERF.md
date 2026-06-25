# Canvas performance budget (Epic 5, Story 9)

## Budget

The canvas targets interactive performance at scale:

- **Target graph size:** 1,000 nodes (the synthetic stress test graph)
- **Interaction target:** Pan/zoom stays ≥ ~30 FPS (smooth) at 1,000 nodes on a typical dev laptop; node drag of a single node does not stutter
- **Initial render:** < ~1.5 s to first interactive frame for the 1,000-node graph

These are the **budget to verify**, not hard guarantees — Epic 5 explicitly defers real performance verification to manual browser measurement.

## Strategy

Three structural levers keep the canvas responsive at scale:

1. **Virtualization** — `onlyRenderVisibleElements` in `src/canvas/Canvas.tsx` (line 139) ensures only nodes and edges in the current viewport are rendered; off-screen nodes are culled from the DOM.

2. **Level-of-detail (LOD)** — `src/canvas/nodes/lod.ts` defines `LOD_ZOOM_THRESHOLD = 0.4`; below this zoom level, `CmNode` hides port-name text (via `visibility: hidden`, preserving handle anchors) and suppresses the in-node results panel to reduce render overhead when zoomed out.

3. **Lazy heavy views** — In-node `/execute` result panels default to collapsed state in `CmNode`, deferring expensive rendering until the user explicitly opens them. This pairs with roadmap Epic 8's richer result renderers.

All three are implemented up front because they are cheap, structural, and require no user intervention; further perf work (e.g., canvas-level culling, web-worker layout) is deferred until a real graph misses the budget (pragmatism over edge cases).

## How to reproduce a measurement

1. Run `cd ui && npm run dev`; optionally start `colonymind serve` (not required for pan/zoom perf testing, but needed if testing the `/compile` workflow).

2. Click the dev **"Load 1000 nodes"** button (visible only in dev builds; search for `data-testid="dev-load-large"` in `src/dev/DevControls.tsx`).

3. Open the browser DevTools Performance panel, hit record, and capture 10–15 seconds of panning and zooming around the graph. Stop recording and read the reported FPS in the timeline.

4. For comparative testing, temporarily toggle `onlyRenderVisibleElements` off in `Canvas.tsx` (line 139) and re-test to see the impact of virtualization alone.

5. Zoom past 0.4 and back below it to confirm LOD kicks in (port text and results panel disappear/reappear).

## Measured results

| Scenario | Nodes | FPS / time | Notes |
|----------|-------|-----------|-------|
| Initial render (cold load) | 1,000 | TBD (manual browser run) | Time to first interactive frame |
| Pan at 1000 nodes | 1,000 | TBD (manual browser run) | Smooth scrolling horizontally/vertically |
| Zoom at 1000 nodes | 1,000 | TBD (manual browser run) | In and out, crossing LOD threshold at 0.4 |

**Note:** FPS numbers are filled in from a manual browser profiling run; the jsdom test environment cannot measure real frame timing or rendering performance.

## Decision

Virtualization, LOD, and default-collapsed heavy views form a three-layer defense against canvas bloat. They are structural optimizations that cost little to implement and deliver immediate wins on responsiveness. If a real graph later misses the budget (measured in production use), the next phase can add canvas-level culling, web-worker layout, or edge rendering optimizations — but premature optimization of those edge cases is deferred.
