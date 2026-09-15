import { describe, expect, test } from "vitest";

import { computeTrace } from "./trace";
import type { TraceEdge } from "./trace";

function edge(id: string, source: string, target: string): TraceEdge {
  return { id, source, target };
}

describe("computeTrace", () => {
  test("empty selection is inactive and empty", () => {
    const result = computeTrace([], ["a", "b"], [edge("ab", "a", "b")]);
    expect(result.active).toBe(false);
    expect(result.highlightedNodeIds.size).toBe(0);
    expect(result.highlightedEdgeIds.size).toBe(0);
  });

  test("linear chain a -> b -> c highlights all three nodes and both edges", () => {
    const result = computeTrace(
      ["a"],
      ["a", "b", "c"],
      [edge("ab", "a", "b"), edge("bc", "b", "c")],
    );
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b", "c"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab", "bc"]));
  });

  test("selected node with no downstream highlights only itself", () => {
    const result = computeTrace(["b"], ["a", "b"], [edge("ab", "a", "b")]);
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["b"]));
    expect(result.highlightedEdgeIds.size).toBe(0);
  });

  test("diamond a->b, a->c, b->d, c->d highlights all nodes and edges", () => {
    const result = computeTrace(
      ["a"],
      ["a", "b", "c", "d"],
      [
        edge("ab", "a", "b"),
        edge("ac", "a", "c"),
        edge("bd", "b", "d"),
        edge("cd", "c", "d"),
      ],
    );
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b", "c", "d"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab", "ac", "bd", "cd"]));
  });

  test("union of multiple roots highlights both chains", () => {
    const result = computeTrace(
      ["a", "c"],
      ["a", "b", "c", "d"],
      [edge("ab", "a", "b"), edge("cd", "c", "d")],
    );
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b", "c", "d"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab", "cd"]));
  });

  test("edge with only one endpoint highlighted is not highlighted", () => {
    const result = computeTrace(["q"], ["p", "q"], [edge("pq", "p", "q")]);
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["q"]));
    expect(result.highlightedEdgeIds.has("pq")).toBe(false);
  });

  test("selected id missing from nodeIds is skipped without breaking traversal", () => {
    const result = computeTrace(["ghost", "a"], ["a", "b"], [edge("ab", "a", "b")]);
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab"]));
  });

  test("cycles do not infinite-loop", () => {
    const result = computeTrace(
      ["a"],
      ["a", "b"],
      [edge("ab", "a", "b"), edge("ba", "b", "a")],
    );
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab", "ba"]));
  });
});
