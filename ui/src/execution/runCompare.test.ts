import { describe, it, expect } from "vitest";
import { computeRunGraphDiff } from "./runCompare";

describe("computeRunGraphDiff", () => {
  it("detects added nodes", () => {
    const graphA = { nodes: { n1: { type: "test" } }, edges: {} };
    const graphB = { nodes: { n1: { type: "test" }, n2: { type: "test" } }, edges: {} };
    const diff = computeRunGraphDiff(graphA as any, graphB as any);
    expect(diff.added).toHaveLength(1);
    expect(diff.added[0].id).toBe("n2");
  });

  it("detects removed nodes", () => {
    const graphA = { nodes: { n1: { type: "test" }, n2: { type: "test" } }, edges: {} };
    const graphB = { nodes: { n1: { type: "test" } }, edges: {} };
    const diff = computeRunGraphDiff(graphA as any, graphB as any);
    expect(diff.removed).toHaveLength(1);
    expect(diff.removed[0].id).toBe("n2");
  });

  it("detects modified nodes", () => {
    const graphA = { nodes: { n1: { type: "test", params: [{ name: "x", value: 1 }] } }, edges: {} };
    const graphB = { nodes: { n1: { type: "test", params: [{ name: "x", value: 2 }] } }, edges: {} };
    const diff = computeRunGraphDiff(graphA as any, graphB as any);
    expect(diff.modified).toHaveLength(1);
  });

  it("returns empty diff for identical graphs", () => {
    const graph = { nodes: { n1: { type: "test" } }, edges: {} };
    const diff = computeRunGraphDiff(graph as any, graph as any);
    expect(diff.added).toHaveLength(0);
    expect(diff.removed).toHaveLength(0);
    expect(diff.modified).toHaveLength(0);
    expect(diff.addedEdges).toHaveLength(0);
    expect(diff.removedEdges).toHaveLength(0);
  });
});