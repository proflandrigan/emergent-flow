import { describe, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import { generateLargeGraph } from "./generateLargeGraph";

const SPACING_X = 220;
const SPACING_Y = 140;

describe("generateLargeGraph", () => {
  test("generates a large graph with correct node count", () => {
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

    // 10 generated nodes + 2 group containers (Stage A, Stage B)
    expect(Object.keys(model.nodes)).toHaveLength(12);
  });

  test("each node has a unique id", () => {
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
    const ids = Object.keys(model.nodes);
    const uniqueIds = new Set(ids);

    expect(uniqueIds.size).toBe(ids.length);
  });

  test("edges are empty", () => {
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

    expect(model.edges).toEqual({});
  });

  test("node 0 has position {x: 0, y: 0}", () => {
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
    const nodeId = Object.keys(model.nodes)[0];

    expect(model.nodes[nodeId].position).toEqual({ x: 0, y: 0 });
  });

  test("node 1 has position {x: SPACING_X, y: 0}", () => {
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
    const nodeId = Object.keys(model.nodes)[1];

    expect(model.nodes[nodeId].position).toEqual({ x: SPACING_X, y: 0 });
  });

  test("node at index 40 has y === SPACING_Y", () => {
    const spec: CatalogNode = {
      type: "t",
      version: 1,
      family: "f",
      label: "L",
      paradigm: "functional",
      ports: [{ name: "out", direction: "out" }],
      params: [],
    };

    const model = generateLargeGraph(spec, 50);
    const nodeId = Object.keys(model.nodes)[40];

    expect(model.nodes[nodeId].position.y).toBe(SPACING_Y);
  });

  test("each node's ports match spec and have fresh ids", () => {
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

    for (const node of Object.values(model.nodes)) {
      if (node.type === "layout.group") continue;
      expect(node.ports).toHaveLength(1);
      const port = node.ports[0];
      expect(port.name).toBe("out");
      expect(port.dataType).toBe("any");
      expect(port.id).toBeTruthy();
    }
  });

  test("node ports have unique ids", () => {
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
    const portIds = Object.values(model.nodes).flatMap((n) =>
      n.ports.map((p) => p.id),
    );
    const uniquePortIds = new Set(portIds);

    expect(uniquePortIds.size).toBe(portIds.length);
  });
});
