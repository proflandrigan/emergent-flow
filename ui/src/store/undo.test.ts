import { beforeEach, describe, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import catalog from "../generated/catalog.json";
import { useGraphStore } from "./graphStore";

const catalogNodes = (catalog as unknown as { nodes: CatalogNode[] }).nodes;

function requireCatalogNode(type: string): CatalogNode {
  const node = catalogNodes.find((entry) => entry.type === type);
  if (!node) {
    throw new Error(`expected catalog fixture \`${type}\` to exist`);
  }
  return node;
}

const loadCsv = requireCatalogNode("data.load_csv");

beforeEach(() => {
  useGraphStore.getState().reset();
});

describe("undo/redo: add node", () => {
  test("undo removes the added node, redo restores it", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(1);

    useGraphStore.getState().undo();
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(0);

    useGraphStore.getState().redo();
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(1);
  });
});

describe("undo/redo: connect", () => {
  function addTwoConnectableNodes() {
    const sourceId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const targetId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 100, y: 0 });
    const sourcePort = useGraphStore.getState().nodes[sourceId].ports[0];
    const targetPort = useGraphStore.getState().nodes[targetId].ports[0];
    return {
      source: { node_id: sourceId, port_id: sourcePort.id },
      target: { node_id: targetId, port_id: targetPort.id },
    };
  }

  test("undo removes the connected edge, redo restores it", () => {
    const { source, target } = addTwoConnectableNodes();
    useGraphStore.getState().connect(source, target);
    expect(Object.keys(useGraphStore.getState().edges)).toHaveLength(1);

    useGraphStore.getState().undo();
    expect(Object.keys(useGraphStore.getState().edges)).toHaveLength(0);

    useGraphStore.getState().redo();
    expect(Object.keys(useGraphStore.getState().edges)).toHaveLength(1);
  });
});

describe("undo/redo: new action clears redo stack", () => {
  test("performing a new action after undo empties future", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    useGraphStore.getState().undo();
    expect(useGraphStore.getState().future.length).toBeGreaterThan(0);

    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 10, y: 10 });
    expect(useGraphStore.getState().future).toHaveLength(0);

    const nodeCountBeforeRedo = Object.keys(
      useGraphStore.getState().nodes,
    ).length;
    useGraphStore.getState().redo();
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(
      nodeCountBeforeRedo,
    );
  });
});

describe("undo/redo: move coalescing", () => {
  test("a multi-step drag collapses into a single undo step", () => {
    const nodeId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    const originalPosition = useGraphStore.getState().nodes[nodeId].position;
    const pastLengthAfterAdd = useGraphStore.getState().past.length;

    useGraphStore.getState().moveNode(nodeId, { x: 10, y: 10 });
    useGraphStore.getState().moveNode(nodeId, { x: 20, y: 20 });
    useGraphStore.getState().moveNode(nodeId, { x: 30, y: 30 });

    expect(useGraphStore.getState().nodes[nodeId].position).toEqual({
      x: 30,
      y: 30,
    });
    // The drag should have pushed exactly one history entry, not three.
    expect(useGraphStore.getState().past.length).toBe(pastLengthAfterAdd + 1);

    useGraphStore.getState().undo();
    expect(useGraphStore.getState().nodes[nodeId].position).toEqual(
      originalPosition,
    );
  });
});

describe("canUndo / canRedo", () => {
  test("reflect the current stack state", () => {
    expect(useGraphStore.getState().canUndo()).toBe(false);
    expect(useGraphStore.getState().canRedo()).toBe(false);

    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    expect(useGraphStore.getState().canUndo()).toBe(true);
    expect(useGraphStore.getState().canRedo()).toBe(false);

    useGraphStore.getState().undo();
    expect(useGraphStore.getState().canUndo()).toBe(false);
    expect(useGraphStore.getState().canRedo()).toBe(true);

    useGraphStore.getState().redo();
    expect(useGraphStore.getState().canUndo()).toBe(true);
    expect(useGraphStore.getState().canRedo()).toBe(false);
  });
});
