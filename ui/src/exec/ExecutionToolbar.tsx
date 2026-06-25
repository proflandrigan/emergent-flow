// Header controls for running the current graph (Story 8). "Download .py" POSTs the IR to
// `/compile` and saves the returned code as a file; "Execute" POSTs the IR to `/execute` and
// writes the response into `executionStore` for Task 07 to render. This component only
// triggers the run + stores the response -- it does not render results itself.

import { useState } from "react";

import { useGraphStore } from "../store/graphStore";
import { useExecutionStore } from "../store/executionStore";

export function ExecutionToolbar(): JSX.Element {
  const [error, setError] = useState<string | null>(null);
  const running = useExecutionStore((s) => s.running);

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
    useExecutionStore.getState().setRunning();
    try {
      const res = await fetch("/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(graph),
      });
      const body = await res.json();
      if (!res.ok || body.error) {
        const msg = body.error ?? `Server error ${res.status}`;
        useExecutionStore.getState().setError(msg);
        setError(msg);
        return;
      }
      useExecutionStore.getState().setResult(body);
      setError(null);
    } catch (err) {
      const msg =
        "Could not reach server: " +
        (err instanceof Error ? err.message : String(err));
      useExecutionStore.getState().setError(msg);
      setError(msg);
    }
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
