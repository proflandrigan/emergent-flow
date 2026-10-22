import { describe, expect, test } from "vitest";

import { computeLens, computeReach, computeRoute, computeTrace } from "./trace";
import type { LensNode } from "./trace";
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

const DIAMOND_NODES = ["a", "b", "c", "d"];
const DIAMOND_EDGES = [
  edge("ab", "a", "b"),
  edge("ac", "a", "c"),
  edge("bd", "b", "d"),
  edge("cd", "c", "d"),
];

describe("computeReach", () => {
  const chain = [edge("ab", "a", "b"), edge("bc", "b", "c")];

  test("upstream on chain from c highlights a, b, c", () => {
    const result = computeReach(["c"], ["a", "b", "c"], chain, "upstream");
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b", "c"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab", "bc"]));
  });

  test("upstream from b in a->b->c highlights a, b only", () => {
    const result = computeReach(["b"], ["a", "b", "c"], chain, "upstream");
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab"]));
  });

  test("both from b excludes siblings", () => {
    const result = computeReach(
      ["b"],
      ["a", "b", "c", "x"],
      [...chain, edge("ax", "a", "x")],
      "both",
    );
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b", "c"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab", "bc"]));
  });

  test("upstream diamond from d highlights everything", () => {
    const result = computeReach(["d"], DIAMOND_NODES, DIAMOND_EDGES, "upstream");
    expect(result.highlightedNodeIds).toEqual(new Set(DIAMOND_NODES));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab", "ac", "bd", "cd"]));
  });

  test("upstream cycle terminates", () => {
    const result = computeReach(
      ["a"],
      ["a", "b"],
      [edge("ab", "a", "b"), edge("ba", "b", "a")],
      "upstream",
    );
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b"]));
  });

  test("empty roots are inactive", () => {
    const result = computeReach([], ["a", "b"], chain, "both");
    expect(result.active).toBe(false);
    expect(result.highlightedNodeIds.size).toBe(0);
    expect(result.highlightedEdgeIds.size).toBe(0);
  });

  test("downstream equals computeTrace for the diamond", () => {
    const reach = computeReach(["a"], DIAMOND_NODES, DIAMOND_EDGES, "downstream");
    const trace = computeTrace(["a"], DIAMOND_NODES, DIAMOND_EDGES);
    expect(reach).toEqual(trace);
  });
});

describe("computeRoute", () => {
  test("route a->d in diamond excludes off-route nodes and edges", () => {
    const result = computeRoute(
      "a",
      "d",
      [...DIAMOND_NODES, "e", "z"],
      [...DIAMOND_EDGES, edge("de", "d", "e"), edge("zb", "z", "b")],
    );
    expect(result.active).toBe(true);
    expect(result.found).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b", "c", "d"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab", "ac", "bd", "cd"]));
  });

  test("unreachable route is not found", () => {
    const result = computeRoute("d", "a", DIAMOND_NODES, DIAMOND_EDGES);
    expect(result.active).toBe(true);
    expect(result.found).toBe(false);
    expect(result.highlightedNodeIds.size).toBe(0);
    expect(result.highlightedEdgeIds.size).toBe(0);
  });

  test("disconnected nodes are not found", () => {
    const result = computeRoute("a", "b", ["a", "b"], []);
    expect(result.found).toBe(false);
  });

  test("from === to is found with a single node and no edges", () => {
    const result = computeRoute("a", "a", ["a", "b"], [edge("ab", "a", "b")]);
    expect(result.found).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["a"]));
    expect(result.highlightedEdgeIds.size).toBe(0);
  });

  test("deleted ids are not found", () => {
    const edges = [edge("ab", "a", "b")];
    expect(computeRoute("ghost", "a", ["a", "b"], edges).found).toBe(false);
    expect(computeRoute("a", "ghost", ["a", "b"], edges).found).toBe(false);
  });

  test("cycle a->b->c->a route a->c terminates", () => {
    const result = computeRoute(
      "a",
      "c",
      ["a", "b", "c"],
      [edge("ab", "a", "b"), edge("bc", "b", "c"), edge("ca", "c", "a")],
    );
    expect(result.found).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b", "c"]));
    expect(result.highlightedEdgeIds.has("ab")).toBe(true);
    expect(result.highlightedEdgeIds.has("bc")).toBe(true);
  });
});

describe("computeLens", () => {
  const lensNodes: LensNode[] = [
    { id: "a", family: "data" },
    { id: "b", family: "ml" },
    { id: "c", family: "ml" },
    { id: "d", family: null },
  ];
  const lensEdges = [edge("ab", "a", "b"), edge("bc", "b", "c"), edge("cd", "c", "d")];

  test("empty families is inactive and empty", () => {
    const result = computeLens(new Set(), lensNodes, lensEdges);
    expect(result.active).toBe(false);
    expect(result.highlightedNodeIds.size).toBe(0);
    expect(result.highlightedEdgeIds.size).toBe(0);
  });

  test("single family highlights matching nodes and edges between them only", () => {
    const result = computeLens(new Set(["ml"]), lensNodes, lensEdges);
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["b", "c"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["bc"]));
  });

  test("multiple families highlight the union", () => {
    const result = computeLens(new Set(["data", "ml"]), lensNodes, lensEdges);
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds).toEqual(new Set(["a", "b", "c"]));
    expect(result.highlightedEdgeIds).toEqual(new Set(["ab", "bc"]));
  });

  test("family not present in nodes is active with empty sets", () => {
    const result = computeLens(new Set(["viz"]), lensNodes, lensEdges);
    expect(result.active).toBe(true);
    expect(result.highlightedNodeIds.size).toBe(0);
    expect(result.highlightedEdgeIds.size).toBe(0);
  });
});
