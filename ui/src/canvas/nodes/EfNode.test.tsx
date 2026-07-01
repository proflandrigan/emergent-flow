import { ReactFlowProvider, type Node, type NodeProps } from "@xyflow/react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import type { Payload } from "../../store/execution";
import { EfNode, type EfNodeData } from "./EfNode";

const scalarPayload: Payload = { kind: "scalar", value: 42 };

type EfNodeType = Node<EfNodeData, "efNode">;

function makeProps(data: EfNodeData): NodeProps<EfNodeType> {
  return {
    id: "n1",
    data,
    selected: false,
    type: "efNode",
    dragging: false,
    isConnectable: true,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
  } as unknown as NodeProps<EfNodeType>;
}

function renderEfNode(data: EfNodeData) {
  return render(
    <ReactFlowProvider>
      <EfNode {...makeProps(data)} />
    </ReactFlowProvider>,
  );
}

describe("EfNode", () => {
  test("collapsed by default, expands on toggle", async () => {
    const data: EfNodeData = {
      label: "Load CSV",
      ports: [],
      status: "ok",
      results: { out: scalarPayload },
    };

    renderEfNode(data);

    expect(screen.queryByTestId("node-results")).not.toBeInTheDocument();

    const toggle = screen.getByTestId("node-results-toggle");
    fireEvent.click(toggle);

    const panel = screen.getByTestId("node-results");
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveTextContent("42");
  });

  test("no results toggle when there are no results", () => {
    const data: EfNodeData = {
      label: "Load CSV",
      ports: [],
      status: null,
      results: null,
    };

    renderEfNode(data);

    expect(screen.queryByTestId("node-results-toggle")).not.toBeInTheDocument();
  });

  test("at default zoom, port names are visible and results toggle is present", () => {
    const data: EfNodeData = {
      label: "Load CSV",
      ports: [{ id: "in1", name: "input", direction: "in" }],
      status: "ok",
      results: { out: scalarPayload },
    };

    renderEfNode(data);

    expect(screen.getByText("input")).toHaveStyle({ visibility: "visible" });
    expect(screen.getByTestId("node-results-toggle")).toBeInTheDocument();
  });

  test("cached status renders a blue ring and the cached badge", () => {
    const data: EfNodeData = {
      label: "Load CSV",
      ports: [],
      status: "cached",
      results: null,
    };

    renderEfNode(data);

    expect(screen.getByTestId("node-cached-badge")).toBeInTheDocument();
    expect(screen.getByTestId("ef-node").style.boxShadow).toContain("#0288d1");
  });

  test("ok status does not render the cached badge", () => {
    const data: EfNodeData = {
      label: "Load CSV",
      ports: [],
      status: "ok",
      results: null,
    };

    renderEfNode(data);

    expect(screen.queryByTestId("node-cached-badge")).not.toBeInTheDocument();
  });

  test("error status renders a red ring with glow", () => {
    const data: EfNodeData = {
      label: "Load CSV",
      ports: [],
      status: "error",
      results: null,
    };

    renderEfNode(data);

    expect(screen.getByTestId("ef-node").style.boxShadow).toContain("#c00");
  });

  test("skipped status applies reduced opacity", () => {
    const data: EfNodeData = {
      label: "Load CSV",
      ports: [],
      status: "skipped",
      results: null,
    };

    renderEfNode(data);

    expect(screen.getByTestId("ef-node")).toHaveStyle({ opacity: 0.6 });
  });

  test("running status applies the ef-node--running class", () => {
    const data: EfNodeData = {
      label: "Load CSV",
      ports: [],
      status: "running",
      results: null,
    };

    renderEfNode(data);

    expect(screen.getByTestId("ef-node")).toHaveClass("ef-node--running");
  });
});
