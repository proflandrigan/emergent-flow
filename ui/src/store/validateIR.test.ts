import { describe, expect, test } from "vitest";

import {
  checkSchemaVersion,
  supportedSchemaVersion,
  validateIR,
} from "./validateIR";
import type { Graph } from "../generated/ir";

function validGraph(): Graph {
  return { paradigm: "functional", nodes: {}, edges: {} };
}

describe("supportedSchemaVersion", () => {
  test("is read from the schema and equals the current IR version", () => {
    expect(typeof supportedSchemaVersion).toBe("number");
    expect(supportedSchemaVersion).toBe(2);
  });
});

describe("validateIR", () => {
  test("accepts a minimal valid graph", () => {
    const result = validateIR(validGraph());

    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  test("rejects a graph with a node missing the required type", () => {
    const invalidGraph = {
      paradigm: "functional",
      nodes: { n1: { id: "n1" } },
      edges: {},
    } as unknown;

    const result = validateIR(invalidGraph);

    expect(result.valid).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});

describe("checkSchemaVersion", () => {
  test("returns null when schema_version matches the supported version", () => {
    const graph: Graph = { ...validGraph(), schema_version: supportedSchemaVersion };

    expect(checkSchemaVersion(graph)).toBeNull();
  });

  test("returns a message naming both versions on mismatch", () => {
    const graph: Graph = { ...validGraph(), schema_version: 999 };

    const message = checkSchemaVersion(graph);

    expect(message).not.toBeNull();
    expect(message).toContain("999");
    expect(message).toContain(String(supportedSchemaVersion));
  });

  test("returns null when schema_version is omitted", () => {
    expect(checkSchemaVersion(validGraph())).toBeNull();
  });
});
