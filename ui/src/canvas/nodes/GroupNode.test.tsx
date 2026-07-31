import { ReactFlowProvider, type Node, type NodeProps } from "@xyflow/react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import type { CatalogNode } from "../../catalog/types";
import catalog from "../../generated/catalog.json";
import { useCollapseStore } from "../../store/collapseStore";
import { useExecutionStore } from "../../store/executionStore";
import { useGraphStore } from "../../store/graphStore";
import { aggregateGroupStatus, GroupNode, type GroupNodeData } from "./GroupNode";

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
  useCollapseStore.getState().clear();
  useExecutionStore.getState().clear();
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

  test("clicking the collapse toggle shows the summary and hides the empty body", () => {
    const groupId = useGraphStore.getState().addNodeFromSpec(groupNode, { x: 0, y: 0 });
    renderGroupNode(groupId, { label: "Test", color: "slate" });

    expect(screen.getByTestId("group-node-body")).toBeInTheDocument();
    expect(screen.queryByTestId("group-node-summary")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("group-node-collapse-toggle"));

    expect(screen.queryByTestId("group-node-body")).not.toBeInTheDocument();
    expect(screen.getByTestId("group-node-summary")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("group-node-collapse-toggle"));

    expect(screen.getByTestId("group-node-body")).toBeInTheDocument();
    expect(screen.queryByTestId("group-node-summary")).not.toBeInTheDocument();
  });

  test("the summary shows the correct member count for 0, 1, and 2+ members", () => {
    const groupId = useGraphStore.getState().addNodeFromSpec(groupNode, { x: 0, y: 0 });
    renderGroupNode(groupId, { label: "Test", color: "slate" });

    fireEvent.click(screen.getByTestId("group-node-collapse-toggle"));
    expect(screen.getByTestId("group-node-member-count")).toHaveTextContent("0 nodes");

    let node1 = "";
    act(() => {
      node1 = useGraphStore.getState().addNodeFromSpec(groupNode, { x: 100, y: 0 });
      useGraphStore.setState((state) => ({
        nodes: {
          ...state.nodes,
          [node1]: { ...state.nodes[node1], groupId },
        },
      }));
    });

    expect(screen.getByTestId("group-node-member-count")).toHaveTextContent("1 node");

    let node2 = "";
    act(() => {
      node2 = useGraphStore.getState().addNodeFromSpec(groupNode, { x: 200, y: 0 });
      useGraphStore.setState((state) => ({
        nodes: {
          ...state.nodes,
          [node2]: { ...state.nodes[node2], groupId },
        },
      }));
    });

    expect(screen.getByTestId("group-node-member-count")).toHaveTextContent("2 nodes");
  });

  test("collapsing a group whose members include one with status error shows a red status dot", () => {
    const groupId = useGraphStore.getState().addNodeFromSpec(groupNode, { x: 0, y: 0 });
    const memberId = useGraphStore.getState().addNodeFromSpec(groupNode, { x: 100, y: 0 });
    useGraphStore.setState((state) => ({
      nodes: {
        ...state.nodes,
        [memberId]: { ...state.nodes[memberId], groupId },
      },
    }));

    useExecutionStore.getState().setNodeError(memberId, "boom");

    renderGroupNode(groupId, { label: "Test", color: "slate" });
    fireEvent.click(screen.getByTestId("group-node-collapse-toggle"));

    const dot = screen.getByTestId("group-node-status-dot");
    expect(dot.style.background).toBe("var(--danger)");
  });

  test("when collapsed, the rendered output includes target and source handles", () => {
    const groupId = useGraphStore.getState().addNodeFromSpec(groupNode, { x: 0, y: 0 });
    const { container } = renderGroupNode(groupId, { label: "Test", color: "slate" });

    fireEvent.click(screen.getByTestId("group-node-collapse-toggle"));

    const groupInHandle = container.querySelector('[data-handleid="group-in"]');
    const groupOutHandle = container.querySelector('[data-handleid="group-out"]');
    expect(groupInHandle).toBeInTheDocument();
    expect(groupOutHandle).toBeInTheDocument();
  });

  test("when expanded, the rendered output does not include the handles", () => {
    const groupId = useGraphStore.getState().addNodeFromSpec(groupNode, { x: 0, y: 0 });
    const { container } = renderGroupNode(groupId, { label: "Test", color: "slate" });

    const groupInHandle = container.querySelector('[data-handleid="group-in"]');
    const groupOutHandle = container.querySelector('[data-handleid="group-out"]');
    expect(groupInHandle).not.toBeInTheDocument();
    expect(groupOutHandle).not.toBeInTheDocument();
  });
});

describe("aggregateGroupStatus", () => {
  test("empty array returns null", () => {
    expect(aggregateGroupStatus([])).toBe(null);
  });

  test("any error present returns error", () => {
    expect(aggregateGroupStatus(["ok", "error", "cached"])).toBe("error");
    expect(aggregateGroupStatus(["error"])).toBe("error");
  });

  test("no error but any running returns running", () => {
    expect(aggregateGroupStatus(["ok", "running", "cached"])).toBe("running");
    expect(aggregateGroupStatus(["running"])).toBe("running");
  });

  test("all cached returns cached", () => {
    expect(aggregateGroupStatus(["cached", "cached"])).toBe("cached");
  });

  test("all ok or cached returns ok", () => {
    expect(aggregateGroupStatus(["ok", "ok"])).toBe("ok");
    expect(aggregateGroupStatus(["ok", "cached"])).toBe("ok");
  });

  test("genuine mix returns null", () => {
    expect(aggregateGroupStatus(["ok", undefined])).toBe(null);
    expect(aggregateGroupStatus(["ok", "cached", "skipped"])).toBe(null);
  });
});
