// Custom React Flow node renderer for Colony Mind canvas nodes. Purely presentational: it
// renders the label and one Handle per port (IN ports as targets on the left, OUT ports as
// sources on the right). The store stays the source of truth for IR data; this component only
// reflects `data` that `toReactFlow.ts` derived from a `NodeModel`.

import { Handle, Position, useStore, type Node, type NodeProps } from "@xyflow/react";
import { useState, type CSSProperties } from "react";

import { PayloadView } from "../../inspector/PayloadView";
import type { NodeStatus, Payload } from "../../store/execution";
import { isDetailed } from "./lod";

// React Flow v12 constrains node `data` to `Record<string, unknown>`, so the data interface
// must carry an index signature; extending Record satisfies that without weakening the named
// fields (the index's `unknown` value type accepts anything).
export interface CmNodeData extends Record<string, unknown> {
  label: string;
  ports: { id: string; name: string; direction: "in" | "out" }[];
  status?: NodeStatus | null; // from /execute statuses
  results?: Record<string, Payload> | null; // outPortName -> payload
}

const boxStyleBase: CSSProperties = {
  width: 160,
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

const resultsToggleStyle: CSSProperties = {
  fontSize: 11,
  marginTop: "0.25rem",
  background: "none",
  border: "none",
  padding: 0,
  cursor: "pointer",
  color: "#444",
};

const resultsPanelStyle: CSSProperties = {
  marginTop: "0.25rem",
  maxHeight: 160,
  overflow: "auto",
  fontSize: 11,
};

function borderColorFor(status: NodeStatus | null | undefined): string {
  switch (status) {
    case "ok":
      return "#2e7d32";
    case "error":
      return "#c00";
    case "skipped":
      return "#bbb";
    default:
      return "#888";
  }
}

type CmNodeType = Node<CmNodeData, "cmNode">;

export function CmNode({ data }: NodeProps<CmNodeType>): JSX.Element {
  const [open, setOpen] = useState(false);
  const detailed = useStore((s) => isDetailed(s.transform[2]));

  const inPorts = data.ports.filter((port) => port.direction === "in");
  const outPorts = data.ports.filter((port) => port.direction === "out");

  const resultEntries = data.results ? Object.entries(data.results) : [];
  const hasResults = resultEntries.length > 0;

  const borderColor = borderColorFor(data.status);
  const boxStyle: CSSProperties = {
    ...boxStyleBase,
    border: `1px solid ${borderColor}`,
  };

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
            <span style={{ visibility: detailed ? "visible" : "hidden" }}>{port.name}</span>
          </div>
        ))}
        {outPorts.map((port) => (
          <div key={port.id} style={{ ...portRowStyle, textAlign: "right" }}>
            <span style={{ visibility: detailed ? "visible" : "hidden" }}>{port.name}</span>
            <Handle
              type="source"
              position={Position.Right}
              id={port.id}
              style={{ right: -4 }}
            />
          </div>
        ))}
      </div>
      {hasResults && detailed ? (
        <>
          <button
            type="button"
            className="nodrag"
            data-testid="node-results-toggle"
            style={resultsToggleStyle}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? "▾" : "▸"} results
          </button>
          {open ? (
            <div className="nodrag" data-testid="node-results" style={resultsPanelStyle}>
              {resultEntries.map(([portName, payload]) => (
                <div key={portName}>
                  <span style={{ fontWeight: 600 }}>{portName}</span>
                  <PayloadView payload={payload} />
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export default CmNode;
