import { useState, type CSSProperties, type KeyboardEvent } from "react";
import type { Node, NodeProps } from "@xyflow/react";

import { useGraphStore } from "../../store/graphStore";

export interface GroupNodeData extends Record<string, unknown> {
  groupId: string;
  label: string;
  color: string;
  memberCount: number;
  memberCompleteCount: number;
  memberErrorCount: number;
}

type GroupNodeType = Node<GroupNodeData, "groupNode">;

export function GroupNode({ data }: NodeProps<GroupNodeType>): JSX.Element {
  const setGroupMeta = useGraphStore((s) => s.setGroupMeta);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(data.label);

  function startEditing() {
    setDraft(data.label);
    setEditing(true);
  }

  function commit() {
    if (draft !== data.label) {
      setGroupMeta(data.groupId, { label: draft });
    }
    setEditing(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      setDraft(data.label);
      setEditing(false);
    } else if (e.key === "Enter") {
      commit();
    }
  }

  // header: 28px tall, color + "22" background, color + "66" border-bottom
  const headerStyle: CSSProperties = {
    height: 28,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 var(--space-2)",
    background: data.color + "22",
    borderBottom: `2px solid ${data.color}66`,
    borderTopLeftRadius: "var(--radius-md)",
    borderTopRightRadius: "var(--radius-md)",
    color: data.color,
    fontWeight: 600,
    fontSize: "var(--text-sm)",
  };

  const memberCountPillStyle: CSSProperties = {
    background: data.color + "33",
    borderRadius: 10,
    padding: "0 6px",
    fontSize: "var(--text-xs)",
    lineHeight: "18px",
    color: data.color,
  };

  const statusDotStyle: CSSProperties = {
    width: 8,
    height: 8,
    borderRadius: "50%",
    display: "inline-block",
    flexShrink: 0,
  };

  const boxStyle: CSSProperties = {
    minWidth: 200,
    minHeight: 80,
    borderRadius: "var(--radius-md)",
    background: data.color + "14",
    border: `2px solid ${data.color}66`,
    boxSizing: "border-box",
  };

  // Determine aggregate status
  let statusIndicator: JSX.Element | null = null;
  if (data.memberErrorCount > 0) {
    statusIndicator = <span style={{ ...statusDotStyle, background: "#ef4444" }} title={`${data.memberErrorCount} errors`} />;
  } else if (data.memberCompleteCount === data.memberCount && data.memberCount > 0) {
    statusIndicator = <span style={{ ...statusDotStyle, background: "#22c55e" }} title="All complete" />;
  }

  return (
    <div style={boxStyle} data-testid="group-node">
      <div style={headerStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-1)", flex: 1, minWidth: 0 }}>
          {statusIndicator}
          {editing ? (
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onKeyDown={onKeyDown}
              className="nodrag"
              style={{
                background: "transparent",
                border: "none",
                outline: "none",
                color: "inherit",
                font: "inherit",
                fontWeight: 600,
                fontSize: "var(--text-sm)",
                width: "100%",
              }}
              data-testid="group-node-label-editor"
            />
          ) : (
            <span
              onDoubleClick={startEditing}
              style={{
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                cursor: "pointer",
              }}
              data-testid="group-node-label"
            >
              {data.label}
            </span>
          )}
        </div>
        <span style={memberCountPillStyle} data-testid="group-node-count">
          {data.memberCount}
        </span>
      </div>
      <div style={{ padding: "var(--space-2) var(--space-3)", fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
        {data.memberCount} node{data.memberCount !== 1 ? "s" : ""}
      </div>
    </div>
  );
}

export default GroupNode;
