import { beforeEach, describe, expect, test } from "vitest";

import { selectedNodeId, useSelectionStore } from "./selectionStore";

beforeEach(() => {
  useSelectionStore.setState({ nodes: {}, edges: {} });
});

describe("selectedNodeId", () => {
  test("returns the id when exactly one node is selected", () => {
    useSelectionStore.getState().setNodeSelected("n1", true);
    expect(selectedNodeId(useSelectionStore.getState())).toBe("n1");
  });

  test("returns null when two nodes are selected", () => {
    useSelectionStore.getState().setNodeSelected("n1", true);
    useSelectionStore.getState().setNodeSelected("n2", true);
    expect(selectedNodeId(useSelectionStore.getState())).toBeNull();
  });

  test("returns null when zero nodes are selected", () => {
    expect(selectedNodeId(useSelectionStore.getState())).toBeNull();
  });
});

describe("clear", () => {
  test("empties both nodes and edges", () => {
    useSelectionStore.getState().setNodeSelected("n1", true);
    useSelectionStore.getState().setEdgeSelected("e1", true);

    useSelectionStore.getState().clear();

    expect(useSelectionStore.getState().nodes).toEqual({});
    expect(useSelectionStore.getState().edges).toEqual({});
  });
});

describe("setEdgeSelected", () => {
  test("records the edge selection", () => {
    useSelectionStore.getState().setEdgeSelected("e1", true);
    expect(useSelectionStore.getState().edges).toEqual({ e1: true });
  });
});
