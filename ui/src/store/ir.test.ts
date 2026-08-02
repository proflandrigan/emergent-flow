import { describe, expect, test } from "vitest";

import { fromIR, toIR } from "./ir";
import type { Graph } from "../generated/ir";
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
              label: null,
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
              label: null,
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

  test("a non-null groupId survives round-trip through toIR -> fromIR", () => {
    const model: CanvasModel = {
      schemaVersion: 1,
      name: "My Pipeline",
      paradigm: "functional",
      nodes: {
        "group-1": {
          id: "group-1",
          type: "layout.group",
          label: "My Group",
          paradigm: "functional",
          position: { x: 0, y: 0 },
          groupId: null,
          params: [
            { name: "label", typeToken: "str", value: "My Group", default: "My Group" },
            { name: "color", typeToken: "str", value: "slate", default: "slate" },
          ],
          ports: [],
        },
        "node-1": {
          id: "node-1",
          type: "data.load_csv",
          label: "Load CSV",
          paradigm: "functional",
          position: { x: 10, y: 20 },
          groupId: "group-1",
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
              label: null,
            },
          ],
        },
      },
      edges: {},
    };

    const roundTripped = fromIR(toIR(model));

    expect(roundTripped.nodes["node-1"].groupId).toBe("group-1");
    expect(roundTripped).toEqual(model);
  });
});

describe("composite/module subgraph fidelity", () => {
  // A DECLARATIVE graph's whole substance lives in the `nn.module` node's `subgraph`. The
  // canvas doesn't render subgraphs, but `fromIR`/`toIR` sit on every path that moves a graph
  // in and out of the store -- file import/export, session join/push, accepting an agent
  // proposal -- so dropping the field silently destroyed the model and left a graph that
  // `compile_to_code` rejects with "nn.module node ... has no subgraph to compile."
  const subgraph = {
    paradigm: "declarative" as const,
    name: "SimpleClassifier body",
    nodes: {
      "n-linear": {
        id: "n-linear",
        type: "nn.linear",
        paradigm: "declarative" as const,
        position: { x: 0, y: 0 },
        params: [{ name: "out_features", type_token: "int", value: 64 }],
        ports: [],
      },
    },
    edges: {},
  };

  function moduleGraph(): Graph {
    return {
      paradigm: "declarative",
      nodes: {
        "n-module": {
          id: "n-module",
          type: "nn.module",
          label: "Net",
          paradigm: "declarative",
          position: { x: 0, y: 0 },
          params: [],
          ports: [],
          subgraph,
        },
      },
      edges: {},
    };
  }

  test("an nn.module's subgraph survives fromIR -> toIR", () => {
    const graph = moduleGraph();
    const roundTripped = toIR(fromIR(graph));

    // Deep-equal, not just present: every layer, param and edge inside the module must come
    // back untouched, since the canvas has no way to reconstruct them.
    expect(roundTripped.nodes!["n-module"].subgraph).toEqual(subgraph);
  });

  test("an explicit `subgraph: null` is preserved as null, not dropped", () => {
    const graph: Graph = {
      paradigm: "functional",
      nodes: {
        "n-1": {
          id: "n-1",
          type: "data.load_csv",
          paradigm: "functional",
          position: { x: 0, y: 0 },
          params: [],
          ports: [],
          subgraph: null,
        },
      },
      edges: {},
    };

    expect(toIR(fromIR(graph)).nodes!["n-1"]).toHaveProperty("subgraph", null);
  });

  test("a canvas-built node with no subgraph key does not gain one", () => {
    const model: CanvasModel = {
      paradigm: "functional",
      nodes: {
        "n-1": {
          id: "n-1",
          type: "data.load_csv",
          paradigm: "functional",
          position: { x: 0, y: 0 },
          params: [],
          ports: [],
          groupId: null,
        },
      },
      edges: {},
    };

    expect(toIR(model).nodes!["n-1"]).not.toHaveProperty("subgraph");
  });
});

describe("graph-level params", () => {
  // `paramToIR`/`paramFromIR` are module-private, so `ref`/`description` fidelity is verified
  // through the node-param path (`nodeToIR`/`nodeFromIR` route every param through them).

  test("a ParamModel with ref/description maps to IR and back unchanged", () => {
    const model: CanvasModel = {
      paradigm: "functional",
      nodes: {
        "node-1": {
          id: "node-1",
          type: "data.load_csv",
          paradigm: "functional",
          position: { x: 10, y: 20 },
          groupId: null,
          params: [
            {
              name: "path",
              typeToken: "str",
              value: "a.csv",
              default: null,
              ref: "data_dir",
              description: "CSV file to load",
            },
          ],
          ports: [],
        },
      },
      edges: {},
    };

    const roundTripped = fromIR(toIR(model));

    expect(roundTripped.nodes["node-1"].params[0]).toEqual(
      model.nodes["node-1"].params[0],
    );
  });

  test("a CanvasModel with graph-level params round-trips through toIR/fromIR", () => {
    const model: CanvasModel = {
      paradigm: "functional",
      nodes: {},
      edges: {},
      params: {
        p: {
          name: "p",
          typeToken: "str",
          value: "hello",
          default: null,
          ref: null,
          description: "A graph-level param",
        },
      },
    };

    expect(fromIR(toIR(model))).toEqual(model);
  });

  test("a CanvasModel without params produces an IR graph without a params key", () => {
    const graph = toIR(emptyModel());

    expect(graph).not.toHaveProperty("params");
  });
});
