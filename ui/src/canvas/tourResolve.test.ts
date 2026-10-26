import { describe, expect, test } from "vitest";

import type { TourStep } from "../generated/tour";
import type { TraceEdge } from "./trace";
import { plainTourGraphView, resolveTourStep, type TourGraphView } from "./tourResolve";

function edge(id: string, source: string, target: string): TraceEdge {
  return { id, source, target };
}

const CHAIN_NODES = ["a", "b", "c", "d"];
const CHAIN_EDGES = [edge("ab", "a", "b"), edge("bc", "b", "c"), edge("cd", "c", "d")];
const chainView = plainTourGraphView(CHAIN_NODES, CHAIN_EDGES);

const DIAMOND_NODES = ["s", "l", "r", "t", "x"];
const DIAMOND_EDGES = [
  edge("sl", "s", "l"),
  edge("sr", "s", "r"),
  edge("lt", "l", "t"),
  edge("rt", "r", "t"),
];
const diamondView = plainTourGraphView(DIAMOND_NODES, DIAMOND_EDGES);

describe("resolveTourStep focus", () => {
  test("focus [b] highlights only b with no downstream expansion", () => {
    const result = resolveTourStep({ note: "n", focus: ["b"] }, chainView);
    expect(result.kind).toBe("focus");
    expect(result.routeStatus).toBeNull();
    expect(result.highlight.active).toBe(true);
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["b"]));
    expect(result.highlight.highlightedEdgeIds.size).toBe(0);
    expect(result.fitIds).toEqual(["b"]);
  });

  test("focus [a, b] highlights a, b and the edge between them only", () => {
    const result = resolveTourStep({ note: "n", focus: ["a", "b"] }, chainView);
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["a", "b"]));
    expect(result.highlight.highlightedEdgeIds).toEqual(new Set(["ab"]));
  });
});

describe("resolveTourStep reach", () => {
  test("down from b highlights b, c, d", () => {
    const result = resolveTourStep({ note: "n", focus: ["b"], reach: "down" }, chainView);
    expect(result.kind).toBe("reach");
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["b", "c", "d"]));
    expect(result.highlight.highlightedEdgeIds).toEqual(new Set(["bc", "cd"]));
    expect(result.fitIds).toEqual(["b"]);
  });

  test("up from c highlights a, b, c", () => {
    const result = resolveTourStep({ note: "n", focus: ["c"], reach: "up" }, chainView);
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["a", "b", "c"]));
    expect(result.highlight.highlightedEdgeIds).toEqual(new Set(["ab", "bc"]));
  });

  test("both from b highlights the whole chain", () => {
    const result = resolveTourStep({ note: "n", focus: ["b"], reach: "both" }, chainView);
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(CHAIN_NODES));
    expect(result.highlight.highlightedEdgeIds).toEqual(new Set(["ab", "bc", "cd"]));
  });
});

describe("resolveTourStep route", () => {
  test("route s -> t on the diamond highlights both branches and excludes x", () => {
    const result = resolveTourStep({ note: "n", route: ["s", "t"] }, diamondView);
    expect(result.kind).toBe("route");
    expect(result.routeStatus).toBe("found");
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["s", "l", "r", "t"]));
    expect(result.highlight.highlightedEdgeIds).toEqual(new Set(["sl", "sr", "lt", "rt"]));
    expect(result.highlight.highlightedNodeIds.has("x")).toBe(false);
    expect(result.fitIds).toEqual(["s", "t"]);
  });

  test("reverse-only route t -> s is no-path and is not retried reversed", () => {
    const result = resolveTourStep({ note: "n", route: ["t", "s"] }, diamondView);
    expect(result.routeStatus).toBe("no-path");
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["t", "s"]));
    expect(result.highlight.highlightedEdgeIds.size).toBe(0);
    expect(result.removedIds).toEqual([]);
  });

  test("disconnected present pair s -> x is no-path", () => {
    const result = resolveTourStep({ note: "n", route: ["s", "x"] }, diamondView);
    expect(result.routeStatus).toBe("no-path");
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["s", "x"]));
  });

  test("route with a removed endpoint is endpoint-removed and keeps the survivor", () => {
    const result = resolveTourStep({ note: "n", route: ["s", "gone"] }, diamondView);
    expect(result.routeStatus).toBe("endpoint-removed");
    expect(result.removedIds).toEqual(["gone"]);
    expect(result.authoredIds).toEqual(["s", "gone"]);
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["s"]));
    expect(result.fitIds).toEqual(["s"]);
  });
});

describe("resolveTourStep removed ids", () => {
  test("focus [a, gone] lists gone as removed and highlights a", () => {
    const result = resolveTourStep({ note: "n", focus: ["a", "gone"] }, chainView);
    expect(result.removedIds).toEqual(["gone"]);
    expect(result.authoredIds).toEqual(["a", "gone"]);
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["a"]));
  });

  test("all ids removed is inactive with nothing to fit", () => {
    const result = resolveTourStep({ note: "n", focus: ["gone", "gone2"] }, chainView);
    expect(result.removedIds).toEqual(["gone", "gone2"]);
    expect(result.highlight.active).toBe(false);
    expect(result.highlight.highlightedNodeIds.size).toBe(0);
    expect(result.fitIds).toEqual([]);
  });
});

describe("resolveTourStep collapsed groups", () => {
  // b and c are hidden inside group g; edges are re-anchored to the group.
  const hidden = new Set(["b", "c"]);
  const groupView: TourGraphView = {
    nodeIds: ["a", "g", "d"],
    edges: [edge("ag", "a", "g"), edge("gd", "g", "d")],
    hasNode: (id) => ["a", "b", "c", "d", "g"].includes(id),
    visibleId: (id) => (hidden.has(id) ? "g" : id),
  };

  test("focus on a hidden member highlights its group but keeps authored ids", () => {
    const result = resolveTourStep({ note: "n", focus: ["b"] }, groupView);
    expect(result.authoredIds).toEqual(["b"]);
    expect(result.removedIds).toEqual([]);
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["g"]));
    expect(result.fitIds).toEqual(["g"]);
  });

  test("route a -> c resolves through the group", () => {
    const result = resolveTourStep({ note: "n", route: ["a", "c"] }, groupView);
    expect(result.routeStatus).toBe("found");
    expect(result.highlight.highlightedNodeIds).toEqual(new Set(["a", "g"]));
    expect(result.highlight.highlightedEdgeIds).toEqual(new Set(["ag"]));
    expect(result.fitIds).toEqual(["a", "g"]);
  });
});

describe("resolveTourStep odd input", () => {
  test("a step with neither focus nor route is inactive and does not throw", () => {
    const step: TourStep = { note: "n" };
    const result = resolveTourStep(step, chainView);
    expect(result.kind).toBe("focus");
    expect(result.authoredIds).toEqual([]);
    expect(result.removedIds).toEqual([]);
    expect(result.highlight.active).toBe(false);
    expect(result.highlight.highlightedNodeIds.size).toBe(0);
    expect(result.highlight.highlightedEdgeIds.size).toBe(0);
    expect(result.routeStatus).toBeNull();
    expect(result.fitIds).toEqual([]);
  });
});
