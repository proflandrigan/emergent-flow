import { describe, expect, test } from "vitest";

import { fromIR, toIR } from "./ir";
import type { CanvasModel } from "./model";

function emptyModel(): CanvasModel {
  return { paradigm: "functional", nodes: {}, edges: {} };
}

describe("toIR", () => {
  test("maps an empty model to an empty functional graph with no Python-only fields", () => {
    const graph = toIR(emptyModel());

    expect(graph).toEqual({
      paradigm: "functional",
      nodes: {},
      edges: {},
    });
    expect(graph).not.toHaveProperty("schema_version");
    expect(graph).not.toHaveProperty("name");
  });

  test("maps a model with one node and one edge into id-keyed IR maps", () => {
    const model: CanvasModel = {
      paradigm: "functional",
      nodes: {
        "node-1": {
          id: "node-1",
          type: "data.load_csv",
          label: "Load CSV",
          paradigm: "functional",
          position: { x: 10, y: 20 },
          groupId: null,
          params: [
            { name: "path", typeToken: "str", value: "a.csv", default: null },
            {
              name: "encoding",
              typeToken: "str",
              value: "utf-8",
              default: "utf-8",
            },
          ],
          ports: [
            {
              id: "port-out",
              name: "frame",
              direction: "out",
              dataType: "DataFrame",
              cardinality: "one",
            },
          ],
        },
        "node-2": {
          id: "node-2",
          type: "reports.generate_html_summary",
          paradigm: "functional",
          position: { x: 100, y: 20 },
          groupId: null,
          params: [],
          ports: [
            {
              id: "port-in",
              name: "frame",
              direction: "in",
              dataType: "DataFrame",
              cardinality: "one",
            },
          ],
        },
      },
      edges: {
        "edge-1": {
          id: "edge-1",
          source: { node_id: "node-1", port_id: "port-out" },
          target: { node_id: "node-2", port_id: "port-in" },
        },
      },
    };

    const graph = toIR(model);

    expect(Object.keys(graph.nodes ?? {})).toEqual(["node-1", "node-2"]);
    expect(Object.keys(graph.edges ?? {})).toEqual(["edge-1"]);

    const node1 = graph.nodes?.["node-1"];
    expect(node1?.type).toBe("data.load_csv");
    expect(node1?.ports?.[0]).toMatchObject({ id: "port-out", name: "frame" });
    expect(node1?.params?.[0]).toMatchObject({
      name: "path",
      type_token: "str",
      value: "a.csv",
    });

    const edge1 = graph.edges?.["edge-1"];
    expect(edge1?.source).toEqual({ node_id: "node-1", port_id: "port-out" });
    expect(edge1?.target).toEqual({ node_id: "node-2", port_id: "port-in" });
  });

  test("round-trips a model through toIR -> fromIR", () => {
    const model: CanvasModel = {
      schemaVersion: 1,
      name: "My Pipeline",
      paradigm: "functional",
      nodes: {
        "node-1": {
          id: "node-1",
          type: "data.load_csv",
          label: "Load CSV",
          paradigm: "functional",
          position: { x: 10, y: 20 },
          groupId: null,
          params: [
            { name: "path", typeToken: "str", value: "a.csv", default: null },
          ],
          ports: [
            {
              id: "port-out",
              name: "frame",
              direction: "out",
              dataType: "DataFrame",
              cardinality: "one",
            },
          ],
        },
        "node-2": {
          id: "node-2",
          type: "reports.generate_html_summary",
          paradigm: "functional",
          position: { x: 100, y: 20 },
          groupId: null,
          params: [],
          ports: [
            {
              id: "port-in",
              name: "frame",
              direction: "in",
              dataType: "DataFrame",
              cardinality: "one",
            },
          ],
        },
      },
      edges: {
        "edge-1": {
          id: "edge-1",
          source: { node_id: "node-1", port_id: "port-out" },
          target: { node_id: "node-2", port_id: "port-in" },
        },
      },
    };

    expect(fromIR(toIR(model))).toEqual(model);
  });
});
