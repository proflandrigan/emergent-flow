import { describe, expect, test } from "vitest";

import type { EdgeModel, NodeModel } from "../store/model";
import { layeredLayout, separateOverlappingNodes } from "./layout";

function node(id: string, x: number, y: number): NodeModel {
  return {
    id,
    type: "test",
    paradigm: "functional",
    params: [],
    ports: [],
    position: { x, y },
  };
}

describe("separateOverlappingNodes", () => {
  test("two nodes at the same position are nudged apart", () => {
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
      b: node("b", 0, 0),
    };
    const result = separateOverlappingNodes(nodes);
    expect(result.a.position).not.toEqual(result.b.position);
  });

  test("three nodes at the same position — all pairwise distinct", () => {
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
      b: node("b", 0, 0),
      c: node("c", 0, 0),
    };
    const result = separateOverlappingNodes(nodes);
    expect(result.a.position).not.toEqual(result.b.position);
    expect(result.a.position).not.toEqual(result.c.position);
    expect(result.b.position).not.toEqual(result.c.position);
  });

  test("nodes at distinct positions are unchanged", () => {
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
      b: node("b", 100, 50),
    };
    const result = separateOverlappingNodes(nodes);
    expect(result.a.position).toEqual({ x: 0, y: 0 });
    expect(result.b.position).toEqual({ x: 100, y: 50 });
  });

  test("single node at origin is unchanged", () => {
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
    };
    const result = separateOverlappingNodes(nodes);
    expect(result.a.position).toEqual({ x: 0, y: 0 });
  });

  test("a cascaded node never lands on an unrelated node elsewhere in the graph", () => {
    // a/b collide at (0,0); the first cascade step for b would be (48,48),
    // which c already occupies -- b must be pushed past that too.
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
      b: node("b", 0, 0),
      c: node("c", 48, 48),
    };
    const result = separateOverlappingNodes(nodes);
    expect(result.b.position).not.toEqual(result.a.position);
    expect(result.b.position).not.toEqual(result.c.position);
    expect(result.c.position).toEqual({ x: 48, y: 48 });
  });
});

function makeEdge(
  id: string,
  source: string,
  target: string,
): EdgeModel {
  return {
    id,
    source: { node_id: source, port_id: "out" },
    target: { node_id: target, port_id: "in" },
  };
}

describe("layeredLayout", () => {
  test("two-node chain a -> b lays b to the right of a", () => {
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
      b: node("b", 0, 0),
    };
    const edges: Record<string, EdgeModel> = {
      ab: makeEdge("ab", "a", "b"),
    };
    const result = layeredLayout(nodes, edges);
    expect(result.b.position.x).toBeGreaterThan(result.a.position.x);
  });

  test("two nodes with no edges both stay in layer 0 with different y", () => {
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
      b: node("b", 0, 0),
    };
    const edges: Record<string, EdgeModel> = {};
    const result = layeredLayout(nodes, edges);
    expect(result.a.position.x).toBe(0);
    expect(result.b.position.x).toBe(0);
    expect(result.a.position.y).not.toBe(result.b.position.y);
  });

  test("diamond a->b, a->c, b->d, c->d places d past b and c", () => {
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
      b: node("b", 0, 0),
      c: node("c", 0, 0),
      d: node("d", 0, 0),
    };
    const edges: Record<string, EdgeModel> = {
      ab: makeEdge("ab", "a", "b"),
      ac: makeEdge("ac", "a", "c"),
      bd: makeEdge("bd", "b", "d"),
      cd: makeEdge("cd", "c", "d"),
    };
    const result = layeredLayout(nodes, edges);
    expect(result.d.position.x).toBeGreaterThan(result.b.position.x);
    expect(result.d.position.x).toBeGreaterThan(result.c.position.x);
  });
});
