// A small info panel showing a node's full catalog metadata. Opened from the right-click
// context menu on canvas nodes.

import type { JSX } from "react";
import type { CatalogNode } from "../catalog/types";

export interface NodeInfoPanelProps {
  node: CatalogNode;
}

export function NodeInfoPanel({ node }: NodeInfoPanelProps): JSX.Element {
  return (
    <div data-testid="node-info-panel">
      <h2 style={{ margin: 0, fontSize: "var(--text-md)" }}>{node.label}</h2>
      <div
        style={{
          color: "var(--text-tertiary)",
          fontSize: "var(--text-xs)",
          marginBottom: "var(--space-3)",
        }}
      >
        {node.type}
      </div>
      {node.description && <p>{node.description}</p>}
      <div style={{ marginBottom: "var(--space-2)" }}>
        <strong>Family:</strong> {node.family}
      </div>
      {node.ports.length > 0 && (
        <div style={{ marginBottom: "var(--space-3)" }}>
          <strong>Ports</strong>
          <ul style={{ margin: "var(--space-1) 0", paddingLeft: "var(--space-4)" }}>
            {node.ports.map((port) => (
              <li key={`${port.direction}-${port.name}`}>
                <span style={{ fontWeight: 600 }}>{port.label ?? port.name}</span>{" "}
                <span style={{ color: "var(--text-tertiary)" }}>
                  ({port.direction})
                </span>
                {port.help && (
                  <div
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "var(--text-xs)",
                    }}
                  >
                    {port.help}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {node.params.length > 0 && (
        <div>
          <strong>Params</strong>
          <ul style={{ margin: "var(--space-1) 0", paddingLeft: "var(--space-4)" }}>
            {node.params.map((param) => (
              <li key={param.name}>
                <span style={{ fontWeight: 600 }}>{param.label ?? param.name}</span>
                {param.help && (
                  <div
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "var(--text-xs)",
                    }}
                  >
                    {param.help}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default NodeInfoPanel;
