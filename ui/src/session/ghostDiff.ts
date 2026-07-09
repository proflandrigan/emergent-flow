// Pure ghost-diff computation (Epic 14 Story 4): projects a pending GraphMutation against the
// current canvas model into the set of ghost nodes/edges and badge markers the canvas should
// overlay. No React, no store access -- reuses the SAME nodeFromIR/edgeFromIR mappers ir.ts's
// real fromIR uses, so a ghost node is mapped identically to how the accepted graph would map it.
// ui/src/session/GhostOverlay.tsx (a sibling module) turns this pure result into React Flow
// nodes/edges; wiring the overlay into the live Canvas is a later task.

import type { Node as IRNode } from "../generated/ir";
import type { GraphMutation } from "../generated/mutation";
import { newId } from "../store/ids";
import { edgeFromIR, nodeFromIR } from "../store/ir";
import type { CanvasModel, EdgeModel, NodeModel } from "../store/model";

export interface GhostDiff {
  // Added nodes, ALWAYS with a concrete position: nodes the mutation gave a position keep it;
  // position-less nodes get an auto-layout position placed to the right of the existing graph.
  addedNodes: NodeModel[];
  addedEdges: EdgeModel[];
  removedNodeIds: Set<string>;
  removedEdgeIds: Set<string>;
  // Existing node ids with a pending `set_params` change (badge the affected node, per Story 4).
  paramChangedNodeIds: Set<string>;
}

const AUTO_LAYOUT_X_OFFSET = 260;
const AUTO_LAYOUT_Y_SPACING = 160;

function existingMaxX(model: CanvasModel): number {
  const xs = Object.values(model.nodes).map((n) => n.position.x);
  return xs.length > 0 ? Math.max(...xs) : 0;
}

function isPositionless(node: IRNode): boolean {
  return node.position === undefined || node.position === null;
}

function withStableId<T extends { id: string }>(mapped: T, prefix: string): T {
  return mapped.id ? mapped : { ...mapped, id: newId(prefix) };
}

// Pure: never mutates *model* or *mutation*. Deterministic for a given (model, mutation) pair
// EXCEPT for freshly-minted ids on nodes/edges the mutation left unidentified (newId() is
// random by design, same as the rest of the store) -- callers that need a stable diff across
// re-renders should compute it once and hold the result, not call this on every render.
export function computeGhostDiff(
  model: CanvasModel,
  mutation: GraphMutation,
): GhostDiff {
  const baseX = existingMaxX(model) + AUTO_LAYOUT_X_OFFSET;
  let autoLayoutIndex = 0;

  const addedNodes: NodeModel[] = (mutation.add_nodes ?? []).map((rawNode) => {
    const positionless = isPositionless(rawNode);
    const mapped = withStableId(nodeFromIR(rawNode), "node");
    if (!positionless) {
      return mapped;
    }
    const laidOut: NodeModel = {
      ...mapped,
      position: { x: baseX, y: autoLayoutIndex * AUTO_LAYOUT_Y_SPACING },
    };
    autoLayoutIndex += 1;
    return laidOut;
  });

  const addedEdges: EdgeModel[] = (mutation.add_edges ?? []).map((rawEdge) =>
    withStableId(edgeFromIR(rawEdge), "edge"),
  );

  return {
    addedNodes,
    addedEdges,
    removedNodeIds: new Set(mutation.remove_nodes ?? []),
    removedEdgeIds: new Set(mutation.remove_edges ?? []),
    paramChangedNodeIds: new Set(Object.keys(mutation.set_params ?? {})),
  };
}
