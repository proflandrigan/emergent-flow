// Execution results (per-node SSE updates from `/execute/stream`) is the single source of truth
// for in-node result panels and node status colouring. Status tracks whether execution is in-flight;
// results and statuses are never cleared on error (a failed run must not wipe the last successful
// results). Updated incrementally, one node at a time, as SSE events arrive (Epic 7 Story 4) rather
// than in one whole-batch write. A cache hit updates results the same way a fresh execution does,
// just with a different status.

import { create } from "zustand";

import type { NodeRunStatus, Payload, RunMeta } from "./execution";

export interface ProgressState {
  current: number;
  total: number;
  label: string;
}

export interface ExecutionStore {
  running: boolean;
  results: Record<string, Record<string, Payload>>;
  statuses: Record<string, NodeRunStatus>;
  /** Artifact-store revision of each node's last stored output, to detect replacement later. */
  nodeRevisions: Record<string, string>;
  error: string | null;
  lastRunAt: number | null;
  /** Identity of the most recent completed run (id + UTC finish time), for result evidence. */
  runMeta: RunMeta | null;
  /**
   * Per-node run identity: the run that last produced each node's current `results` entry.
   * `results` accumulate across runs (a scoped run only touches some nodes), so evidence must use
   * the source node's own meta, never the global `runMeta`.
   */
  nodeRunMeta: Record<string, RunMeta>;
  /** Nodes that produced a result (ok or cached) in the in-flight run, stamped at completion. */
  pendingRunNodes: string[];
  progress: ProgressState | null;
  setRunning: () => void;
  setNodeStart: (label: string, current: number, total: number) => void;
  setNodeResult: (
    nodeId: string,
    results: Record<string, Payload>,
    revision?: string,
  ) => void;
  setNodeCached: (
    nodeId: string,
    results: Record<string, Payload>,
    revision?: string,
  ) => void;
  setNodeError: (nodeId: string, error: string) => void;
  setNodeSkipped: (nodeId: string, reason?: string) => void;
  setRunComplete: (meta?: { runId?: string | null; finishedAt?: string }) => void;
  setError: (message: string) => void;
  clear: () => void;
}

function withRevision(
  revisions: Record<string, string>,
  nodeId: string,
  revision: string | undefined,
): Record<string, string> {
  if (revision !== undefined) {
    return { ...revisions, [nodeId]: revision };
  }
  // A result without a revision (nothing stored) must not leave the PREVIOUS revision next to the
  // new results: drop it so the UI falls back to the labelled preview instead of browsing old data.
  if (!(nodeId in revisions)) {
    return revisions;
  }
  const next = { ...revisions };
  delete next[nodeId];
  return next;
}

function withPending(pending: string[], nodeId: string): string[] {
  return pending.includes(nodeId) ? pending : [...pending, nodeId];
}

function stampPending(
  nodeRunMeta: Record<string, RunMeta>,
  pending: string[],
  meta: RunMeta,
): Record<string, RunMeta> {
  if (pending.length === 0) {
    return nodeRunMeta;
  }
  const next = { ...nodeRunMeta };
  for (const nodeId of pending) {
    next[nodeId] = meta;
  }
  return next;
}

export const useExecutionStore = create<ExecutionStore>((set) => ({
  running: false,
  results: {},
  statuses: {},
  nodeRevisions: {},
  error: null,
  lastRunAt: null,
  runMeta: null,
  nodeRunMeta: {},
  pendingRunNodes: [],
  progress: null,

  setRunning() {
    set({ running: true, error: null, progress: null, pendingRunNodes: [] });
  },

  setNodeStart(label, current, total) {
    set({ progress: { current, total, label } });
  },

  setNodeResult(nodeId, results, revision) {
    set((state) => ({
      results: { ...state.results, [nodeId]: results },
      statuses: { ...state.statuses, [nodeId]: { status: "ok" } },
      nodeRevisions: withRevision(state.nodeRevisions, nodeId, revision),
      pendingRunNodes: withPending(state.pendingRunNodes, nodeId),
    }));
  },

  setNodeCached(nodeId, results, revision) {
    set((state) => ({
      results: { ...state.results, [nodeId]: results },
      statuses: { ...state.statuses, [nodeId]: { status: "cached" } },
      nodeRevisions: withRevision(state.nodeRevisions, nodeId, revision),
      pendingRunNodes: withPending(state.pendingRunNodes, nodeId),
    }));
  },

  setNodeError(nodeId, error) {
    set((state) => ({
      statuses: { ...state.statuses, [nodeId]: { status: "error", error } },
    }));
  },

  setNodeSkipped(nodeId, reason) {
    set((state) => {
      const status: NodeRunStatus = { status: "skipped" };
      if (reason) {
        status.reason = reason;
      }
      return {
        statuses: { ...state.statuses, [nodeId]: status },
      };
    });
  },

  setRunComplete(meta) {
    set((state) => {
      // run_id is null for scoped/partial runs or an unsaved record: keep it null (timestamp-only
      // evidence) rather than inventing an id that `GET /runs/{id}` cannot resolve.
      const runMeta: RunMeta = {
        runId: meta?.runId ?? null,
        finishedAt: meta?.finishedAt ?? new Date().toISOString(),
      };
      return {
        running: false,
        error: null,
        lastRunAt: Date.now(),
        runMeta,
        nodeRunMeta: stampPending(state.nodeRunMeta, state.pendingRunNodes, runMeta),
        pendingRunNodes: [],
        progress: null,
      };
    });
  },

  setError(message) {
    set((state) => ({
      running: false,
      error: message,
      progress: null,
      // Results that did arrive before the run failed have no persisted run record.
      nodeRunMeta: stampPending(state.nodeRunMeta, state.pendingRunNodes, {
        runId: null,
        finishedAt: new Date().toISOString(),
      }),
      pendingRunNodes: [],
    }));
  },

  clear() {
    set({
      running: false,
      results: {},
      statuses: {},
      nodeRevisions: {},
      error: null,
      lastRunAt: null,
      runMeta: null,
      nodeRunMeta: {},
      pendingRunNodes: [],
      progress: null,
    });
  },
}));
