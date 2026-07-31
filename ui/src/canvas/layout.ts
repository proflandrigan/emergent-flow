// Canvas-side layout helpers (issue #91: agent-proposed node batches, or any
// bulk graph load, must never render with multiple nodes silently stacked on
// the exact same coordinates). Pure functions only -- no store/React
// dependency here so they stay trivially unit-testable and reusable from
// both `loadIR` and a future "Auto-layout / tidy" action.

import type { EdgeModel, NodeModel } from "../store/model";

const CASCADE_STEP = 48;

function posKey(position: { x: number; y: number }): string {
  return `${Math.round(position.x)}:${Math.round(position.y)}`;
}

// Groups nodes by their rounded (x, y) so near-identical floats (e.g. two
// nodes both left at the IR's `Position()` default) are treated as one
// collision group, then nudges every node in a group after the first by a
// fixed cascade offset. Nodes that don't collide with anything are returned
// unchanged (same object reference), so callers that diff for re-render
// don't see spurious churn.
//
// The cascade offset for a group member is checked against every occupied
// spot in the graph (pre-existing nodes AND spots already claimed by earlier
// cascaded members), not just the other members of its own group -- otherwise
// a node cascaded out of one collision could land exactly on an unrelated
// node (or another group's cascaded node) elsewhere on the canvas.
export function separateOverlappingNodes(
  nodes: Record<string, NodeModel>,
): Record<string, NodeModel> {
  const groups = new Map<string, string[]>();
  const taken = new Set<string>();
  for (const node of Object.values(nodes)) {
    const key = posKey(node.position);
    const group = groups.get(key);
    if (group) {
      group.push(node.id);
    } else {
      groups.set(key, [node.id]);
    }
    taken.add(key);
  }

  const result: Record<string, NodeModel> = { ...nodes };
  for (const ids of groups.values()) {
    if (ids.length < 2) {
      continue;
    }
    ids.forEach((id, index) => {
      if (index === 0) {
        return; // first node in the group keeps its original spot
      }
      const existing = nodes[id];
      let step = index;
      let position = {
        x: existing.position.x + CASCADE_STEP * step,
        y: existing.position.y + CASCADE_STEP * step,
      };
      while (taken.has(posKey(position))) {
        step += 1;
        position = {
          x: existing.position.x + CASCADE_STEP * step,
          y: existing.position.y + CASCADE_STEP * step,
        };
      }
      taken.add(posKey(position));
      result[id] = { ...existing, position };
    });
  }
  return result;
}

const COLUMN_WIDTH = 260;
const ROW_HEIGHT = 140;

const GROUP_NODE_TYPE = "layout.group";
const GROUP_MEMBER_COLUMNS = 2;
export const GROUP_MEMBER_COLUMN_WIDTH = 220;
export const GROUP_MEMBER_ROW_HEIGHT = 100;
const GROUP_PADDING = 40;

export function layeredLayout(
  nodes: Record<string, NodeModel>,
  edges: Record<string, EdgeModel>,
): Record<string, NodeModel> {
  const ids = Object.keys(nodes);
  const layer: Record<string, number> = {};
  for (const id of ids) {
    layer[id] = 0;
  }

  for (let i = 0; i < ids.length; i++) {
    let changed = false;
    for (const edge of Object.values(edges)) {
      const src = edge.source.node_id;
      const dst = edge.target.node_id;
      if (!(src in layer) || !(dst in layer)) {
        continue;
      }
      if (layer[dst] < layer[src] + 1) {
        layer[dst] = layer[src] + 1;
        changed = true;
      }
    }
    if (!changed) {
      break;
    }
  }

  const rowCounters = new Map<number, number>();
  const result: Record<string, NodeModel> = {};
  for (const id of ids) {
    const l = layer[id];
    const row = rowCounters.get(l) ?? 0;
    rowCounters.set(l, row + 1);
    result[id] = {
      ...nodes[id],
      position: { x: l * COLUMN_WIDTH, y: row * ROW_HEIGHT },
    };
  }

  // A group is a layout unit (#117 stage 1): re-pack each group's members into a compact
  // cluster anchored at the centroid of their individually-computed positions above, rather
  // than leaving them scattered across whichever columns their own edges happened to place
  // them in. A node whose `groupId` doesn't resolve to a real `layout.group` node in this
  // graph (stale/dangling) is left at its individually-computed position.
  const membersByGroup = new Map<string, string[]>();
  for (const id of ids) {
    const groupId = nodes[id].groupId;
    if (!groupId) {
      continue;
    }
    const bucket = membersByGroup.get(groupId);
    if (bucket) {
      bucket.push(id);
    } else {
      membersByGroup.set(groupId, [id]);
    }
  }

  for (const [groupId, memberIds] of membersByGroup) {
    const groupNode = result[groupId];
    if (!groupNode || groupNode.type !== GROUP_NODE_TYPE) {
      continue;
    }
    const centroidX =
      memberIds.reduce((sum, id) => sum + result[id].position.x, 0) / memberIds.length;
    const centroidY =
      memberIds.reduce((sum, id) => sum + result[id].position.y, 0) / memberIds.length;
    memberIds.forEach((id, index) => {
      const col = index % GROUP_MEMBER_COLUMNS;
      const row = Math.floor(index / GROUP_MEMBER_COLUMNS);
      result[id] = {
        ...result[id],
        position: {
          x: centroidX + col * GROUP_MEMBER_COLUMN_WIDTH,
          y: centroidY + row * GROUP_MEMBER_ROW_HEIGHT,
        },
      };
    });
    result[groupId] = {
      ...groupNode,
      position: { x: centroidX - GROUP_PADDING, y: centroidY - GROUP_PADDING },
    };
  }

  return result;
}
