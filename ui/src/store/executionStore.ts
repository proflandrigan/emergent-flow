// Execution results (last `/execute` payload and node statuses) is the single source of truth
// for in-node result panels and node status colouring. Status tracks whether execution is in-flight;
// results and statuses are never cleared on error (a failed run must not wipe the last successful results).

import { create } from "zustand";

import { EXPECTED_PAYLOAD_VERSION } from "./execution";
import type { ExecuteResponse, NodeRunStatus, Payload } from "./execution";

export interface ExecutionStore {
  running: boolean;
  results: Record<string, Record<string, Payload>>;
  statuses: Record<string, NodeRunStatus>;
  error: string | null;
  lastRunAt: number | null;
  setRunning: () => void;
  setResult: (res: ExecuteResponse) => void;
  setError: (message: string) => void;
  clear: () => void;
}

export const useExecutionStore = create<ExecutionStore>((set) => ({
  running: false,
  results: {},
  statuses: {},
  error: null,
  lastRunAt: null,

  setRunning() {
    set({ running: true, error: null });
  },

  setResult(res) {
    if (res.payload_version !== EXPECTED_PAYLOAD_VERSION) {
      set({
        running: false,
        error: `Server payload version ${res.payload_version} is incompatible (expected ${EXPECTED_PAYLOAD_VERSION}). Restart the server or refresh the page.`,
      });
      return;
    }
    set({
      results: res.results,
      statuses: res.statuses,
      running: false,
      error: null,
      lastRunAt: Date.now(),
    });
  },

  setError(message) {
    set({ running: false, error: message });
  },

  clear() {
    set({
      running: false,
      results: {},
      statuses: {},
      error: null,
      lastRunAt: null,
    });
  },
}));
