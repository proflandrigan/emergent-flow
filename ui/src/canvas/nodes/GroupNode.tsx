import { ChevronDown, ChevronRight } from "lucide-react";
import { useMemo, useState, type CSSProperties, type KeyboardEvent, type MouseEvent } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { useCollapseStore } from "../../store/collapseStore";
import type { NodeStatus } from "../../store/execution";
import { useExecutionStore } from "../../store/executionStore";
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

// Priority order matches the issue's own wording: any failure wins, then any still running,
// then "all cached" / "all ok". Anything else (an empty group, or a genuine mix like some ok
// and some never-run) has no single meaningful aggregate -- returns null.
export function aggregateGroupStatus(
  statuses: Array<NodeStatus | null | undefined>,
): NodeStatus | null {
  if (statuses.length === 0) {
    return null;
  }
  if (statuses.some((s) => s === "error")) {
    return "error";
  }
  if (statuses.some((s) => s === "running")) {
    return "running";
  }
  if (statuses.every((s) => s === "cached")) {
    return "cached";
  }
  if (statuses.every((s) => s === "ok" || s === "cached")) {
    return "ok";
  }
  return null;
}

function statusDotColor(status: NodeStatus | null): string {
  switch (status) {
    case "ok":
      return "var(--success)";
    case "cached":
      return "var(--info)";
    case "error":
      return "var(--danger)";
    case "running":
      return "var(--warning)";
    default:
      return "var(--text-tertiary)";
  }
}

export function GroupNode({ id, data }: NodeProps<GroupNodeType>): JSX.Element {
  const setParam = useGraphStore((s) => s.setParam);
  const nodes = useGraphStore((s) => s.nodes);
  const statuses = useExecutionStore((s) => s.statuses);
  const collapsed = useCollapseStore((s) => !!s.collapsed[id]);
  const toggleCollapsed = useCollapseStore((s) => s.toggleCollapsed);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(data.label);

  const members = useMemo(
    () => Object.values(nodes).filter((n) => n.groupId === id),
    [nodes, id],
  );
  const aggregateStatus = useMemo(
    () => aggregateGroupStatus(members.map((m) => statuses[m.id]?.status)),
    [members, statuses],
  );

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

  function handleToggleCollapse(e: MouseEvent) {
    e.stopPropagation();
    toggleCollapsed(id);
  }

  return (
    <div style={containerStyle} data-testid="group-node">
      <div
        className="group-node-header nodrag"
        data-testid="group-node-header"
        style={{ borderBottom: `1px solid ${swatch.border}` }}
        onDoubleClick={startEditing}
      >
        <button
          type="button"
          className="group-node-collapse-toggle nodrag"
          data-testid="group-node-collapse-toggle"
          aria-label={collapsed ? "Expand group" : "Collapse group"}
          onClick={handleToggleCollapse}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        </button>
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
      {collapsed ? (
        <>
          <Handle type="target" position={Position.Left} id="group-in" />
          <Handle type="source" position={Position.Right} id="group-out" />
          <div className="group-node-summary" data-testid="group-node-summary">
            <span
              className="group-node-status-dot"
              data-testid="group-node-status-dot"
              style={{ background: statusDotColor(aggregateStatus) }}
            />
            <span data-testid="group-node-member-count">
              {members.length} {members.length === 1 ? "node" : "nodes"}
            </span>
          </div>
        </>
      ) : (
        <div
          className="group-node-body"
          data-testid="group-node-body"
          style={{ pointerEvents: "none" }}
        />
      )}
    </div>
  );
}

export default GroupNode;
