// Ephemeral guided-tour PLAYBACK state (issue #171): which tour is playing, at which step, and the
// pre-tour view snapshot to restore on exit. Separate from the server's tour collection
// (sessionStore.tours) and from graphStore. Never serialized into the IR (ADR 0014); playback
// never writes graph data.

import type { Viewport } from "@xyflow/react";
import { create } from "zustand";

import { formatViewHash, parseViewHash } from "../io/viewLink";
import type { Tour } from "../session/sessionClient";
import { useGraphStore } from "./graphStore";
import type { NodeModel } from "./model";
import { useSelectionStore } from "./selectionStore";
import { useSubgraphStore, type SubgraphBreadcrumb } from "./subgraphStore";
import { useTraceStore, type TraceStore } from "./traceStore";

export interface TourSnapshot {
  selection: { nodes: Record<string, boolean>; edges: Record<string, boolean> };
  trace: Pick<TraceStore, "mode" | "direction" | "routeFrom" | "routeTo" | "families">;
  breadcrumbs: SubgraphBreadcrumb[];
  hash: string;
  /** Filled by Canvas right after start (it owns the React Flow instance); null until then. */
  viewport: Viewport | null;
  focusEl: HTMLElement | null;
}

export interface TourPlayback {
  tour: Tour;
  index: number;
}

export interface TourStore {
  playing: TourPlayback | null;
  snapshot: TourSnapshot | null;
  /** Viewport Canvas should restore after exit (Canvas calls consumeViewportRestore). */
  pendingViewportRestore: Viewport | null;
  /** Last screen-reader announcement ("Step 2 of 3", "Tour updated", ...). */
  announcement: string | null;
  start: (tour: Tour, index?: number) => void;
  captureViewport: (viewport: Viewport) => void;
  goTo: (index: number) => void;
  next: () => void;
  prev: () => void;
  updateTour: (tour: Tour) => void;
  exit: (opts?: { restore?: boolean }) => void;
  consumeViewportRestore: () => void;
}

function clampIndex(index: number, count: number): number {
  if (!Number.isInteger(index) || index < 0) return 0;
  return Math.min(index, Math.max(0, count - 1));
}

function replaceHash(hash: string): void {
  window.history.replaceState(
    window.history.state,
    "",
    window.location.pathname + window.location.search + hash,
  );
}

/**
 * Rebuild a breadcrumb path against the CURRENT graph: walk the snapshot's composite ids, looking
 * each up in the current top-level nodes (level 0) or the previous level's subgraph, and stop at
 * the first one that no longer exists.
 */
export function resolveBreadcrumbs(
  snapshot: SubgraphBreadcrumb[],
  nodes: Record<string, NodeModel>,
): SubgraphBreadcrumb[] {
  const out: SubgraphBreadcrumb[] = [];
  for (const entry of snapshot) {
    const subgraph =
      out.length === 0
        ? nodes[entry.compositeId]?.subgraph
        : out[out.length - 1].subgraph.nodes?.[entry.compositeId]?.subgraph;
    if (!subgraph) break;
    out.push({ compositeId: entry.compositeId, label: entry.label, subgraph });
  }
  return out;
}

export const useTourStore = create<TourStore>((set, get) => {
  function applyStep(tour: Tour, index: number, announcement?: string): void {
    set({
      playing: { tour, index },
      announcement: announcement ?? `Step ${index + 1} of ${tour.steps.length}: ${tour.title}`,
    });
    useTraceStore.getState().setTourStep(tour.steps[index]);
    replaceHash(formatViewHash({ tour: tour.id, step: index }));
  }

  function moveTo(index: number): void {
    const playing = get().playing;
    if (!playing) return;
    const target = clampIndex(index, playing.tour.steps.length);
    applyStep(playing.tour, target);
  }

  return {
    playing: null,
    snapshot: null,
    pendingViewportRestore: null,
    announcement: null,

    start(tour, index = 0) {
      if (tour.steps.length === 0) return;
      if (get().playing === null) {
        const sel = useSelectionStore.getState();
        const trace = useTraceStore.getState();
        const inTour = trace.mode === "tour";
        const active = document.activeElement;
        set({
          snapshot: {
            selection: { nodes: { ...sel.nodes }, edges: { ...sel.edges } },
            trace: inTour
              ? {
                  mode: "selection-downstream",
                  direction: "downstream",
                  routeFrom: null,
                  routeTo: null,
                  families: [],
                }
              : {
                  mode: trace.mode,
                  direction: trace.direction,
                  routeFrom: trace.routeFrom,
                  routeTo: trace.routeTo,
                  families: [...trace.families],
                },
            breadcrumbs: [...useSubgraphStore.getState().breadcrumbs],
            hash: window.location.hash,
            viewport: null,
            focusEl: active instanceof HTMLElement ? active : null,
          },
        });
        // Tours anchor top-level ids, so leave any drilled-in subgraph and drop the selection.
        useSubgraphStore.getState().clear();
        useSelectionStore.getState().clear();
      }
      applyStep(tour, clampIndex(index, tour.steps.length));
    },

    captureViewport(viewport) {
      const snap = get().snapshot;
      if (snap && snap.viewport === null) {
        set({ snapshot: { ...snap, viewport } });
      }
    },

    goTo(index) {
      moveTo(index);
    },

    next() {
      const playing = get().playing;
      if (playing) moveTo(playing.index + 1);
    },

    prev() {
      const playing = get().playing;
      if (playing) moveTo(playing.index - 1);
    },

    updateTour(tour) {
      const playing = get().playing;
      if (!playing || playing.tour.id !== tour.id || tour.steps.length === 0) return;
      const last = tour.steps.length - 1;
      if (playing.index <= last) {
        applyStep(tour, playing.index, "Tour updated");
      } else {
        applyStep(tour, last, `Tour updated — now at step ${last + 1} of ${tour.steps.length}`);
      }
    },

    exit({ restore = true } = {}) {
      const { playing, snapshot } = get();
      if (!playing) return;
      set({ playing: null, snapshot: null });

      if (!restore || !snapshot) {
        if (useTraceStore.getState().mode === "tour") useTraceStore.getState().reset();
        return;
      }

      const graph = useGraphStore.getState();

      const nodeIds = Object.keys(snapshot.selection.nodes).filter(
        (id) => snapshot.selection.nodes[id] && id in graph.nodes,
      );
      const edgeIds = Object.keys(snapshot.selection.edges).filter(
        (id) => snapshot.selection.edges[id] && id in graph.edges,
      );
      useSelectionStore.getState().replaceSelection(nodeIds, edgeIds);

      const trace = useTraceStore.getState();
      const t = snapshot.trace;
      if (t.mode === "reach" && nodeIds.length > 0) {
        trace.setReach(t.direction);
      } else if (
        t.mode === "route" &&
        t.routeFrom !== null &&
        t.routeTo !== null &&
        t.routeFrom in graph.nodes &&
        t.routeTo in graph.nodes
      ) {
        trace.setRoute(t.routeFrom, t.routeTo);
      } else if (t.mode === "lens") {
        trace.setLens(t.families);
      } else {
        trace.reset();
      }

      // Only touch the subgraph store when the path actually changes: Canvas resets the trace on
      // every breadcrumbs change, which would discard the trace restored above. (Returning into a
      // composite therefore restores selection/viewport but not a trace drawn inside it.)
      const crumbs = resolveBreadcrumbs(snapshot.breadcrumbs, graph.nodes);
      const subgraph = useSubgraphStore.getState();
      if (crumbs.length > 0 || subgraph.breadcrumbs.length > 0) {
        subgraph.clear();
        for (const crumb of crumbs) useSubgraphStore.getState().pushSubgraph(crumb);
      }

      // A tour opened by a link must not leave its hash behind, or the view would re-trigger it.
      replaceHash(parseViewHash(snapshot.hash).tour !== null ? "" : snapshot.hash);

      set({ pendingViewportRestore: snapshot.viewport, announcement: "Tour closed" });

      if (snapshot.focusEl?.isConnected) snapshot.focusEl.focus();
    },

    consumeViewportRestore() {
      set({ pendingViewportRestore: null });
    },
  };
});
