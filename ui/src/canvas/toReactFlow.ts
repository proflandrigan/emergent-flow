// Pure derivation helpers: map store `NodeModel`/`EdgeModel` records to React Flow's
// `Node`/`Edge` shapes. The store stays the single source of truth for IR data (ADR 0014
// Decision 3); these functions never mutate anything, they only project.

import type { Edge as RFEdge, Node as RFNode } from "@xyflow/react";

import type { EdgeModel, NodeModel } from "../store/model";
import type { NodeStatus, Payload } from "../store/execution";
import type { EfEdgeData } from "./edges/EfEdge";
import type { EfNodeData } from "./nodes/EfNode";
import type { NoteNodeData } from "./nodes/NoteNode";
import type { GroupNodeData } from "./nodes/GroupNode";

const NOTE_NODE_TYPE = "notes.markdown";
const GROUP_NODE_TYPE = "layout.group";

// A group container auto-sizes to fit its members plus this padding on every side. The
// footprint constants are a rough per-node bounding box (matches EfNode's typical rendered
// size) used only to size the container BEFORE React Flow has measured real node sizes --
// good enough for the container to visually contain its members, not pixel-exact.
export const GROUP_PADDING = 40;
const MIN_GROUP_WIDTH = 240;
const MIN_GROUP_HEIGHT = 160;
const NODE_FOOTPRINT_WIDTH = 200;
const NODE_FOOTPRINT_HEIGHT = 100;

export interface GroupBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

// The group's absolute top-left origin and size, derived purely from its members' current
// absolute positions. Never called with an empty array by this module's own callers (they all
// guard on `members.length > 0` first) but is defensive here too since Math.min(...[]) is
// -Infinity in JS.
export function computeGroupBounds(members: NodeModel[]): GroupBounds {
  if (members.length === 0) {
    return { x: 0, y: 0, width: MIN_GROUP_WIDTH, height: MIN_GROUP_HEIGHT };
  }
  const minX = Math.min(...members.map((m) => m.position.x));
  const minY = Math.min(...members.map((m) => m.position.y));
  const maxX = Math.max(...members.map((m) => m.position.x + NODE_FOOTPRINT_WIDTH));
  const maxY = Math.max(...members.map((m) => m.position.y + NODE_FOOTPRINT_HEIGHT));
  return {
    x: minX - GROUP_PADDING,
    y: minY - GROUP_PADDING,
    width: Math.max(MIN_GROUP_WIDTH, maxX - minX + GROUP_PADDING * 2),
    height: Math.max(MIN_GROUP_HEIGHT, maxY - minY + GROUP_PADDING * 2),
  };
}

// Groups every node that carries a `groupId` by that id. Nodes with no `groupId` are omitted.
export function membersByGroupId(nodeModels: NodeModel[]): Map<string, NodeModel[]> {
  const map = new Map<string, NodeModel[]>();
  for (const model of nodeModels) {
    if (!model.groupId) {
      continue;
    }
    const bucket = map.get(model.groupId);
    if (bucket) {
      bucket.push(model);
    } else {
      map.set(model.groupId, [model]);
    }
  }
  return map;
}

// Post-processes the already-built `rfNodes` (one call to `toRFNode` per node, unchanged) to
// wire up React Flow's parent/child nesting:
//   - a `layout.group` node with members gets its rendered position/size overridden to the
//     bounding box computed from its members' CURRENT absolute positions, and a negative
//     zIndex so its box paints behind its (later-rendered) members;
//   - a member node (non-empty `groupId` pointing at a real `layout.group` node) gets
//     `parentId`/`extent: "parent"` and its position converted from absolute to
//     parent-relative (React Flow requires a child's `position` to be relative to its parent).
// Nodes with no group relationship, or a `groupId` that doesn't resolve to a `layout.group`
// node (stale/dangling), pass through unchanged.
export function applyGroupNesting(
  nodeModels: NodeModel[],
  rfNodes: RFNode[],
): RFNode[] {
  const modelById = new Map(nodeModels.map((m) => [m.id, m]));
  const grouped = membersByGroupId(nodeModels);

  const mapped = rfNodes.map((rfNode) => {
    const model = modelById.get(rfNode.id);
    if (!model) {
      return rfNode;
    }

    if (model.type === GROUP_NODE_TYPE) {
      const members = grouped.get(model.id);
      if (!members || members.length === 0) {
        return rfNode;
      }
      const bounds = computeGroupBounds(members);
      return {
        ...rfNode,
        position: { x: bounds.x, y: bounds.y },
        style: { ...(rfNode.style ?? {}), width: bounds.width, height: bounds.height },
        zIndex: -1,
      };
    }

    if (model.groupId) {
      const groupModel = modelById.get(model.groupId);
      const members = grouped.get(model.groupId);
      if (!groupModel || groupModel.type !== GROUP_NODE_TYPE || !members || members.length === 0) {
        return rfNode;
      }
      const bounds = computeGroupBounds(members);
      return {
        ...rfNode,
        parentId: model.groupId,
        extent: "parent" as const,
        position: {
          x: model.position.x - bounds.x,
          y: model.position.y - bounds.y,
        },
      };
    }

    return rfNode;
  });

  // React Flow requires a parent node to appear before its children in the array -- our
  // `mapped` order follows `nodeModels`' insertion order (a group is created after its
  // members already exist), which violates that. Partition group nodes to the front,
  // preserving relative order within each partition, rather than sorting -- there is only
  // one level of nesting today (groups don't nest inside groups).
  const groups = mapped.filter((n) => modelById.get(n.id)?.type === GROUP_NODE_TYPE);
  const others = mapped.filter((n) => modelById.get(n.id)?.type !== GROUP_NODE_TYPE);
  return [...groups, ...others];
}

// Inverse of the position half of `applyGroupNesting`'s member branch: React Flow reports a
// dragged child's new position in parent-relative coordinates, but the store only ever holds
// absolute positions (ADR 0014 Decision 3). Converts back before calling `moveNode`. Returns
// `relativePosition` unchanged for a node with no group, or a stale/dangling `groupId`.
export function toAbsolutePosition(
  nodeModels: NodeModel[],
  nodeId: string,
  relativePosition: { x: number; y: number },
): { x: number; y: number } {
  const modelById = new Map(nodeModels.map((m) => [m.id, m]));
  const model = modelById.get(nodeId);
  if (!model?.groupId) {
    return relativePosition;
  }
  const groupModel = modelById.get(model.groupId);
  if (!groupModel || groupModel.type !== GROUP_NODE_TYPE) {
    return relativePosition;
  }
  const members = membersByGroupId(nodeModels).get(model.groupId);
  if (!members || members.length === 0) {
    return relativePosition;
  }
  const bounds = computeGroupBounds(members);
  return { x: relativePosition.x + bounds.x, y: relativePosition.y + bounds.y };
}

export function toRFNode(
  node: NodeModel,
  selected: boolean,
  status: NodeStatus | null | undefined,
  results: Record<string, Payload> | null | undefined,
  family: string | null | undefined,
  description: string | null | undefined,
): RFNode<EfNodeData> | RFNode<NoteNodeData> | RFNode<GroupNodeData> {
  if (node.type === GROUP_NODE_TYPE) {
    const paramValue = (name: string): unknown =>
      node.params.find((p) => p.name === name)?.value;
    const label = paramValue("label");
    const color = paramValue("color");
    return {
      id: node.id,
      type: "groupNode",
      position: node.position,
      selected,
      data: {
        label: typeof label === "string" ? label : "Group",
        color: typeof color === "string" ? color : "slate",
      },
    };
  }
  if (node.type === NOTE_NODE_TYPE) {
    const paramValue = (name: string): unknown =>
      node.params.find((p) => p.name === name)?.value;
    const content = paramValue("content");
    const color = paramValue("color");
    const anchorId = paramValue("anchor_id");
    return {
      id: node.id,
      type: "noteNode",
      position: node.position,
      selected,
      data: {
        content: typeof content === "string" ? content : "",
        color: typeof color === "string" ? color : "yellow",
        anchorId: typeof anchorId === "string" ? anchorId : null,
      },
    };
  }
  return {
    id: node.id,
    type: "efNode",
    position: node.position,
    selected,
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
