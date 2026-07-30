import { useState, type CSSProperties, type KeyboardEvent } from "react";
import type { Node, NodeProps } from "@xyflow/react";

import { useGraphStore } from "../../store/graphStore";
import "./GroupNode.css";

export interface GroupNodeData extends Record<string, unknown> {
  label: string;
  color: string;
}

type GroupNodeType = Node<GroupNodeData, "groupNode">;

const GROUP_COLORS: Record<string, { background: string; border: string }> = {
  slate: { background: "#e2e8f0", border: "#64748b" },
  blue: { background: "#dbeafe", border: "#3b82f6" },
  green: { background: "#dcfce7", border: "#22c55e" },
  purple: { background: "#f3e8ff", border: "#a855f7" },
  amber: { background: "#fef3c7", border: "#f59e0b" },
  rose: { background: "#ffe4e6", border: "#f43f5e" },
};

const DEFAULT_COLOR = "slate";

const containerStyleBase: CSSProperties = {
  width: "100%",
  height: "100%",
  minWidth: 240,
  minHeight: 160,
  borderRadius: "var(--radius-md)",
  boxSizing: "border-box",
  display: "flex",
  flexDirection: "column",
};

export function GroupNode({ id, data }: NodeProps<GroupNodeType>): JSX.Element {
  const setParam = useGraphStore((s) => s.setParam);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(data.label);

  const swatch = GROUP_COLORS[data.color] ?? GROUP_COLORS[DEFAULT_COLOR];
  const containerStyle: CSSProperties = {
    ...containerStyleBase,
    border: `2px dashed ${swatch.border}`,
    background: `${swatch.background}55`,
  };

  function startEditing() {
    setDraft(data.label);
    setEditing(true);
  }

  function commit() {
    if (draft.trim() && draft !== data.label) {
      setParam(id, "label", draft);
    }
    setEditing(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      setDraft(data.label);
      setEditing(false);
    } else if (e.key === "Enter") {
      e.preventDefault();
      commit();
    }
  }

  return (
    <div style={containerStyle} data-testid="group-node">
      <div
        className="group-node-header nodrag"
        data-testid="group-node-header"
        style={{ borderBottom: `1px solid ${swatch.border}` }}
        onDoubleClick={startEditing}
      >
        {editing ? (
          <input
            data-testid="group-node-label-editor"
            className="nodrag"
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={onKeyDown}
          />
        ) : (
          <span data-testid="group-node-label">{data.label || "Group"}</span>
        )}
      </div>
      <div className="group-node-body" style={{ pointerEvents: "none" }} />
    </div>
  );
}

export default GroupNode;
