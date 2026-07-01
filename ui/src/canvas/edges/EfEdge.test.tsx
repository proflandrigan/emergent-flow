import { Position, type Edge, type EdgeProps } from "@xyflow/react";
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import type { EfNodeData } from "../nodes/EfNode";
import { EfEdge, type EfEdgeData } from "./EfEdge";

const mockUseNodesData = vi.fn();

vi.mock("@xyflow/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@xyflow/react")>();
  return {
    ...actual,
    useNodesData: (id: string) => mockUseNodesData(id),
  };
});

type EfEdgeType = Edge<EfEdgeData, "efEdge">;

function makeProps(data: EfEdgeData, selected = false): EdgeProps<EfEdgeType> {
  return {
    id: "e1",
    source: "a",
    target: "b",
    sourceX: 0,
    sourceY: 0,
    targetX: 100,
    targetY: 0,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    selected,
    data,
  } as unknown as EdgeProps<EfEdgeType>;
}

describe("EfEdge", () => {
  test("default render uses --border-strong and strokeWidth 1.5", () => {
    mockUseNodesData.mockReturnValue(null);

    const { container } = render(<svg><EfEdge {...makeProps({})} /></svg>);

    const path = container.querySelector(".react-flow__edge-path");
    expect(path).toBeTruthy();
    expect(path!.getAttribute("style")).toContain("var(--border-strong)");
    expect(path!.getAttribute("style")).toContain("1.5");
  });

  test("selected edge tints to source node family color", () => {
    mockUseNodesData.mockReturnValue({
      id: "a",
      type: "efNode",
      data: { label: "A", family: "data", ports: [] } satisfies EfNodeData,
    });

    const { container } = render(<svg><EfEdge {...makeProps({}, true)} /></svg>);

    const path = container.querySelector(".react-flow__edge-path");
    expect(path).toBeTruthy();
    expect(path!.getAttribute("style")).toContain("var(--fam-data)");
  });

  test("incompatible edge renders var(--danger), strokeWidth 2, and title tooltip regardless of selection", () => {
    mockUseNodesData.mockReturnValue({
      id: "a",
      type: "efNode",
      data: { label: "A", family: "data", ports: [] } satisfies EfNodeData,
    });

    const { container } = render(
      <svg>
        <EfEdge {...makeProps({ incompatible: true, reason: "Type mismatch" }, true)} />
      </svg>,
    );

    const path = container.querySelector(".react-flow__edge-path");
    expect(path).toBeTruthy();
    expect(path!.getAttribute("style")).toContain("var(--danger)");
    expect(path!.getAttribute("style")).toContain("2");

    const title = container.querySelector("title");
    expect(title).toBeTruthy();
    expect(title!.textContent).toBe("Type mismatch");
  });

  test("hovered edge tints to source node family color", () => {
    mockUseNodesData.mockReturnValue({
      id: "a",
      type: "efNode",
      data: { label: "A", family: "data", ports: [] } satisfies EfNodeData,
    });

    const { container } = render(<svg><EfEdge {...makeProps({})} /></svg>);

    const g = container.querySelector("g")!;
    const path = container.querySelector(".react-flow__edge-path")!;
    expect(path.getAttribute("style")).toContain("var(--border-strong)");

    fireEvent.mouseEnter(g);

    expect(path.getAttribute("style")).toContain("var(--fam-data)");
  });
});
