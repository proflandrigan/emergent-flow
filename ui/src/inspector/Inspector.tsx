// Right-side Inspector dock (Epic 5 Story 4): a tabbed panel with Config, Code, and Results
// tabs. Renders the Config form for the single selected node (or an empty-state prompt), the
// Code tab's live-compiled output, and the Results tab's last execution output for the selected
// node; selection is read from `selectionStore`, never the IR.

import { useState } from "react";

import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { selectedNodeId, useSelectionStore } from "../store/selectionStore";
import { CodePanel } from "./CodePanel";
import { ConfigForm } from "./ConfigForm";
import { PayloadView } from "./PayloadView";

type InspectorTab = "config" | "code" | "results";

// Renders a past millisecond timestamp as a coarse "Ns ago" relative to now.
function formatAgo(ms: number): string {
  const secs = Math.max(0, Math.round((Date.now() - ms) / 1000));
  return `${secs}s ago`;
}

export function Inspector(): JSX.Element {
  const [tab, setTab] = useState<InspectorTab>("config");
  const selNodes = useSelectionStore((s) => s.nodes);
  const nodes = useGraphStore((s) => s.nodes);
  const nodeId = selectedNodeId({ nodes: selNodes });
  const node = nodeId ? nodes[nodeId] : null;

  const results = useExecutionStore((s) => s.results);
  const statuses = useExecutionStore((s) => s.statuses);
  const lastRunAt = useExecutionStore((s) => s.lastRunAt);

  function renderResults(): JSX.Element {
    if (!nodeId) {
      return (
        <p data-testid="results-empty-no-selection" style={{ color: "#666" }}>
          Select a node to see its results.
        </p>
      );
    }
    const status = statuses[nodeId];
    if (status?.status === "error") {
      return (
        <div
          data-testid="results-error"
          style={{ color: "#b00", whiteSpace: "pre-wrap" }}
        >
          {status.error ?? "Execution failed."}
        </div>
      );
    }
    const nodeResults = results[nodeId];
    if (!nodeResults || Object.keys(nodeResults).length === 0) {
      return (
        <p data-testid="results-empty-no-run" style={{ color: "#666" }}>
          No results — run the graph first.
        </p>
      );
    }
    return (
      <div data-testid="results-list">
        {lastRunAt !== null ? (
          <div
            data-testid="results-last-run"
            style={{ color: "#666", fontSize: 11, marginBottom: "0.5rem" }}
          >
            last run: {formatAgo(lastRunAt)}
          </div>
        ) : null}
        {Object.entries(nodeResults).map(([portName, payload]) => (
          <div key={portName} style={{ marginBottom: "0.5rem" }}>
            <span style={{ fontWeight: 600 }}>{portName}</span>
            <PayloadView payload={payload} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <aside
      data-testid="inspector"
      style={{
        width: 300,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        borderLeft: "1px solid #ddd",
        height: "100%",
      }}
    >
      <div style={{ display: "flex", borderBottom: "1px solid #ddd" }}>
        <button
          type="button"
          data-testid="inspector-tab-config"
          onClick={() => setTab("config")}
          style={{
            flex: 1,
            padding: "0.5rem",
            border: "none",
            background: "none",
            cursor: "pointer",
            fontWeight: tab === "config" ? 600 : 400,
            borderBottom:
              tab === "config" ? "2px solid #333" : "2px solid transparent",
          }}
        >
          Config
        </button>
        <button
          type="button"
          data-testid="inspector-tab-code"
          onClick={() => setTab("code")}
          style={{
            flex: 1,
            padding: "0.5rem",
            border: "none",
            background: "none",
            cursor: "pointer",
            fontWeight: tab === "code" ? 600 : 400,
            borderBottom:
              tab === "code" ? "2px solid #333" : "2px solid transparent",
          }}
        >
          Code
        </button>
        <button
          type="button"
          data-testid="inspector-tab-results"
          onClick={() => setTab("results")}
          style={{
            flex: 1,
            padding: "0.5rem",
            border: "none",
            background: "none",
            cursor: "pointer",
            fontWeight: tab === "results" ? 600 : 400,
            borderBottom:
              tab === "results" ? "2px solid #333" : "2px solid transparent",
          }}
        >
          Results
        </button>
      </div>
      <div
        style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "0.5rem" }}
      >
        {tab === "config" ? (
          node ? (
            <ConfigForm node={node} />
          ) : (
            <p data-testid="inspector-empty" style={{ color: "#666" }}>
              Select a node to edit its parameters.
            </p>
          )
        ) : tab === "code" ? (
          <CodePanel />
        ) : (
          renderResults()
        )}
      </div>
    </aside>
  );
}
