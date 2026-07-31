import { Layers } from "lucide-react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import "./CompositeNode.css";

export interface CompositeNodeData extends Record<string, unknown> {
  label: string;
  ports: {
    id: string;
    name: string;
    direction: "in" | "out";
    label?: string | null;
  }[];
  memberCount: number;
}

type CompositeNodeType = Node<CompositeNodeData, "compositeNode">;

const containerStyle: React.CSSProperties = {
  width: 200,
  borderRadius: "var(--radius-md)",
  background: "var(--surface-1)",
  fontSize: 12,
  boxSizing: "border-box",
  position: "relative",
  boxShadow: "var(--shadow-2)",
  border: "2px solid var(--fam-layout)",
  overflow: "hidden",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-2)",
  padding: "var(--space-2) var(--space-3)",
  background: "var(--fam-layout-soft)",
  borderBottom: "1px solid var(--fam-layout)",
  fontWeight: 600,
  color: "var(--text-primary)",
  fontSize: "var(--text-sm)",
};

const bodyStyle: React.CSSProperties = {
  padding: "0.5rem",
  display: "flex",
  flexDirection: "column",
  gap: "0.25rem",
};

const drillHintStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "var(--space-1)",
  padding: "0.25rem 0.5rem",
  marginTop: "0.25rem",
  borderRadius: "var(--radius-sm)",
  background: "var(--surface-2)",
  color: "var(--text-secondary)",
  fontSize: "var(--text-xs)",
  cursor: "pointer",
  border: "1px dashed var(--border-subtle)",
};

const portRowStyle: React.CSSProperties = {
  position: "relative",
  padding: "0.15rem 0.5rem",
  color: "var(--text-secondary)",
};

export function CompositeNode({ data }: NodeProps<CompositeNodeType>): JSX.Element {
  const inPorts = data.ports.filter((port) => port.direction === "in");
  const outPorts = data.ports.filter((port) => port.direction === "out");

  return (
    <div style={containerStyle} data-testid="composite-node">
      <div style={headerStyle} data-testid="composite-node-header">
        <Layers size={14} style={{ color: "var(--fam-layout)", flexShrink: 0 }} />
        <span data-testid="composite-node-label">{data.label}</span>
      </div>
      <div style={bodyStyle}>
        <div
          data-testid="composite-node-drill-hint"
          style={drillHintStyle}
          className="nodrag"
        >
          <Layers size={12} />
          <span>{data.memberCount} nodes &middot; double-click to open</span>
        </div>
        <div data-testid="composite-node-ports">
          {inPorts.map((port) => (
            <div key={port.id} style={{ ...portRowStyle, textAlign: "left" }}>
              <Handle
                type="target"
                position={Position.Left}
                id={port.id}
                style={{
                  left: -4,
                  width: 8,
                  height: 8,
                  background: "var(--fam-layout)",
                  border: "2px solid var(--border-strong)",
                  borderRadius: "50%",
                }}
              />
              <span>{port.label ?? port.name}</span>
            </div>
          ))}
          {outPorts.map((port) => (
            <div key={port.id} style={{ ...portRowStyle, textAlign: "right" }}>
              <Handle
                type="source"
                position={Position.Right}
                id={port.id}
                style={{
                  right: -4,
                  width: 8,
                  height: 8,
                  background: "var(--fam-layout)",
                  border: "2px solid var(--border-strong)",
                  borderRadius: "50%",
                }}
              />
              <span>{port.label ?? port.name}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default CompositeNode;
