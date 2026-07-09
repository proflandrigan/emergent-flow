/* eslint-disable react-refresh/only-export-components */
// React Flow presentational pieces for a pending GraphMutation overlay (Epic 14 Story 4): a
// dashed "ghost" node type for proposed additions, a dashed ghost edge type, and a small badge
// node type for marking an EXISTING node with a pending param change or pending removal (so
// EfNode.tsx itself never needs to know about proposals). Pure mapper functions turn a
// `GhostDiff` (ghostDiff.ts) + the current `CanvasModel` into React Flow node/edge arrays a
// LATER task merges into Canvas.tsx's own `rfNodes`/`rfEdges`. This module renders nothing on
// its own -- nothing here runs unless a caller imports and uses it (works-without-agents).

import {
  BaseEdge,
  getBezierPath,
  Handle,
  Position,
  type Edge as RFEdge,
  type EdgeProps,
  type Node as RFNode,
  type NodeProps,
} from "@xyflow/react";
import type { CSSProperties } from "react";

import type { CanvasModel } from "../store/model";
import type { GhostDiff } from "./ghostDiff";

export interface GhostNodeData extends Record<string, unknown> {
  label: string;
  ports: { id: string; name: string; direction: "in" | "out" }[];
}

type GhostNodeType = RFNode<GhostNodeData, "efGhostNode">;

const ghostBoxStyle: CSSProperties = {
  width: 176,
  borderRadius: "var(--radius-md)",
  background: "var(--surface-1)",
  border: "1px dashed var(--accent)",
  opacity: 0.8,
  fontSize: 12,
  padding: "0.5rem",
  boxSizing: "border-box",
};

const ghostHandleStyle: CSSProperties = {
  width: 8,
  height: 8,
  background: "var(--accent)",
  border: "2px solid var(--border-strong)",
  borderRadius: "50%",
};

export function GhostNode({ data }: NodeProps<GhostNodeType>): JSX.Element {
  const inPorts = data.ports.filter((port) => port.direction === "in");
  const outPorts = data.ports.filter((port) => port.direction === "out");

  return (
    <div style={ghostBoxStyle} data-testid="ef-ghost-node">
      <div style={{ fontWeight: 600, marginBottom: "0.15rem" }}>
        {data.label}
      </div>
      <div style={{ fontSize: "var(--text-xs)", color: "var(--accent)" }}>
        proposed
      </div>
      {inPorts.map((port) => (
        <Handle
          key={port.id}
          type="target"
          position={Position.Left}
          id={port.id}
          style={{ ...ghostHandleStyle, left: -4 }}
        />
      ))}
      {outPorts.map((port) => (
        <Handle
          key={port.id}
          type="source"
          position={Position.Right}
          id={port.id}
          style={{ ...ghostHandleStyle, right: -4 }}
        />
      ))}
    </div>
  );
}

export interface GhostBadgeData extends Record<string, unknown> {
  label: string;
}

type GhostBadgeType = RFNode<GhostBadgeData, "efGhostBadge">;

export function GhostBadge({ data }: NodeProps<GhostBadgeType>): JSX.Element {
  return (
    <div
      data-testid="ef-ghost-badge"
      style={{
        fontSize: "var(--text-xs)",
        padding: "0.1rem 0.4rem",
        borderRadius: "var(--radius-sm)",
        background: "var(--accent-soft)",
        color: "var(--accent)",
        border: "1px solid var(--accent)",
        whiteSpace: "nowrap",
      }}
    >
      {data.label}
    </div>
  );
}

type GhostEdgeType = RFEdge<Record<string, unknown>, "efGhostEdge">;

export function GhostEdge(props: EdgeProps<GhostEdgeType>): JSX.Element {
  const { sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition } =
    props;
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  return (
    <BaseEdge
      id={props.id}
      path={edgePath}
      style={{
        stroke: "var(--accent)",
        strokeWidth: 1.5,
        strokeDasharray: "4 3",
      }}
    />
  );
}

export const ghostNodeTypes = {
  efGhostNode: GhostNode,
  efGhostBadge: GhostBadge,
};
export const ghostEdgeTypes = { efGhostEdge: GhostEdge };

const BADGE_OFFSET_X = 140;
const BADGE_OFFSET_Y = -24;

// Pure: projects a GhostDiff + the current CanvasModel into React Flow nodes -- added-node
// ghosts (draggable/selectable disabled -- they aren't real yet) plus one small badge node per
// existing node with a pending param change or pending removal, positioned near that node.
// Skips a badge if its target node id isn't in *model* (defensive against a stale diff).
export function toGhostRFNodes(diff: GhostDiff, model: CanvasModel): RFNode[] {
  const added: RFNode[] = diff.addedNodes.map((node) => ({
    id: node.id,
    type: "efGhostNode",
    position: node.position,
    selectable: false,
    draggable: false,
    data: {
      label: node.label ?? node.type,
      ports: node.ports.map((port) => ({
        id: port.id,
        name: port.name,
        direction: port.direction,
      })),
    } satisfies GhostNodeData,
  }));

  const badgeKinds: [string, string, ReadonlySet<string>][] = [
    ["params", "params", diff.paramChangedNodeIds],
    ["remove", "remove", diff.removedNodeIds],
  ];
  const badges: RFNode[] = [];
  for (const [idPrefix, label, nodeIds] of badgeKinds) {
    for (const nodeId of nodeIds) {
      const existing = model.nodes[nodeId];
      if (!existing) continue;
      badges.push({
        id: `ghost-badge-${idPrefix}:${nodeId}`,
        type: "efGhostBadge",
        position: {
          x: existing.position.x + BADGE_OFFSET_X,
          y: existing.position.y + BADGE_OFFSET_Y,
        },
        selectable: false,
        draggable: false,
        data: { label } satisfies GhostBadgeData,
      });
    }
  }

  return [...added, ...badges];
}

// Pure: projects a GhostDiff's added edges into React Flow ghost edges.
export function toGhostRFEdges(diff: GhostDiff): RFEdge[] {
  return diff.addedEdges.map((edge) => ({
    id: edge.id,
    type: "efGhostEdge",
    source: edge.source.node_id,
    sourceHandle: edge.source.port_id,
    target: edge.target.node_id,
    targetHandle: edge.target.port_id,
    selectable: false,
  }));
}
