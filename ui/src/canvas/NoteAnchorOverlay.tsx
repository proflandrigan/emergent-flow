// Overlay that draws a dashed leader-line/callout connector from each anchored note to its
// anchor target (a node, or an edge's target node). This is intentionally NOT a React Flow
// Edge -- notes have zero ports/Handles (see NoteNode.tsx), so there is nothing for a real
// Edge to attach to. Rendered via ViewportPortal so the lines stay in flow coordinate space
// and pan/zoom in sync with every node.

import { useMemo } from "react";
import { ViewportPortal } from "@xyflow/react";

import { useGraphStore } from "../store/graphStore";

const NOTE_NODE_TYPE = "notes.markdown";

// Approximate visual centers used as leader-line endpoints. Both EfNode and NoteNode vary in
// actual rendered height with their content/ports, and measuring that precisely would require
// DOM refs and post-render timing; a leader-line/callout only needs to originate "near" its
// target, not at a pixel-perfect border, so a fixed offset (half of each node type's fixed
// CSS width, plus a reasonable fixed vertical guess) is an intentional, acceptable v1
// simplification -- NOT a bug to "fix" by adding measurement logic.
const EF_NODE_CENTER_OFFSET = { x: 88, y: 40 };
const NOTE_NODE_CENTER_OFFSET = { x: 110, y: 40 };

interface Point {
  x: number;
  y: number;
}

function approximateCenter(position: Point, nodeType: string): Point {
  const offset = nodeType === NOTE_NODE_TYPE ? NOTE_NODE_CENTER_OFFSET : EF_NODE_CENTER_OFFSET;
  return { x: position.x + offset.x, y: position.y + offset.y };
}

interface LeaderLine {
  id: string;
  from: Point;
  to: Point;
}

export function NoteAnchorOverlay(): JSX.Element {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);

  const lines = useMemo<LeaderLine[]>(() => {
    const result: LeaderLine[] = [];
    for (const node of Object.values(nodes)) {
      if (node.type !== NOTE_NODE_TYPE) {
        continue;
      }
      const anchorId = node.params.find((p) => p.name === "anchor_id")?.value;
      if (typeof anchorId !== "string" || anchorId.length === 0) {
        continue;
      }

      let targetNode = nodes[anchorId];
      if (!targetNode) {
        const edge = edges[anchorId];
        if (edge) {
          targetNode = nodes[edge.target.node_id];
        }
      }
      if (!targetNode) {
        continue;
      }

      result.push({
        id: node.id,
        from: approximateCenter(node.position, node.type),
        to: approximateCenter(targetNode.position, targetNode.type),
      });
    }
    return result;
  }, [nodes, edges]);

  return (
    <ViewportPortal>
      <svg
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          overflow: "visible",
          pointerEvents: "none",
        }}
        data-testid="note-anchor-overlay"
      >
        {lines.map((line) => (
          <line
            key={line.id}
            data-testid="note-anchor-line"
            x1={line.from.x}
            y1={line.from.y}
            x2={line.to.x}
            y2={line.to.y}
            stroke="var(--fam-notes)"
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
        ))}
      </svg>
    </ViewportPortal>
  );
}

export default NoteAnchorOverlay;
