import { describe, expect, test } from "vitest";

import type { EdgeModel, NodeModel } from "../store/model";
import {
  layeredLayout,
  separateOverlappingNodes,
  expandLayout,
  nodeFootprint,
  GROUP_MEMBER_COLUMN_WIDTH,
  GROUP_MEMBER_ROW_HEIGHT,
} from "./layout";

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

function groupNode(id: string): NodeModel {
  return {
    id,
    type: "layout.group",
    paradigm: "functional",
    params: [],
    ports: [],
    position: { x: 0, y: 0 },
    groupId: null,
  };
}

function nodeWithPorts(id: string, inCount: number, outCount: number): NodeModel {
  const inPorts = Array.from({ length: inCount }, (_, i) => ({
    id: `${id}-in-${i}`,
    name: `in_${i}`,
    direction: "in" as const,
    dataType: "any",
    cardinality: "one" as const,
  }));
  const outPorts = Array.from({ length: outCount }, (_, i) => ({
    id: `${id}-out-${i}`,
    name: `out_${i}`,
    direction: "out" as const,
    dataType: "any",
    cardinality: "one" as const,
  }));
  return { ...node(id, 0, 0), ports: [...inPorts, ...outPorts] };
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

  test("two grouped nodes that would land in different layers end up close together", () => {
    const group1 = "group1";
    const nodes: Record<string, NodeModel> = {
      a: { ...node("a", 0, 0), groupId: group1 },
      b: { ...node("b", 0, 0), groupId: group1 },
      [group1]: groupNode(group1),
    };
    const edges: Record<string, EdgeModel> = {
      ab: makeEdge("ab", "a", "b"),
    };
    const result = layeredLayout(nodes, edges);
    // Nodes a and b are members of group1, so they should be within one cell
    // width/height of each other despite a->b edge placing them in different
    // layers
    expect(Math.abs(result.a.position.x - result.b.position.x)).toBeLessThanOrEqual(
      GROUP_MEMBER_COLUMN_WIDTH,
    );
    expect(Math.abs(result.a.position.y - result.b.position.y)).toBeLessThanOrEqual(
      GROUP_MEMBER_ROW_HEIGHT,
    );
  });

  test("a node whose groupId points to non-existent group stays at layered position", () => {
    const nodes: Record<string, NodeModel> = {
      a: { ...node("a", 0, 0), groupId: "nonexistent" },
      b: node("b", 0, 0),
    };
    const edges: Record<string, EdgeModel> = {};
    const result = layeredLayout(nodes, edges);
    // a should stay at its individually computed layer 0 position
    expect(result.a.position.x).toBe(0);
  });

  test("ungrouped node unaffected when other nodes form a group", () => {
    const group1 = "group1";
    const nodes: Record<string, NodeModel> = {
      a: { ...node("a", 0, 0), groupId: group1 },
      b: { ...node("b", 0, 0), groupId: group1 },
      c: node("c", 0, 0),
      [group1]: groupNode(group1),
    };
    const edges: Record<string, EdgeModel> = {};
    const result = layeredLayout(nodes, edges);
    // a and b should be repositioned by the group re-pack, but c should stay
    // at its individually computed position (layer 0, row 2)
    expect(result.c.position.x).toBe(0);
    expect(result.c.position.y).toBeGreaterThan(0);
  });
});

describe("nodeFootprint", () => {
  test("grows with port count: 3 IN ports is taller than 0 ports, width constant", () => {
    const empty = nodeFootprint(nodeWithPorts("a", 0, 0));
    const busy = nodeFootprint(nodeWithPorts("b", 3, 0));
    expect(busy.height).toBeGreaterThan(empty.height);
    expect(busy.width).toBe(empty.width);
  });
});

describe("expandLayout", () => {
  test("two-node chain a -> b places b to the right of a", () => {
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
      b: node("b", 0, 0),
    };
    const edges: Record<string, EdgeModel> = {
      ab: makeEdge("ab", "a", "b"),
    };
    const result = expandLayout(nodes, edges);
    expect(result.b.position.x).toBeGreaterThan(result.a.position.x);
  });

  test("tall node in a layer forces extra row pitch (no vertical overlap)", () => {
    const nodes: Record<string, NodeModel> = {
      tall: nodeWithPorts("tall", 8, 0),
      short: node("short", 0, 0),
    };
    const edges: Record<string, EdgeModel> = {};
    const result = expandLayout(nodes, edges);
    const tallHeight = nodeFootprint(nodes.tall).height;
    const ySeparation = Math.abs(result.tall.position.y - result.short.position.y);
    expect(ySeparation).toBeGreaterThanOrEqual(tallHeight);
  });

  test("same-position collision produces distinct positions", () => {
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
      b: node("b", 0, 0),
    };
    const edges: Record<string, EdgeModel> = {};
    const result = expandLayout(nodes, edges);
    expect(result.a.position.y).not.toBe(result.b.position.y);
  });

  test("grouped nodes stay clustered", () => {
    const group1 = "group1";
    const nodes: Record<string, NodeModel> = {
      a: { ...node("a", 0, 0), groupId: group1 },
      b: { ...node("b", 0, 0), groupId: group1 },
      [group1]: groupNode(group1),
    };
    const edges: Record<string, EdgeModel> = {
      ab: makeEdge("ab", "a", "b"),
    };
    const result = expandLayout(nodes, edges);
    expect(Math.abs(result.a.position.x - result.b.position.x)).toBeLessThanOrEqual(
      GROUP_MEMBER_COLUMN_WIDTH,
    );
    expect(Math.abs(result.a.position.y - result.b.position.y)).toBeLessThanOrEqual(
      GROUP_MEMBER_ROW_HEIGHT,
    );
  });

  test("no edges -> all layer 0, stacked vertically, no y overlap", () => {
    const nodes: Record<string, NodeModel> = {
      a: node("a", 0, 0),
      b: node("b", 0, 0),
      c: node("c", 0, 0),
    };
    const edges: Record<string, EdgeModel> = {};
    const result = expandLayout(nodes, edges);
    expect(result.a.position.x).toBe(0);
    expect(result.b.position.x).toBe(0);
    expect(result.c.position.x).toBe(0);
    expect(result.a.position.y).not.toBe(result.b.position.y);
    expect(result.a.position.y).not.toBe(result.c.position.y);
    expect(result.b.position.y).not.toBe(result.c.position.y);
  });
});
