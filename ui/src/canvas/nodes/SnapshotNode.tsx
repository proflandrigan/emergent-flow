import { type Node, type NodeProps } from "@xyflow/react";
import { Pin } from "lucide-react";

import "./SnapshotNode.css";
import { PayloadView } from "../../inspector/PayloadView";
import type { Payload } from "../../store/execution";

export interface SnapshotNodeData extends Record<string, unknown> {
  payload: Payload | null;
  portName: string;
  sourceLabel: string;
  caption: string;
}

type SnapshotNodeType = Node<SnapshotNodeData, "snapshotNode">;

const containerStyle: React.CSSProperties = {
  width: 260,
  borderRadius: "var(--radius-md)",
  background: "var(--surface-1)",
  fontSize: 11,
  boxSizing: "border-box",
  position: "relative",
  boxShadow: "var(--shadow-2)",
  border: "1px solid var(--border-subtle)",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-1)",
  padding: "var(--space-1) var(--space-2)",
  borderTopLeftRadius: "var(--radius-md)",
  borderTopRightRadius: "var(--radius-md)",
  background: "var(--surface-2)",
  borderBottom: "1px solid var(--border-subtle)",
  fontSize: 10,
  color: "var(--text-secondary)",
};

const bodyStyle: React.CSSProperties = {
  padding: "var(--space-1) var(--space-2)",
  maxHeight: 200,
  overflow: "auto",
};

export function SnapshotNode({ data }: NodeProps<SnapshotNodeType>): JSX.Element {
  const { payload, portName, sourceLabel, caption } = data;

  return (
    <div style={containerStyle} data-testid="snapshot-node">
      <div style={headerStyle} data-testid="snapshot-node-header">
        <Pin size={10} />
        <span>{sourceLabel}.{portName}</span>
      </div>
      <div style={bodyStyle} data-testid="snapshot-node-body">
        {payload ? (
          <PayloadView payload={payload} />
        ) : (
          <span style={{ color: "var(--text-secondary)", fontStyle: "italic" }}>
            Empty snapshot
          </span>
        )}
      </div>
      {caption ? (
        <div
          data-testid="snapshot-node-caption"
          style={{
            padding: "0 var(--space-2) var(--space-1)",
            fontSize: 10,
            color: "var(--text-secondary)",
            fontStyle: "italic",
          }}
        >
          {caption}
        </div>
      ) : null}
    </div>
  );
}

export default SnapshotNode;