// Right-side Inspector dock (Epic 5 Story... inspector shell): a tabbed panel with Config and
// Code tabs. This task builds only the shell + tab switching + empty states -- the Config form
// and Code panel are filled in by later tasks; for now each tab renders a trivial placeholder.

import { useState } from "react";

import { useGraphStore } from "../store/graphStore";
import { selectedNodeId, useSelectionStore } from "../store/selectionStore";
import { CodePanel } from "./CodePanel";
import { ConfigForm } from "./ConfigForm";

type InspectorTab = "config" | "code";

export function Inspector(): JSX.Element {
  const [tab, setTab] = useState<InspectorTab>("config");
  const selNodes = useSelectionStore((s) => s.nodes);
  const nodes = useGraphStore((s) => s.nodes);
  const nodeId = selectedNodeId({ nodes: selNodes });
  const node = nodeId ? nodes[nodeId] : null;

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
        ) : (
          <CodePanel />
        )}
      </div>
    </aside>
  );
}
