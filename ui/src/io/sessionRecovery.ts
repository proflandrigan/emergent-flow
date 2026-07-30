// Cheapest-possible persistence layer for the canvas: localStorage-based session recovery.
// Works independently of the flow store -- even if the server is down, the user's last graph
// survives a browser refresh. Serialization goes through graphStore.toIR()/loadIR(), the same
// pure mappers the rest of the app uses to cross the wire-IR boundary.

import { useEffect } from "react";

import type { Graph } from "../generated/ir";
import { useGraphStore } from "../store/graphStore";
import { supportedSchemaVersion } from "../store/validateIR";

const STORAGE_KEY = "ef-session-recovery";
const DEBOUNCE_MS = 2000;

// Serialize the current graph to localStorage.
export function saveSession(): void {
  try {
    const graph = useGraphStore.getState().toIR();
    const payload = JSON.stringify({
      schema_version: supportedSchemaVersion,
      graph,
      saved_at: Date.now(),
    });
    localStorage.setItem(STORAGE_KEY, payload);
  } catch {
    // localStorage full or unavailable -- silently ignore
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

export interface RecoveredSession {
  graph: Graph;
  savedAt: number;
}

export function recoverSession(): RecoveredSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    // Gate on schema version -- discard stale blobs
    if (data.schema_version !== supportedSchemaVersion) {
      clearSession();
      return null;
    }
    if (!data.graph || typeof data.graph !== "object") {
      clearSession();
      return null;
    }
    // Don't restore an empty graph (no nodes)
    const nodes = data.graph.nodes;
    if (!nodes || Object.keys(nodes).length === 0) {
      clearSession();
      return null;
    }
    return { graph: data.graph as Graph, savedAt: data.saved_at ?? 0 };
  } catch {
    clearSession();
    return null;
  }
}

// React hook: subscribes to graphStore changes and debounce-saves to localStorage. Call it once
// from App. Not wired here (Task 7) -- this module only owns the persistence primitives.
export function useSessionAutoSave(): void {
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const unsub = useGraphStore.subscribe(() => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        saveSession();
      }, DEBOUNCE_MS);
    });
    return () => {
      unsub();
      if (timer) clearTimeout(timer);
    };
  }, []);
}
