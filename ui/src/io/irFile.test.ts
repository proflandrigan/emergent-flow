import { describe, expect, test } from "vitest";

import type { Graph } from "../generated/ir";
import { parseImport, serializeIR } from "./irFile";

describe("serializeIR", () => {
  test("round-trips a small graph through JSON.parse", () => {
    const graph: Graph = { paradigm: "functional", nodes: {}, edges: {} };

    const json = serializeIR(graph);

    expect(JSON.parse(json)).toEqual(graph);
  });
});

describe("parseImport", () => {
  test("returns an error for invalid JSON, no graph", () => {
    const result = parseImport("{ not json");

    expect(result.graph).toBeUndefined();
    expect(result.error).toBeTruthy();
  });

  test("returns a first-class version-mismatch error before structural validation", () => {
    const text = JSON.stringify({
      paradigm: "functional",
      nodes: {},
      edges: {},
      schema_version: 999,
    });

    const result = parseImport(text);

    expect(result.graph).toBeUndefined();
    expect(result.error).toContain("999");
  });

  test("returns the graph when valid and on the supported schema version", () => {
    const text = JSON.stringify({
      paradigm: "functional",
      nodes: {},
      edges: {},
    });

    const result = parseImport(text);

    expect(result.error).toBeUndefined();
    expect(result.graph).toEqual({
      paradigm: "functional",
      nodes: {},
      edges: {},
    });
  });

  test("returns a structural error when ajv validation fails", () => {
    const text = JSON.stringify({ nodes: "nope" });

    const result = parseImport(text);

    expect(result.graph).toBeUndefined();
    expect(result.error).toBeTruthy();
  });
});
