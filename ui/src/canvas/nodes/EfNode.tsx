// Custom React Flow node renderer for Emergent Flow canvas nodes. Purely presentational: it
// renders the label and one Handle per port (IN ports as targets on the left, OUT ports as
// sources on the right). The store stays the source of truth for IR data; this component only
// reflects `data` that `toReactFlow.ts` derived from a `NodeModel`.

import {
  Handle,
  Position,
  useStore,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { useState, type CSSProperties } from "react";
import { Save } from "lucide-react";

import "./EfNode.css";
import { useCatalog } from "../../catalog/useCatalog";
import { PayloadView } from "../../inspector/PayloadView";
import type { NodeStatus, Payload } from "../../store/execution";
import { Tooltip } from "../../ui/Tooltip";
import { isDetailed } from "./lod";
import { familyMeta } from "../../theme/family";

// React Flow v12 constrains node `data` to `Record<string, unknown>`, so the data interface
// must carry an index signature; extending Record satisfies that without weakening the named
// fields (the index's `unknown` value type accepts anything).
export interface EfNodeData extends Record<string, unknown> {
  label: string;
  nodeType?: string;
  family?: string | null;
  ports: {
    id: string;
    name: string;
    direction: "in" | "out";
    label?: string | null;
  }[];
  status?: NodeStatus | null; // from /execute statuses
  results?: Record<string, Payload> | null; // outPortName -> payload
}

const boxStyleBase: CSSProperties = {
  width: 176,
  borderRadius: "var(--radius-md)",
  background: "var(--surface-1)",
  fontSize: 12,
  padding: "0.5rem",
  boxSizing: "border-box",
  position: "relative",
  boxShadow: "var(--shadow-2)",
};

const portRowStyle: CSSProperties = {
  position: "relative",
  padding: "0.15rem 0.5rem",
  color: "var(--text-secondary)",
};

const resultsToggleStyle: CSSProperties = {
  fontSize: "var(--text-xs)",
  marginTop: "0.25rem",
  background: "none",
  border: "none",
  padding: 0,
  cursor: "pointer",
  color: "var(--text-secondary)",
};

const resultsPanelStyle: CSSProperties = {
  marginTop: "0.25rem",
  maxHeight: 160,
  overflow: "auto",
  fontSize: "var(--text-xs)",
};

const cachedBadgeStyle: CSSProperties = {
  position: "absolute",
  bottom: -6,
  right: -6,
  fontSize: "var(--text-xs)",
  lineHeight: 1,
};

function borderColorFor(status: NodeStatus | null | undefined): string {
  switch (status) {
    case "ok":
      return "var(--success)";
    case "cached":
      return "var(--info)";
    case "error":
      return "var(--danger)";
    case "skipped":
      return "var(--border-strong)";
    default:
      return "var(--border-subtle)";
  }
}

type EfNodeType = Node<EfNodeData, "efNode">;

export function EfNode({ data }: NodeProps<EfNodeType>): JSX.Element {
  const [open, setOpen] = useState(false);
  const detailed = useStore((s) => isDetailed(s.transform[2]));

  const meta = familyMeta(data.family ?? "");
  const catalog = useCatalog();
  const catalogNode = data.nodeType
    ? catalog.nodes.find((n) => n.type === data.nodeType)
    : undefined;
  const description = catalogNode?.description;
  const FamIcon = meta.Icon;

  const inPorts = data.ports.filter((port) => port.direction === "in");
  const outPorts = data.ports.filter((port) => port.direction === "out");

  const resultEntries = data.results ? Object.entries(data.results) : [];
  const hasResults = resultEntries.length > 0;

  const headerStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-2)",
    marginLeft: "calc(-1 * var(--space-2))",
    marginRight: "calc(-1 * var(--space-2))",
    marginTop: "calc(-1 * var(--space-2))",
    marginBottom: "var(--space-2)",
    padding: "var(--space-2) var(--space-3)",
    borderTopLeftRadius: "var(--radius-md)",
    borderTopRightRadius: "var(--radius-md)",
    background: meta.soft,
    borderLeft: `3px solid ${meta.color}`,
    fontWeight: 600,
    color: "var(--text-primary)",
    fontSize: "var(--text-sm)",
  };

  const boxStyle: CSSProperties = {
    ...boxStyleBase,
    border: `1px solid ${borderColorFor(data.status)}`,
  };

  switch (data.status) {
    case "cached":
      boxStyle.boxShadow = `var(--shadow-2), 0 0 0 3px ${borderColorFor("cached")}`;
      break;
    case "error":
      boxStyle.boxShadow = `var(--shadow-2), 0 0 0 3px ${borderColorFor("error")}, 0 0 12px 2px var(--danger-soft)`;
      break;
    case "skipped":
      boxStyle.opacity = 0.6;
      break;
  }

  return (
    <div
      style={boxStyle}
      data-testid="ef-node"
      className={data.status === "running" ? "ef-node--running" : undefined}
    >
      {description ? (
        <Tooltip label={description}>
          <div style={headerStyle}>
            <FamIcon size={14} style={{ color: meta.color, flexShrink: 0 }} />
            <span>{data.label}</span>
          </div>
        </Tooltip>
      ) : (
        <div style={headerStyle}>
          <FamIcon size={14} style={{ color: meta.color, flexShrink: 0 }} />
          <span>{data.label}</span>
        </div>
      )}
      <div>
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
                background: meta.color,
                border: "2px solid var(--border-strong)",
                borderRadius: "50%",
              }}
            />
            <span style={{ visibility: detailed ? "visible" : "hidden" }}>
              {port.label ?? port.name}
            </span>
          </div>
        ))}
        {outPorts.map((port) => (
          <div key={port.id} style={{ ...portRowStyle, textAlign: "right" }}>
            <span style={{ visibility: detailed ? "visible" : "hidden" }}>
              {port.label ?? port.name}
            </span>
            <Handle
              type="source"
              position={Position.Right}
              id={port.id}
              style={{
                right: -4,
                width: 8,
                height: 8,
                background: meta.color,
                border: "2px solid var(--border-strong)",
                borderRadius: "50%",
              }}
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
            <div
              className="nodrag"
              data-testid="node-results"
              style={resultsPanelStyle}
            >
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
      {data.status === "cached" ? (
        <span
          data-testid="node-cached-badge"
          title="Served from the execution cache"
          style={cachedBadgeStyle}
        >
          <Save size={12} style={{ color: "var(--text-secondary)", display: "block" }} />
        </span>
      ) : null}
    </div>
  );
}

export default EfNode;
