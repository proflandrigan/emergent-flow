// Pure derivation helpers: map store `NodeModel`/`EdgeModel` records to React Flow's
// `Node`/`Edge` shapes. The store stays the single source of truth for IR data (ADR 0014
// Decision 3); these functions never mutate anything, they only project.

import type { Edge as RFEdge, Node as RFNode } from "@xyflow/react";

import type { EdgeModel, NodeModel } from "../store/model";
import type { CmNodeData } from "./nodes/CmNode";

export function toRFNode(
  node: NodeModel,
  selected: boolean,
): RFNode<CmNodeData> {
  return {
    id: node.id,
    type: "cmNode",
    position: node.position,
    selected,
    data: {
      label: node.label ?? node.type,
      ports: node.ports.map((port) => ({
        id: port.id,
        name: port.name,
        direction: port.direction,
      })),
    },
  };
}

export function toRFEdge(edge: EdgeModel, selected: boolean): RFEdge {
  return {
    id: edge.id,
    source: edge.source.node_id,
    sourceHandle: edge.source.port_id,
    target: edge.target.node_id,
    targetHandle: edge.target.port_id,
    selected,
  };
}
