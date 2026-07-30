import { ReactFlowProvider, type Node, type NodeProps } from "@xyflow/react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import type { CatalogNode } from "../../catalog/types";
import catalog from "../../generated/catalog.json";
import { useGraphStore } from "../../store/graphStore";
import { GroupNode, type GroupNodeData } from "./GroupNode";

const catalogNodes = (catalog as unknown as { nodes: CatalogNode[] }).nodes;

function requireCatalogNode(type: string): CatalogNode {
  const node = catalogNodes.find((entry) => entry.type === type);
  if (!node) {
    throw new Error(`expected catalog fixture \`${type}\` to exist`);
  }
  return node;
}

const groupNode = requireCatalogNode("layout.group");

type GroupNodeType = Node<GroupNodeData, "groupNode">;

function makeProps(id: string, data: GroupNodeData): NodeProps<GroupNodeType> {
  return {
    id,
    data,
    selected: false,
    type: "groupNode",
    dragging: false,
    isConnectable: true,
    zIndex: 0,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
  } as unknown as NodeProps<GroupNodeType>;
}

function renderGroupNode(id: string, data: GroupNodeData) {
  return render(
    <ReactFlowProvider>
      <GroupNode {...makeProps(id, data)} />
    </ReactFlowProvider>,
  );
}

beforeEach(() => {
  useGraphStore.getState().reset();
});

describe("GroupNode", () => {
  test("renders the label from data.label", () => {
    renderGroupNode("g1", { label: "My Group", color: "slate" });

    expect(screen.getByTestId("group-node-label")).toHaveTextContent("My Group");
  });

  test("color param controls the background swatch", () => {
    renderGroupNode("g1", { label: "Test", color: "blue" });

    const element = screen.getByTestId("group-node");
    expect(element.style.background).toBe("rgba(219, 234, 254, 0.333)");
  });

  test("unknown color falls back to the slate swatch", () => {
    renderGroupNode("g1", { label: "Test", color: "not-a-real-color" });

    const element = screen.getByTestId("group-node");
    expect(element.style.background).toBe("rgba(226, 232, 240, 0.333)");
  });

  test("double-click header enters edit mode; blur commits the new label via setParam", () => {
    const nodeId = useGraphStore.getState().addNodeFromSpec(groupNode, { x: 0, y: 0 });
    useGraphStore.getState().setParam(nodeId, "label", "original label");

    renderGroupNode(nodeId, { label: "original label", color: "slate" });

    fireEvent.doubleClick(screen.getByTestId("group-node-header"));

    const editor = screen.getByTestId("group-node-label-editor");
    fireEvent.change(editor, { target: { value: "new label" } });
    fireEvent.blur(editor);

    expect(screen.queryByTestId("group-node-label-editor")).not.toBeInTheDocument();
    const stored = useGraphStore
      .getState()
      .nodes[nodeId].params.find((p) => p.name === "label");
    expect(stored?.value).toBe("new label");
  });

  test("Escape cancels the edit without committing", () => {
    const nodeId = useGraphStore.getState().addNodeFromSpec(groupNode, { x: 0, y: 0 });
    useGraphStore.getState().setParam(nodeId, "label", "original label");

    renderGroupNode(nodeId, { label: "original label", color: "slate" });

    fireEvent.doubleClick(screen.getByTestId("group-node-header"));
    const editor = screen.getByTestId("group-node-label-editor");
    fireEvent.change(editor, { target: { value: "throwaway edit" } });
    fireEvent.keyDown(editor, { key: "Escape" });

    expect(screen.queryByTestId("group-node-label-editor")).not.toBeInTheDocument();
    const stored = useGraphStore
      .getState()
      .nodes[nodeId].params.find((p) => p.name === "label");
    expect(stored?.value).toBe("original label");
  });
});
