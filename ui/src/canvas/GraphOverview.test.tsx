import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { Edge as RFEdge, Node as RFNode } from "@xyflow/react";

import { EfEdge } from "./edges/EfEdge";
import { EfNode } from "./nodes/EfNode";
import { GraphOverview } from "./GraphOverview";

const nodeTypes = { efNode: EfNode };
const edgeTypes = { efEdge: EfEdge };
const nodes: RFNode[] = [
  {
    id: "n1",
    type: "efNode",
    position: { x: 0, y: 0 },
    data: { label: "Load CSV", family: "data", ports: [] },
  } as RFNode,
];
const edges: RFEdge[] = [];
const onNavigate = vi.fn();
const onClose = vi.fn();

afterEach(() => {
  vi.clearAllMocks();
});

describe("GraphOverview", () => {
  test("renders the overview modal and its react-flow viewport", () => {
    render(
      <GraphOverview
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNavigate={onNavigate}
        onClose={onClose}
      />,
    );

    expect(document.querySelector(".react-flow")).not.toBeNull();
    expect(screen.getByTestId("overlay-modal-close")).toBeInTheDocument();
  });

  test("clicking a node calls onNavigate with the node id", () => {
    render(
      <GraphOverview
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNavigate={onNavigate}
        onClose={onClose}
      />,
    );

    const nodeElement = document.querySelector(".react-flow__node");
    expect(nodeElement).not.toBeNull();

    fireEvent.click(nodeElement!);

    expect(onNavigate).toHaveBeenCalledWith("n1");
  });

  test("clicking the overlay close button calls onClose", () => {
    render(
      <GraphOverview
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNavigate={onNavigate}
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByTestId("overlay-modal-close"));

    expect(onClose).toHaveBeenCalled();
  });
});