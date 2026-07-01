// Execution results (per-node SSE updates from `/execute/stream`) is the single source of truth
// for in-node result panels and node status colouring. Status tracks whether execution is in-flight;
// results and statuses are never cleared on error (a failed run must not wipe the last successful
// results). Updated incrementally, one node at a time, as SSE events arrive (Epic 7 Story 4) rather
// than in one whole-batch write. A cache hit updates results the same way a fresh execution does,
// just with a different status.

import { create } from "zustand";

import type { NodeRunStatus, Payload } from "./execution";

export interface ProgressState {
  current: number;
  total: number;
  label: string;
}

export interface ExecutionStore {
  running: boolean;
  results: Record<string, Record<string, Payload>>;
  statuses: Record<string, NodeRunStatus>;
  error: string | null;
  lastRunAt: number | null;
  progress: ProgressState | null;
  setRunning: () => void;
  setNodeStart: (label: string, current: number, total: number) => void;
  setNodeResult: (nodeId: string, results: Record<string, Payload>) => void;
  setNodeCached: (nodeId: string, results: Record<string, Payload>) => void;
  setNodeError: (nodeId: string, error: string) => void;
  setNodeSkipped: (nodeId: string) => void;
  setRunComplete: () => void;
  setError: (message: string) => void;
  clear: () => void;
}

export const useExecutionStore = create<ExecutionStore>((set) => ({
  running: false,
  results: {},
  statuses: {},
  error: null,
  lastRunAt: null,
  progress: null,

  setRunning() {
    set({ running: true, error: null, progress: null });
  },

  setNodeStart(label, current, total) {
    set({ progress: { current, total, label } });
  },

  setNodeResult(nodeId, results) {
    set((state) => ({
      results: { ...state.results, [nodeId]: results },
      statuses: { ...state.statuses, [nodeId]: { status: "ok" } },
    }));
  },

  setNodeCached(nodeId, results) {
    set((state) => ({
      results: { ...state.results, [nodeId]: results },
      statuses: { ...state.statuses, [nodeId]: { status: "cached" } },
    }));
  },

  setNodeError(nodeId, error) {
    set((state) => ({
      statuses: { ...state.statuses, [nodeId]: { status: "error", error } },
    }));
  },

  setNodeSkipped(nodeId) {
    set((state) => ({
      statuses: { ...state.statuses, [nodeId]: { status: "skipped" } },
    }));
  },

  setRunComplete() {
    set({ running: false, error: null, lastRunAt: Date.now(), progress: null });
  },

  setError(message) {
    set({ running: false, error: message, progress: null });
  },

  clear() {
    set({
      running: false,
      results: {},
      statuses: {},
      error: null,
      lastRunAt: null,
      progress: null,
    });
  },
}));
