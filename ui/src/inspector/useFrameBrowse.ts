// Client hook for the local server's `/browse/frame` route (issue #178): fetches one window of
// a node's FULL stored DataFrame. Query edits are debounced, and a request counter drops any
// response that is no longer the latest, so a slow early request can never overwrite a newer
// one. Read-only -- it never touches the graph or execution stores.

import { useEffect, useRef, useState } from "react";

export interface BrowseFilter {
  column: string;
  operator: string;
  value: unknown;
}

export interface BrowseSort {
  column: string;
  ascending: boolean;
}

export interface BrowseQuery {
  nodeId: string;
  port: string;
  revision: string;
  filters: BrowseFilter[];
  sort: BrowseSort[];
  offset: number;
  limit: number;
}

export interface BrowseWindow {
  revision: string;
  columns: string[];
  dtypes: string[];
  total_rows: number;
  filtered_rows: number;
  offset: number;
  limit: number;
  rows: Record<string, unknown>[];
}

export type BrowseState =
  | { phase: "loading"; prev: BrowseWindow | null }
  | { phase: "ok"; data: BrowseWindow }
  | { phase: "expired" }
  | { phase: "revision_mismatch"; currentRevision: string | null }
  | { phase: "not_tabular" }
  | { phase: "error"; message: string };

export function useFrameBrowse(query: BrowseQuery, debounceMs = 300): BrowseState {
  const [state, setState] = useState<BrowseState>({ phase: "loading", prev: null });
  const counter = useRef(0);
  const last = useRef<BrowseWindow | null>(null);
  // Stable dependency: the query is rebuilt every render by the caller.
  const key = JSON.stringify(query);

  useEffect(() => {
    const id = ++counter.current;
    setState({ phase: "loading", prev: last.current });
    const handle = setTimeout(() => {
      void (async () => {
        let next: BrowseState;
        try {
          const res = await fetch("/browse/frame", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              node_id: query.nodeId,
              port: query.port,
              revision: query.revision,
              filters: query.filters,
              sort: query.sort,
              offset: query.offset,
              limit: query.limit,
            }),
          });
          const body = await res.json();
          if (!res.ok || body.error) {
            next = { phase: "error", message: body.error ?? `Server error ${res.status}` };
          } else if (body.status === "ok") {
            last.current = body as BrowseWindow;
            next = { phase: "ok", data: body as BrowseWindow };
          } else if (body.status === "expired") {
            next = { phase: "expired" };
          } else if (body.status === "revision_mismatch") {
            next = { phase: "revision_mismatch", currentRevision: body.current_revision ?? null };
          } else if (body.status === "not_tabular") {
            next = { phase: "not_tabular" };
          } else {
            next = { phase: "error", message: "Malformed browse response from server." };
          }
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          next = { phase: "error", message: "Could not reach server: " + msg };
        }
        if (id === counter.current) {
          setState(next);
        }
      })();
    }, debounceMs);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, debounceMs]);

  return state;
}
