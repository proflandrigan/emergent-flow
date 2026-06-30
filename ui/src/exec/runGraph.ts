// The shared streaming-execute call: POSTs the current graph (optionally pruned to a single
// node's ancestor chain via `run_to`) to `/execute/stream` and applies each SSE event to
// `executionStore` incrementally as it arrives. Used by both ExecutionToolbar's "Execute" button
// (whole graph) and the canvas node context menu's "Run to here" action (pruned subgraph),
// Epic 7 Stories 4-5, so the two triggers share one implementation.

import { EXPECTED_PAYLOAD_VERSION } from "../store/execution";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { readSSEEvents } from "./sse";

export interface RunGraphOptions {
  /** If set, only this node's ancestor-closed subgraph runs ("run to here"). */
  runTo?: string;
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

  const { runTo, onError } = options;
  const graph = useGraphStore.getState().toIR();
  const body = runTo ? { graph, run_to: runTo } : graph;

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
          useExecutionStore.getState().setNodeStart(event.label, event.current, event.total);
          break;
        case "node_ok":
          useExecutionStore.getState().setNodeResult(event.node_id, event.results);
          break;
        case "node_error":
          useExecutionStore.getState().setNodeError(event.node_id, event.error);
          break;
        case "node_skip":
          useExecutionStore.getState().setNodeSkipped(event.node_id);
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
    fail("Could not reach server: " + (err instanceof Error ? err.message : String(err)));
  }
}
