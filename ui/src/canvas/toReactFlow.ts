// Pure derivation helpers: map store `NodeModel`/`EdgeModel` records to React Flow's
// `Node`/`Edge` shapes. The store stays the single source of truth for IR data (ADR 0014
// Decision 3); these functions never mutate anything, they only project.

import type { Edge as RFEdge, Node as RFNode } from "@xyflow/react";

import type { EdgeModel, NodeModel } from "../store/model";
import type { NodeStatus, Payload } from "../store/execution";
import type { EfEdgeData } from "./edges/EfEdge";
import type { EfNodeData } from "./nodes/EfNode";
import type { GroupNodeData } from "./nodes/GroupNode";
import type { NoteNodeData } from "./nodes/NoteNode";

export type AnyRFNode = RFNode<EfNodeData> | RFNode<NoteNodeData> | RFNode<GroupNodeData>;

const NOTE_NODE_TYPE = "notes.markdown";

export function toRFNode(
  node: NodeModel,
  selected: boolean,
  status: NodeStatus | null | undefined,
  results: Record<string, Payload> | null | undefined,
  family: string | null | undefined,
  description: string | null | undefined,
  groupMeta?: Record<string, { label: string; color: string; position: { x: number; y: number } }>,
  statuses?: Record<string, { status: NodeStatus }>,
): AnyRFNode {
  if (node.type === NOTE_NODE_TYPE) {
    const paramValue = (name: string): unknown =>
      node.params.find((p) => p.name === name)?.value;
    const content = paramValue("content");
    const color = paramValue("color");
    const anchorId = paramValue("anchor_id");
    const groupPos = node.groupId && groupMeta ? groupMeta[node.groupId]?.position : null;
    return {
      id: node.id,
      type: "noteNode",
      position: groupPos ? { x: node.position.x - groupPos.x, y: node.position.y - groupPos.y } : node.position,
      selected,
      parentId: node.groupId && groupMeta?.[node.groupId] ? node.groupId : undefined,
      data: {
        content: typeof content === "string" ? content : "",
        color: typeof color === "string" ? color : "yellow",
        anchorId: typeof anchorId === "string" ? anchorId : null,
      },
    };
  }
  const groupPos = node.groupId && groupMeta ? groupMeta[node.groupId]?.position : null;
  return {
    id: node.id,
    type: "efNode",
    position: groupPos ? { x: node.position.x - groupPos.x, y: node.position.y - groupPos.y } : node.position,
    selected,
    parentId: node.groupId && groupMeta?.[node.groupId] ? node.groupId : undefined,
    data: {
      label: node.label ?? node.type,
      family: family ?? null,
      description: description ?? null,
      ports: node.ports.map((port) => ({
        id: port.id,
        name: port.name,
        direction: port.direction,
        label: port.label ?? null,
      })),
      status: status ?? null,
      results: results ?? null,
    },
  };
}

export function toRFGroupNodes(
  groupMeta: Record<string, { label: string; color: string; position: { x: number; y: number } }> | undefined,
  nodes: Record<string, NodeModel>,
  statuses: Record<string, { status: NodeStatus }> | undefined,
): AnyRFNode[] {
  if (!groupMeta) return [];
  const result: AnyRFNode[] = [];
  for (const [groupId, meta] of Object.entries(groupMeta)) {
    const memberIds = Object.values(nodes)
      .filter((n) => n.groupId === groupId)
      .map((n) => n.id);
    if (memberIds.length < 1) continue;
    const memberCompleteCount = memberIds.filter(
      (id) => statuses?.[id]?.status === "ok" || statuses?.[id]?.status === "cached",
    ).length;
    const memberErrorCount = memberIds.filter(
      (id) => statuses?.[id]?.status === "error",
    ).length;
    result.push({
      id: groupId,
      type: "groupNode",
      position: meta.position,
      selected: false,
      data: {
        groupId,
        label: meta.label,
        color: meta.color,
        memberCount: memberIds.length,
        memberCompleteCount,
        memberErrorCount,
      },
    });
  }
  return result;
}

export function toRFEdge(
  edge: EdgeModel,
  selected: boolean,
  compatible: boolean | null | undefined,
  reason: string | null | undefined,
): RFEdge<EfEdgeData> {
  return {
    id: edge.id,
    type: "efEdge",
    source: edge.source.node_id,
    sourceHandle: edge.source.port_id,
    target: edge.target.node_id,
    targetHandle: edge.target.port_id,
    selected,
    data: { incompatible: compatible === false, reason: reason ?? null },
  };
}
