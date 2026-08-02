// The shared streaming-execute call: POSTs the current graph (optionally pruned to a
// subgraph via `run_to` / `run_from` / `run_only`) to `/execute/stream` and applies each
// SSE event to `executionStore` incrementally as it arrives. Used by the ExecutionToolbar's
// "Execute" button (whole graph), the canvas node context menu's "Run to here" / "Run this
// node" / "Run from here" actions, and the selection toolbar, so every trigger shares one
// implementation. See issue #105 for the partial-run semantics.

import { EXPECTED_PAYLOAD_VERSION } from "../store/execution";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { readSSEEvents } from "./sse";

export interface RunGraphOptions {
  /** If set, only the ancestor-closed subgraph of this node (or these nodes) runs
   *  ("run to here" for a single id, "run to selected" for an array). */
  runTo?: string | string[];
  /** If set, the target(s) and every node downstream run, reusing prior run's
   *  stored outputs for the targets' own IN ports ("run from here"). */
  runFrom?: string | string[];
  /** If set, exactly the listed nodes run, reusing prior run's stored outputs
   *  where available ("run this node" / "run selected only"). */
  runOnly?: string | string[];
  /** Graph-level parameter overrides sent as `params` (issue #116). */
  params?: Record<string, unknown>;
  /** Called with a human-readable message whenever the run fails (in addition to
   *  `executionStore.error` always being set). Callers that render their own error
   *  banner (e.g. `ExecutionToolbar`) pass this; callers that don't need a local
   *  banner (e.g. the context menu) can omit it. */
  onError?: (message: string) => void;
}

export async function runGraph(options: RunGraphOptions = {}): Promise<void> {
  // The toolbar's Execute button disables itself while `running`, but the canvas context
  // menu's "Run to here" has no such guard -- without this check, firing both triggers before
  // the first run finishes would interleave two SSE streams' updates into the one shared store.
  if (useExecutionStore.getState().running) {
    return;
  }

  const { runTo, runFrom, runOnly, params, onError } = options;
  const graph = useGraphStore.getState().toIR();
  // Only include a scope key when it is a non-empty string or a non-empty
  // array. Using `!== undefined` would send `run_to: []` alongside another
  // scope key, triggering a multi-scope 422 on the server.
  const scopeEntries = [
    ...(typeof runTo === "string" || (Array.isArray(runTo) && runTo.length > 0)
      ? [["run_to", runTo]]
      : []),
    ...(typeof runFrom === "string" ||
    (Array.isArray(runFrom) && runFrom.length > 0)
      ? [["run_from", runFrom]]
      : []),
    ...(typeof runOnly === "string" ||
      (Array.isArray(runOnly) && runOnly.length > 0)
      ? [["run_only", runOnly]]
      : []),
  ];
  const hasScope = scopeEntries.length > 0;
  const hasParams = params !== undefined && Object.keys(params).length > 0;
  const body: Record<string, unknown> = hasScope
    ? { graph, ...Object.fromEntries(scopeEntries) }
    : hasParams
      ? { graph }
      : (graph as unknown as Record<string, unknown>);
  if (hasParams) {
    body.params = params;
  }

  function fail(message: string) {
    useExecutionStore.getState().setError(message);
    onError?.(message);
  }

  useExecutionStore.getState().setRunning();
  try {
    const res = await fetch("/execute/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      fail(errBody.error ?? `Server error ${res.status}`);
      return;
    }
    if (!res.body) {
      fail("Server response had no body");
      return;
    }
    let checkedVersion = false;
    let settled = false;
    for await (const event of readSSEEvents(res.body)) {
      if (!checkedVersion) {
        checkedVersion = true;
        if (
          event.payload_version !== undefined &&
          event.payload_version !== EXPECTED_PAYLOAD_VERSION
        ) {
          fail(
            `Server payload version ${event.payload_version} is incompatible (expected ${EXPECTED_PAYLOAD_VERSION}). Restart the server or refresh the page.`,
          );
          return;
        }
      }
      switch (event.type) {
        case "node_start":
          useExecutionStore
            .getState()
            .setNodeStart(event.label, event.current, event.total);
          break;
        case "node_ok":
          if (event.cached) {
            useExecutionStore
              .getState()
              .setNodeCached(event.node_id, event.results);
          } else {
            useExecutionStore
              .getState()
              .setNodeResult(event.node_id, event.results);
          }
          break;
        case "node_error":
          useExecutionStore.getState().setNodeError(event.node_id, event.error);
          break;
        case "node_skip":
          useExecutionStore.getState().setNodeSkipped(event.node_id, event.reason);
          break;
        case "run_complete":
          settled = true;
          useExecutionStore.getState().setRunComplete();
          break;
        case "run_error":
          settled = true;
          fail(event.error);
          break;
      }
    }
    // The stream ended without a run_complete/run_error frame (a dropped connection, or a
    // server-side bug) -- without this, `running` would stay true forever with no error shown.
    if (!settled) {
      fail("Connection to the server was lost before the run finished.");
    }
  } catch (err) {
    fail(
      "Could not reach server: " +
        (err instanceof Error ? err.message : String(err)),
    );
  }
}
