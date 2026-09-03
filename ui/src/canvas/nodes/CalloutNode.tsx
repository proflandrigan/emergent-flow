import { type CSSProperties } from "react";
import type { Node, NodeProps } from "@xyflow/react";

export interface CalloutNodeData extends Record<string, unknown> {
  label: string;
  color: string;
  width: number;
  height: number;
}

type CalloutNodeType = Node<CalloutNodeData, "calloutNode">;

const CALLOUT_COLORS: Record<string, { background: string; border: string }> = {
  slate: { background: "#e2e8f0", border: "#64748b" },
  blue: { background: "#dbeafe", border: "#3b82f6" },
  green: { background: "#dcfce7", border: "#22c55e" },
  purple: { background: "#f3e8ff", border: "#a855f7" },
  amber: { background: "#fef3c7", border: "#f59e0b" },
  rose: { background: "#ffe4e6", border: "#f43f5e" },
};

const DEFAULT_COLOR = "blue";

const containerStyleBase: CSSProperties = {
  borderRadius: "var(--radius-md)",
  boxSizing: "border-box",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

export function CalloutNode({ data }: NodeProps<CalloutNodeType>): JSX.Element {
  const swatch = CALLOUT_COLORS[data.color] ?? CALLOUT_COLORS[DEFAULT_COLOR];
  const containerStyle: CSSProperties = {
    ...containerStyleBase,
    width: data.width || 400,
    height: data.height || 300,
    border: `2px dashed ${swatch.border}`,
    background: `${swatch.background}44`,
  };

  return (
    <div style={containerStyle} data-testid="callout-node">
      <div
        style={{
          padding: "4px 8px",
          fontSize: "var(--text-xs)",
          fontWeight: 600,
          color: swatch.border,
          background: `${swatch.background}88`,
          borderBottom: `1px dashed ${swatch.border}`,
          userSelect: "none",
        }}
        data-testid="callout-node-header"
      >
        {data.label || "Callout"}
      </div>
    </div>
  );
}

export default CalloutNode;