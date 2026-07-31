// Ephemeral UI state tracking which group nodes are currently collapsed (rendered as a single
// summary node instead of their full contents). Kept OUT of the store/IR, mirroring how
// `selectionStore.ts` keeps node/edge selection out of the graph model (ADR 0014 Decision 3).

import { create } from "zustand";

export interface CollapseStore {
  collapsed: Record<string, boolean>;
  toggleCollapsed: (groupId: string) => void;
  setCollapsed: (groupId: string, collapsed: boolean) => void;
  clear: () => void;
}

export const useCollapseStore = create<CollapseStore>((set) => ({
  collapsed: {},

  toggleCollapsed(groupId) {
    set((state) => ({
      collapsed: { ...state.collapsed, [groupId]: !state.collapsed[groupId] },
    }));
  },

  setCollapsed(groupId, collapsed) {
    set((state) => ({ collapsed: { ...state.collapsed, [groupId]: collapsed } }));
  },

  clear() {
    set({ collapsed: {} });
  },
}));

// Returns whether the given group id is currently collapsed. A group never seen before
// defaults to expanded (not collapsed).
export function isGroupCollapsed(
  state: Pick<CollapseStore, "collapsed">,
  groupId: string,
): boolean {
  return !!state.collapsed[groupId];
}
