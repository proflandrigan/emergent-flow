// Story 5 acceptance: build a graph on the canvas -> IR -> reload -> identical canvas.

import { beforeEach, describe, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import { useGraphStore } from "./graphStore";

const sourceSpec: CatalogNode = {
  type: "test.source",
  version: 1,
  family: "test",
  label: "Source",
  paradigm: "functional",
  ports: [
    { name: "out", direction: "out", data_type: "any", cardinality: "one" },
  ],
  params: [{ name: "path", type_token: "str", default: "data.csv" }],
};

const sinkSpec: CatalogNode = {
  type: "test.sink",
  version: 1,
  family: "test",
  label: "Sink",
  paradigm: "functional",
  ports: [
    { name: "in", direction: "in", data_type: "any", cardinality: "one" },
  ],
  params: [],
};

beforeEach(() => {
  useGraphStore.getState().reset();
});

describe("IR round-trip", () => {
  test("toIR -> reset -> loadIR reproduces the same canvas model", () => {
    const sourceId = useGraphStore
      .getState()
      .addNodeFromSpec(sourceSpec, { x: 0, y: 0 });
    const sinkId = useGraphStore
      .getState()
      .addNodeFromSpec(sinkSpec, { x: 200, y: 100 });

    const sourcePort = useGraphStore.getState().nodes[sourceId].ports[0];
    const sinkPort = useGraphStore.getState().nodes[sinkId].ports[0];
    useGraphStore
      .getState()
      .connect(
        { node_id: sourceId, port_id: sourcePort.id },
        { node_id: sinkId, port_id: sinkPort.id },
      );
    useGraphStore.getState().setParam(sourceId, "path", "other.csv");

    const { paradigm, name, nodes, edges } = useGraphStore.getState();
    const before = structuredClone({ paradigm, name, nodes, edges });

    const ir = useGraphStore.getState().toIR();
    useGraphStore.getState().reset();
    useGraphStore.getState().loadIR(ir);

    const after = (() => {
      const { paradigm, name, nodes, edges } = useGraphStore.getState();
      return { paradigm, name, nodes, edges };
    })();

    expect(after).toEqual(before);
  });
});
