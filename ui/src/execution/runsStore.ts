import { create } from "zustand";
import { listRuns, getRun, deleteRun, type RunEntry, type RunDetail } from "./runsClient";

export interface RunsStore {
  runs: RunEntry[];
  selectedRunId: string | null;
  selectedRunDetail: RunDetail | null;
  compareRunId: string | null;
  compareRunDetail: RunDetail | null;
  loading: boolean;
  error: string | null;

  fetchRuns: () => Promise<void>;
  selectRun: (runId: string | null) => Promise<void>;
  selectCompareRun: (runId: string | null) => Promise<void>;
  clearSelection: () => void;
  deleteRun: (runId: string) => Promise<void>;
  clearError: () => void;
}

let requestSeq = 0;

export const useRunsStore = create<RunsStore>((set, get) => ({
  runs: [],
  selectedRunId: null,
  selectedRunDetail: null,
  compareRunId: null,
  compareRunDetail: null,
  loading: false,
  error: null,

  async fetchRuns() {
    set({ loading: true, error: null });
    try {
      const runs = await listRuns();
      set({ runs, loading: false });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err), loading: false });
    }
  },

  selectRun: async (runId) => {
    if (runId === null) {
      set({ selectedRunId: null, selectedRunDetail: null, loading: false });
      return;
    }
    const requestId = ++requestSeq;
    set({ loading: true, error: null });
    try {
      const detail = await getRun(runId);
      if (requestId === requestSeq) {
        set({ selectedRunId: runId, selectedRunDetail: detail, loading: false });
      }
    } catch (err) {
      if (requestId === requestSeq) {
        set({ error: err instanceof Error ? err.message : String(err), loading: false });
      }
    }
  },

  selectCompareRun: async (runId) => {
    if (runId === null) {
      set({ compareRunId: null, compareRunDetail: null });
      return;
    }
    const requestId = ++requestSeq;
    set({ loading: true, error: null });
    try {
      const detail = await getRun(runId);
      if (requestId === requestSeq) {
        set({ compareRunId: runId, compareRunDetail: detail, loading: false });
      }
    } catch (err) {
      if (requestId === requestSeq) {
        set({ error: err instanceof Error ? err.message : String(err), loading: false });
      }
    }
  },

  clearSelection() {
    set({ selectedRunId: null, selectedRunDetail: null, compareRunId: null, compareRunDetail: null });
  },

  async deleteRun(runId) {
    try {
      await deleteRun(runId);
      const state = get();
      if (state.selectedRunId === runId) {
        state.clearSelection();
      }
      await state.fetchRuns();
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
    }
  },

  clearError() {
    set({ error: null });
  },
}));