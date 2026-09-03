// Selection (which nodes/edges are highlighted) is ephemeral UI state -- it must NEVER be
// serialized into the IR (ADR 0014: the graph store owns IR data only). This store is the single
// source of truth for selection so both Canvas and Inspector can share it.

import { create } from "zustand";

export interface SelectionStore {
  nodes: Record<string, boolean>;
  edges: Record<string, boolean>;
  setNodeSelected: (id: string, selected: boolean) => void;
  setEdgeSelected: (id: string, selected: boolean) => void;
  clear: () => void;
  replaceSelection: (nodeIds: string[]) => void;
}

export const useSelectionStore = create<SelectionStore>((set) => ({
  nodes: {},
  edges: {},

  setNodeSelected(id, selected) {
    set((state) => ({ nodes: { ...state.nodes, [id]: selected } }));
  },

  setEdgeSelected(id, selected) {
    set((state) => ({ edges: { ...state.edges, [id]: selected } }));
  },

  clear() {
    set({ nodes: {}, edges: {} });
  },

  replaceSelection(nodeIds) {
    set(() => {
      const nodes: Record<string, boolean> = {};
      for (const id of nodeIds) {
        nodes[id] = true;
      }
      return { nodes, edges: {} };
    });
  },
}));

// Returns the single selected node id, or null when zero OR more than one node is selected.
export function selectedNodeId(
  state: Pick<SelectionStore, "nodes">,
): string | null {
  const ids = Object.keys(state.nodes).filter((id) => state.nodes[id]);
  return ids.length === 1 ? ids[0] : null;
}
