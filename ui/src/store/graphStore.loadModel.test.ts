import { beforeEach, describe, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import { generateLargeGraph } from "../dev/generateLargeGraph";
import { useGraphStore } from "./graphStore";

beforeEach(() => {
  useGraphStore.getState().reset();
});

describe("loadModel", () => {
  test("loads a model and updates store nodes", () => {
    const spec: CatalogNode = {
      type: "t",
      version: 1,
      family: "f",
      label: "L",
      paradigm: "functional",
      ports: [{ name: "out", direction: "out" }],
      params: [],
    };

    const model = generateLargeGraph(spec, 10);
    useGraphStore.getState().loadModel(model);

    const { nodes } = useGraphStore.getState();
    expect(Object.keys(nodes)).toHaveLength(10);
  });

  test("undo restores prior state with single history entry", () => {
    const spec: CatalogNode = {
      type: "t",
      version: 1,
      family: "f",
      label: "L",
      paradigm: "functional",
      ports: [{ name: "out", direction: "out" }],
      params: [],
    };

    const model = generateLargeGraph(spec, 10);
    useGraphStore.getState().loadModel(model);

    // After loadModel, we should have 1 entry in past (the empty state)
    expect(useGraphStore.getState().past).toHaveLength(1);

    // Undo should restore empty state
    useGraphStore.getState().undo();
    const { nodes } = useGraphStore.getState();
    expect(Object.keys(nodes)).toHaveLength(0);
  });
});
