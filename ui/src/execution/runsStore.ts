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

  async selectRun(runId) {
    if (runId === null) {
      set({ selectedRunId: null, selectedRunDetail: null });
      return;
    }
    set({ loading: true, error: null });
    try {
      const detail = await getRun(runId);
      set({ selectedRunId: runId, selectedRunDetail: detail, loading: false });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err), loading: false });
    }
  },

  async selectCompareRun(runId) {
    if (runId === null) {
      set({ compareRunId: null, compareRunDetail: null });
      return;
    }
    try {
      const detail = await getRun(runId);
      set({ compareRunId: runId, compareRunDetail: detail });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
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