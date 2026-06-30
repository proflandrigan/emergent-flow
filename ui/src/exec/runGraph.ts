// The shared streaming-execute call: POSTs the current graph (optionally pruned to a single
// node's ancestor chain via `run_to`) to `/execute/stream` and applies each SSE event to
// `executionStore` incrementally as it arrives. Used by both ExecutionToolbar's "Execute" button
// (whole graph) and the canvas node context menu's "Run to here" action (pruned subgraph),
// Epic 7 Stories 4-5, so the two triggers share one implementation.

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
    for await (const event of readSSEEvents(res.body)) {
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
        case "run_complete":
          useExecutionStore.getState().setRunComplete();
          break;
        case "run_error":
          fail(event.error);
          break;
      }
    }
  } catch (err) {
    fail("Could not reach server: " + (err instanceof Error ? err.message : String(err)));
  }
}
