// Ephemeral UI state for navigating into composite node subgraphs.
// Tracks a breadcrumb stack of (compositeId, label, subgraph) entries so
// users can drill into nested composites and navigate back via breadcrumbs.
// Kept OUT of the store/IR, mirroring collapseStore and selectionStore
// (ADR 0014 Decision 3).

import { create } from "zustand";
import type { Graph } from "../generated/ir";

export interface SubgraphBreadcrumb {
  compositeId: string;
  label: string;
  subgraph: Graph;
}

export interface SubgraphStore {
  breadcrumbs: SubgraphBreadcrumb[];
  pushSubgraph: (entry: SubgraphBreadcrumb) => void;
  popTo: (depth: number) => void;
  clear: () => void;
}

export const useSubgraphStore = create<SubgraphStore>((set) => ({
  breadcrumbs: [],

  pushSubgraph(entry) {
    set((state) => ({ breadcrumbs: [...state.breadcrumbs, entry] }));
  },

  popTo(depth) {
    set((state) => ({ breadcrumbs: state.breadcrumbs.slice(0, depth) }));
  },

  clear() {
    set({ breadcrumbs: [] });
  },
}));

// Returns the current subgraph being viewed, or null when at the top level.
export function currentSubgraph(state: Pick<SubgraphStore, "breadcrumbs">): Graph | null {
  if (state.breadcrumbs.length === 0) {
    return null;
  }
  return state.breadcrumbs[state.breadcrumbs.length - 1].subgraph;
}

// Build the breadcrumb path labels for display, e.g. ["Top-level", "Composite 1", ...].
export function breadcrumbLabels(state: Pick<SubgraphStore, "breadcrumbs">): string[] {
  if (state.breadcrumbs.length === 0) {
    return ["Top-level"];
  }
  return ["Top-level", ...state.breadcrumbs.map((b) => b.label)];
}
