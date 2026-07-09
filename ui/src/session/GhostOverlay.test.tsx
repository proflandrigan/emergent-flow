import { ReactFlowProvider, type Node, type NodeProps } from "@xyflow/react";
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import type { CanvasModel } from "../store/model";
import type { GhostDiff } from "./ghostDiff";
import {
  GhostBadge,
  GhostEdge,
  GhostNode,
  toGhostRFEdges,
  toGhostRFNodes,
  type GhostBadgeData,
  type GhostNodeData,
} from "./GhostOverlay";

function emptyDiff(overrides: Partial<GhostDiff> = {}): GhostDiff {
  return {
    addedNodes: [],
    addedEdges: [],
    removedNodeIds: new Set(),
    removedEdgeIds: new Set(),
    paramChangedNodeIds: new Set(),
    ...overrides,
  };
}

function emptyModel(): CanvasModel {
  return { paradigm: "functional", nodes: {}, edges: {} };
}

describe("GhostNode", () => {
  test("renders the label, a proposed marker, and one Handle per port", () => {
    const data: GhostNodeData = {
      label: "Describe",
      ports: [
        { id: "p-in", name: "df", direction: "in" },
        { id: "p-out", name: "summary", direction: "out" },
      ],
    };
    render(
      <ReactFlowProvider>
        <GhostNode
          {...({
            id: "n1",
            data,
            selected: false,
            type: "efGhostNode",
            dragging: false,
            isConnectable: true,
            zIndex: 0,
            positionAbsoluteX: 0,
            positionAbsoluteY: 0,
          } as unknown as NodeProps<Node<GhostNodeData, "efGhostNode">>)}
        />
      </ReactFlowProvider>,
    );

    expect(screen.getByTestId("ef-ghost-node")).toBeInTheDocument();
    expect(screen.getByText("Describe")).toBeInTheDocument();
    expect(screen.getByText("proposed")).toBeInTheDocument();
  });
});

describe("GhostBadge", () => {
  test("renders its label", () => {
    const data: GhostBadgeData = { label: "params" };
    render(
      <GhostBadge
        {...({
          id: "b1",
          data,
          selected: false,
          type: "efGhostBadge",
          dragging: false,
          isConnectable: false,
          zIndex: 0,
          positionAbsoluteX: 0,
          positionAbsoluteY: 0,
        } as unknown as NodeProps<Node<GhostBadgeData, "efGhostBadge">>)}
      />,
    );

    expect(screen.getByTestId("ef-ghost-badge")).toHaveTextContent("params");
  });
});

describe("GhostEdge", () => {
  test("renders a dashed path", () => {
    const { container } = render(
      <svg>
        <GhostEdge
          {...({
            id: "e1",
            source: "a",
            target: "b",
            sourceX: 0,
            sourceY: 0,
            targetX: 100,
            targetY: 0,
            sourcePosition: "right",
            targetPosition: "left",
          } as unknown as Parameters<typeof GhostEdge>[0])}
        />
      </svg>,
    );

    const path = container.querySelector(".react-flow__edge-path");
    expect(path).toBeTruthy();
    expect(path!.getAttribute("style")).toContain("4 3");
  });
});

describe("toGhostRFNodes", () => {
  test("maps added nodes to non-draggable, non-selectable efGhostNode entries", () => {
    const diff = emptyDiff({
      addedNodes: [
        {
          id: "n1",
          type: "stats.describe",
          paradigm: "functional",
          params: [],
          ports: [],
          position: { x: 10, y: 20 },
        },
      ],
    });

    const rfNodes = toGhostRFNodes(diff, emptyModel());

    expect(rfNodes).toHaveLength(1);
    expect(rfNodes[0]).toMatchObject({
      id: "n1",
      type: "efGhostNode",
      position: { x: 10, y: 20 },
      selectable: false,
      draggable: false,
    });
  });

  test("adds a params badge near an existing node with a pending param change", () => {
    const model: CanvasModel = {
      paradigm: "functional",
      nodes: {
        n1: {
          id: "n1",
          type: "a",
          paradigm: "functional",
          params: [],
          ports: [],
          position: { x: 0, y: 0 },
        },
      },
      edges: {},
    };
    const diff = emptyDiff({ paramChangedNodeIds: new Set(["n1"]) });

    const rfNodes = toGhostRFNodes(diff, model);

    expect(rfNodes).toHaveLength(1);
    expect(rfNodes[0]).toMatchObject({
      id: "ghost-badge-params:n1",
      type: "efGhostBadge",
    });
  });

  test("skips a badge when its target node id is not in the model", () => {
    const diff = emptyDiff({ paramChangedNodeIds: new Set(["missing"]) });

    const rfNodes = toGhostRFNodes(diff, emptyModel());

    expect(rfNodes).toHaveLength(0);
  });
});

describe("toGhostRFEdges", () => {
  test("maps added edges to efGhostEdge entries", () => {
    const diff = emptyDiff({
      addedEdges: [
        {
          id: "e1",
          source: { node_id: "n1", port_id: "p1" },
          target: { node_id: "n2", port_id: "p2" },
        },
      ],
    });

    const rfEdges = toGhostRFEdges(diff);

    expect(rfEdges).toEqual([
      {
        id: "e1",
        type: "efGhostEdge",
        source: "n1",
        sourceHandle: "p1",
        target: "n2",
        targetHandle: "p2",
        selectable: false,
      },
    ]);
  });
});
