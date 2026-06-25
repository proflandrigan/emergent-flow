// Pure derivation helpers: map store `NodeModel`/`EdgeModel` records to React Flow's
// `Node`/`Edge` shapes. The store stays the single source of truth for IR data (ADR 0014
// Decision 3); these functions never mutate anything, they only project.

import type { Edge as RFEdge, Node as RFNode } from "@xyflow/react";

import type { EdgeModel, NodeModel } from "../store/model";
import type { NodeStatus, Payload } from "../store/execution";
import type { EfEdgeData } from "./edges/EfEdge";
import type { EfNodeData } from "./nodes/EfNode";

export function toRFNode(
  node: NodeModel,
  selected: boolean,
  status: NodeStatus | null | undefined,
  results: Record<string, Payload> | null | undefined,
): RFNode<EfNodeData> {
  return {
    id: node.id,
    type: "efNode",
    position: node.position,
    selected,
    data: {
      label: node.label ?? node.type,
      ports: node.ports.map((port) => ({
        id: port.id,
        name: port.name,
        direction: port.direction,
      })),
      status: status ?? null,
      results: results ?? null,
    },
  };
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
