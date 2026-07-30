// Persistence metadata for named flows (saved graphs) and bundled examples, backed by the
// server's /flows and /examples REST routes. Kept as a separate Zustand store from graphStore
// (which owns the canvas model) -- this store owns *where a graph lives on disk*, not its
// contents.

import { create } from "zustand";

import { useGraphStore } from "../store/graphStore";

export interface FlowEntry {
  slug: string;
  name: string;
  updated_at: string;
}

export interface ExampleEntry {
  name: string;
  path: string;
  slug: string;
}

export interface FlowStore {
  // State
  currentSlug: string | null;
  isDirty: boolean;
  flows: FlowEntry[];
  examples: ExampleEntry[];
  loading: boolean;
  error: string | null;

  // Actions
  fetchFlows: () => Promise<void>;
  fetchExamples: () => Promise<void>;
  saveFlow: (slug: string, graph: Record<string, unknown> | object) => Promise<void>;
  saveNewFlow: (name: string, graph: Record<string, unknown> | object) => Promise<string>;
  loadFlow: (slug: string) => Promise<Record<string, unknown> | object>;
  deleteFlow: (slug: string) => Promise<void>;
  renameFlow: (oldSlug: string, newSlug: string) => Promise<void>;
  loadExample: (path: string) => Promise<Record<string, unknown> | object>;
  setCurrentSlug: (slug: string | null) => void;
  setDirty: (dirty: boolean) => void;
  clearError: () => void;
}

export const useFlowStore = create<FlowStore>((set, get) => ({
  currentSlug: null,
  isDirty: false,
  flows: [],
  examples: [],
  loading: false,
  error: null,

  async fetchFlows() {
    set({ loading: true, error: null });
    try {
      const res = await fetch("/flows");
      if (!res.ok) throw new Error(`Failed to list flows: ${res.status}`);
      const data = await res.json();
      set({ flows: data.flows, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  async fetchExamples() {
    try {
      const res = await fetch("/examples");
      if (!res.ok) return;
      const data = await res.json();
      set({ examples: data.examples });
    } catch {
      // Examples are non-critical; fail silently
    }
  },

  async saveFlow(slug, graph) {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`/flows/${encodeURIComponent(slug)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ graph }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Save failed: ${res.status}`);
      }
      set({ isDirty: false, loading: false });
      // Refresh the list to get updated_at
      get().fetchFlows();
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  async saveNewFlow(name, graph) {
    set({ loading: true, error: null });
    try {
      const res = await fetch("/flows", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ graph }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Save failed: ${res.status}`);
      }
      const data = await res.json();
      const slug = data.slug;
      set({ currentSlug: slug, isDirty: false, loading: false });
      get().fetchFlows();
      return slug;
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
      throw e;
    }
  },

  async loadFlow(slug) {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`/flows/${encodeURIComponent(slug)}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Load failed: ${res.status}`);
      }
      const graph = await res.json();
      set({ currentSlug: slug, isDirty: false, loading: false });
      return graph;
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
      throw e;
    }
  },

  async deleteFlow(slug) {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`/flows/${encodeURIComponent(slug)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Delete failed: ${res.status}`);
      }
      if (get().currentSlug === slug) {
        set({ currentSlug: null });
      }
      set({ loading: false });
      get().fetchFlows();
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  async renameFlow(oldSlug, newSlug) {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`/flows/${encodeURIComponent(oldSlug)}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_slug: newSlug }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Rename failed: ${res.status}`);
      }
      const data = await res.json();
      if (get().currentSlug === oldSlug) {
        set({ currentSlug: data.slug });
      }
      set({ loading: false });
      get().fetchFlows();
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  async loadExample(path) {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`/examples/${path}`);
      if (!res.ok) throw new Error(`Failed to load example: ${res.status}`);
      const graph = await res.json();
      // Examples open as unsaved copies -- no currentSlug, marked dirty
      set({ currentSlug: null, isDirty: true, loading: false });
      return graph;
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
      throw e;
    }
  },

  setCurrentSlug(slug) {
    set({ currentSlug: slug });
  },
  setDirty(dirty) {
    set({ isDirty: dirty });
  },
  clearError() {
    set({ error: null });
  },
}));

let dirtyUnsub: (() => void) | null = null;

export function startDirtyTracking(): void {
  if (dirtyUnsub) return;
  dirtyUnsub = useGraphStore.subscribe((state, prev) => {
    if (
      state.nodes !== prev.nodes ||
      state.edges !== prev.edges ||
      state.paradigm !== prev.paradigm ||
      state.name !== prev.name
    ) {
      useFlowStore.getState().setDirty(true);
    }
  });
}

export function stopDirtyTracking(): void {
  dirtyUnsub?.();
  dirtyUnsub = null;
}
