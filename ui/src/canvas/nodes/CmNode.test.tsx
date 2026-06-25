import { ReactFlowProvider, type Node, type NodeProps } from "@xyflow/react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import type { Payload } from "../../store/execution";
import { CmNode, type CmNodeData } from "./CmNode";

const scalarPayload: Payload = { kind: "scalar", value: 42 };

type CmNodeType = Node<CmNodeData, "cmNode">;

function makeProps(data: CmNodeData): NodeProps<CmNodeType> {
  return {
    id: "n1",
    data,
    selected: false,
    type: "cmNode",
    dragging: false,
    isConnectable: true,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
  } as unknown as NodeProps<CmNodeType>;
}

function renderCmNode(data: CmNodeData) {
  return render(
    <ReactFlowProvider>
      <CmNode {...makeProps(data)} />
    </ReactFlowProvider>,
  );
}

describe("CmNode", () => {
  test("collapsed by default, expands on toggle", async () => {
    const data: CmNodeData = {
      label: "Load CSV",
      ports: [],
      status: "ok",
      results: { out: scalarPayload },
    };

    renderCmNode(data);

    expect(screen.queryByTestId("node-results")).not.toBeInTheDocument();

    const toggle = screen.getByTestId("node-results-toggle");
    fireEvent.click(toggle);

    const panel = screen.getByTestId("node-results");
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveTextContent("42");
  });

  test("no results toggle when there are no results", () => {
    const data: CmNodeData = {
      label: "Load CSV",
      ports: [],
      status: null,
      results: null,
    };

    renderCmNode(data);

    expect(screen.queryByTestId("node-results-toggle")).not.toBeInTheDocument();
  });

  test("at default zoom, port names are visible and results toggle is present", () => {
    const data: CmNodeData = {
      label: "Load CSV",
      ports: [{ id: "in1", name: "input", direction: "in" }],
      status: "ok",
      results: { out: scalarPayload },
    };

    renderCmNode(data);

    expect(screen.getByText("input")).toHaveStyle({ visibility: "visible" });
    expect(screen.getByTestId("node-results-toggle")).toBeInTheDocument();
  });
});
