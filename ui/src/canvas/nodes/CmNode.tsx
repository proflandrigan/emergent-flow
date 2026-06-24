// Custom React Flow node renderer for Colony Mind canvas nodes. Purely presentational: it
// renders the label and one Handle per port (IN ports as targets on the left, OUT ports as
// sources on the right). The store stays the source of truth for IR data; this component only
// reflects `data` that `toReactFlow.ts` derived from a `NodeModel`.

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import type { CSSProperties } from "react";

// React Flow v12 constrains node `data` to `Record<string, unknown>`, so the data interface
// must carry an index signature; extending Record satisfies that without weakening the named
// fields (the index's `unknown` value type accepts anything).
export interface CmNodeData extends Record<string, unknown> {
  label: string;
  ports: { id: string; name: string; direction: "in" | "out" }[];
}

const boxStyle: CSSProperties = {
  width: 160,
  border: "1px solid #888",
  borderRadius: 6,
  background: "#fff",
  fontSize: 12,
  padding: "0.5rem",
  boxSizing: "border-box",
};

const portRowStyle: CSSProperties = {
  position: "relative",
  padding: "0.15rem 0.5rem",
  color: "#444",
};

type CmNodeType = Node<CmNodeData, "cmNode">;

export function CmNode({ data }: NodeProps<CmNodeType>): JSX.Element {
  const inPorts = data.ports.filter((port) => port.direction === "in");
  const outPorts = data.ports.filter((port) => port.direction === "out");

  return (
    <div style={boxStyle}>
      <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
        {data.label}
      </div>
      <div>
        {inPorts.map((port) => (
          <div key={port.id} style={{ ...portRowStyle, textAlign: "left" }}>
            <Handle
              type="target"
              position={Position.Left}
              id={port.id}
              style={{ left: -4 }}
            />
            {port.name}
          </div>
        ))}
        {outPorts.map((port) => (
          <div key={port.id} style={{ ...portRowStyle, textAlign: "right" }}>
            {port.name}
            <Handle
              type="source"
              position={Position.Right}
              id={port.id}
              style={{ right: -4 }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export default CmNode;
