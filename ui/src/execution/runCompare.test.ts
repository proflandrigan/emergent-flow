import { describe, it, expect } from "vitest";
import { computeRunGraphDiff } from "./runCompare";

describe("computeRunGraphDiff", () => {
  it("detects added nodes", () => {
    const graphA: Record<string, unknown> = { nodes: { n1: { type: "test" } }, edges: {} };
    const graphB: Record<string, unknown> = { nodes: { n1: { type: "test" }, n2: { type: "test" } }, edges: {} };
    const diff = computeRunGraphDiff(graphA, graphB);
    expect(diff.added).toHaveLength(1);
    expect(diff.added[0].id).toBe("n2");
  });

  it("detects removed nodes", () => {
    const graphA: Record<string, unknown> = { nodes: { n1: { type: "test" }, n2: { type: "test" } }, edges: {} };
    const graphB: Record<string, unknown> = { nodes: { n1: { type: "test" } }, edges: {} };
    const diff = computeRunGraphDiff(graphA, graphB);
    expect(diff.removed).toHaveLength(1);
    expect(diff.removed[0].id).toBe("n2");
  });

  it("detects modified nodes", () => {
    const graphA: Record<string, unknown> = { nodes: { n1: { type: "test", params: [{ name: "x", value: 1 }] } }, edges: {} };
    const graphB: Record<string, unknown> = { nodes: { n1: { type: "test", params: [{ name: "x", value: 2 }] } }, edges: {} };
    const diff = computeRunGraphDiff(graphA, graphB);
    expect(diff.modified).toHaveLength(1);
  });

  it("returns empty diff for identical graphs", () => {
    const graph: Record<string, unknown> = { nodes: { n1: { type: "test" } }, edges: {} };
    const diff = computeRunGraphDiff(graph, graph);
    expect(diff.added).toHaveLength(0);
    expect(diff.removed).toHaveLength(0);
    expect(diff.modified).toHaveLength(0);
    expect(diff.addedEdges).toHaveLength(0);
    expect(diff.removedEdges).toHaveLength(0);
  });
});