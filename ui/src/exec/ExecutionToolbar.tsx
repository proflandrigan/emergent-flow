// Header controls for running the current graph. "Download .py" POSTs the IR to `/compile` and
// saves the returned code as a file; "Execute" POSTs the IR to `/execute/stream` and applies each
// SSE event to `executionStore` incrementally as it arrives, so node status/results update in
// real time instead of waiting for the whole graph to finish (Epic 7 Story 4).

import { useState } from "react";

import { useGraphStore } from "../store/graphStore";
import { useExecutionStore } from "../store/executionStore";
import { runGraph } from "./runGraph";

export function ExecutionToolbar(): JSX.Element {
  const [error, setError] = useState<string | null>(null);
  const running = useExecutionStore((s) => s.running);
  const progress = useExecutionStore((s) => s.progress);

  async function handleDownload() {
    const graph = useGraphStore.getState().toIR();
    if (Object.keys(graph.nodes ?? {}).length === 0) {
      setError("Add nodes before downloading.");
      return;
    }
    try {
      const res = await fetch("/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(graph),
      });
      const body = await res.json();
      if (!res.ok || body.error) {
        setError(body.error ?? `Server error ${res.status}`);
        return;
      }
      const blob = new Blob([body.code], { type: "text/x-python" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "graph.py";
      anchor.click();
      URL.revokeObjectURL(url);
      setError(null);
    } catch (err) {
      setError(
        "Could not reach server: " +
          (err instanceof Error ? err.message : String(err)),
      );
    }
  }

  async function handleExecute() {
    const graph = useGraphStore.getState().toIR();
    if (Object.keys(graph.nodes ?? {}).length === 0) {
      setError("Add nodes before executing.");
      return;
    }
    setError(null);
    await runGraph({ onError: setError });
  }

  return (
    <div
      style={{
        display: "inline-flex",
        flexDirection: "column",
        gap: "0.25rem",
      }}
    >
      <div style={{ display: "inline-flex", gap: "0.5rem" }}>
        <button
          type="button"
          data-testid="exec-download"
          onClick={handleDownload}
        >
          Download .py
        </button>
        <button
          type="button"
          data-testid="exec-run"
          disabled={running}
          onClick={handleExecute}
        >
          {running ? "Running…" : "Execute"}
        </button>
      </div>
      {progress && (
        <div data-testid="exec-progress" style={{ fontSize: 12, color: "#555" }}>
          Running node {progress.current} of {progress.total} ({progress.label}…)
        </div>
      )}
      {error && (
        <div role="alert" data-testid="exec-error" style={{ color: "#c00" }}>
          {error}
          <button type="button" onClick={() => setError(null)}>
            ×
          </button>
        </div>
      )}
    </div>
  );
}
