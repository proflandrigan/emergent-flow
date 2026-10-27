// Scratch "explore this output" drafts (issue #178 task 2). Ephemeral UI state, in memory only:
// like selection, it must NEVER reach the IR or the saved graph (ADR 0014), so it lives here
// and not in graphStore. One draft per (node_id, port); each is bound to the artifact-store
// revision it was opened against, and a run against a replaced/evicted output reports that
// rather than silently rebinding to newer data.

import { create } from "zustand";

import type { Payload } from "./execution";

export const SCRATCH_TEMPLATE = "def transform(value):\n    return value";

export interface ScratchError {
  type: string;
  message: string;
  traceback: string;
  line: number | null;
}

export interface ScratchOutcome {
  status: "ok" | "error" | "expired" | "revision_mismatch";
  /** The code this outcome was produced from, to tell whether it is still current. */
  code: string;
  result?: Payload;
  stdout?: string;
  stderr?: string;
  error?: ScratchError;
  currentRevision?: string | null;
  elapsedMs?: number;
}

export interface ScratchDraft {
  nodeId: string;
  port: string;
  nodeLabel: string;
  revision: string;
  code: string;
  running: boolean;
  outcome: ScratchOutcome | null;
}

export interface ScratchStore {
  drafts: Record<string, ScratchDraft>;
  activeKey: string | null;
  open: (nodeId: string, port: string, nodeLabel: string, revision: string) => void;
  setCode: (key: string, code: string) => void;
  run: (key: string) => Promise<void>;
  discard: (key: string) => void;
}

export function scratchKey(nodeId: string, port: string): string {
  return `${nodeId}:${port}`;
}

interface RunResponse {
  status: ScratchOutcome["status"];
  result?: Payload;
  stdout?: string;
  stderr?: string;
  /** A `ScratchError` on status "error"; a plain message string on a non-200 (e.g. a 403). */
  error?: ScratchError | string;
  current_revision?: string | null;
  elapsed_ms?: number;
}

function failure(code: string, message: string): ScratchOutcome {
  return {
    status: "error",
    code,
    error: { type: "RequestError", message, traceback: "", line: null },
  };
}

export const useScratchStore = create<ScratchStore>((set, get) => ({
  drafts: {},
  activeKey: null,

  open(nodeId, port, nodeLabel, revision) {
    const key = scratchKey(nodeId, port);
    set((state) => ({
      activeKey: key,
      // An existing draft keeps its original revision: re-opening never rebinds it.
      drafts: state.drafts[key]
        ? state.drafts
        : {
            ...state.drafts,
            [key]: {
              nodeId,
              port,
              nodeLabel,
              revision,
              code: SCRATCH_TEMPLATE,
              running: false,
              outcome: null,
            },
          },
    }));
  },

  setCode(key, code) {
    set((state) => {
      const draft = state.drafts[key];
      return draft ? { drafts: { ...state.drafts, [key]: { ...draft, code } } } : state;
    });
  },

  async run(key) {
    const draft = get().drafts[key];
    if (!draft || draft.running) return;
    const { code } = draft;
    const patch = (p: Partial<ScratchDraft>): void =>
      set((state) =>
        state.drafts[key] ? { drafts: { ...state.drafts, [key]: { ...state.drafts[key], ...p } } } : state,
      );
    patch({ running: true });
    let outcome: ScratchOutcome;
    try {
      const res = await fetch("/scratch/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_id: draft.nodeId,
          port: draft.port,
          revision: draft.revision,
          code,
        }),
      });
      const body = (await res.json()) as RunResponse;
      if (!res.ok || typeof body.error === "string") {
        outcome = failure(code, typeof body.error === "string" ? body.error : `Server error ${res.status}`);
      } else {
        outcome = {
          status: body.status,
          code,
          result: body.result,
          stdout: body.stdout,
          stderr: body.stderr,
          error: body.error as ScratchError | undefined,
          currentRevision: body.current_revision,
          elapsedMs: body.elapsed_ms,
        };
      }
    } catch (err) {
      outcome = failure(code, err instanceof Error ? err.message : String(err));
    }
    patch({ running: false, outcome });
  },

  discard(key) {
    set((state) => {
      const drafts = { ...state.drafts };
      delete drafts[key];
      return { drafts, activeKey: state.activeKey === key ? null : state.activeKey };
    });
  },
}));
