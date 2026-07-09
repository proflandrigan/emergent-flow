import { describe, expect, test } from "vitest";

import type { GraphMutation } from "../generated/mutation";
import type { CanvasModel } from "../store/model";
import { computeGhostDiff } from "./ghostDiff";

function emptyModel(): CanvasModel {
  return { paradigm: "functional", nodes: {}, edges: {} };
}

function baseMutation(overrides: Partial<GraphMutation> = {}): GraphMutation {
  return { base_version: 0, ...overrides };
}

describe("computeGhostDiff", () => {
  test("auto-layouts an added node with no position, to the right of the existing graph", () => {
    const model: CanvasModel = {
      paradigm: "functional",
      nodes: {
        n1: {
          id: "n1",
          type: "data.load_csv",
          paradigm: "functional",
          params: [],
          ports: [],
          position: { x: 100, y: 0 },
        },
      },
      edges: {},
    };
    const mutation = baseMutation({
      add_nodes: [{ type: "stats.describe", ports: [], params: [] }],
    });

    const diff = computeGhostDiff(model, mutation);

    expect(diff.addedNodes).toHaveLength(1);
    expect(diff.addedNodes[0].position.x).toBeGreaterThan(100);
    expect(diff.addedNodes[0].id).toBeTruthy();
  });

  test("keeps an added node's explicit position", () => {
    const mutation = baseMutation({
      add_nodes: [
        {
          type: "stats.describe",
          ports: [],
          params: [],
          position: { x: 42, y: 7 },
        },
      ],
    });

    const diff = computeGhostDiff(emptyModel(), mutation);

    expect(diff.addedNodes[0].position).toEqual({ x: 42, y: 7 });
  });

  test("preserves an added node's explicit id, mints one when absent", () => {
    const mutation = baseMutation({
      add_nodes: [
        { id: "explicit-id", type: "a", ports: [], params: [] },
        { type: "b", ports: [], params: [] },
      ],
    });

    const diff = computeGhostDiff(emptyModel(), mutation);

    expect(diff.addedNodes[0].id).toBe("explicit-id");
    expect(diff.addedNodes[1].id).toBeTruthy();
    expect(diff.addedNodes[1].id).not.toBe("");
  });

  test("stacks multiple position-less added nodes vertically without colliding", () => {
    const mutation = baseMutation({
      add_nodes: [
        { type: "a", ports: [], params: [] },
        { type: "b", ports: [], params: [] },
      ],
    });

    const diff = computeGhostDiff(emptyModel(), mutation);

    expect(diff.addedNodes[0].position.y).not.toBe(
      diff.addedNodes[1].position.y,
    );
  });

  test("maps added edges and mints an id when absent", () => {
    const mutation = baseMutation({
      add_edges: [
        {
          source: { node_id: "n1", port_id: "p1" },
          target: { node_id: "n2", port_id: "p2" },
        },
      ],
    });

    const diff = computeGhostDiff(emptyModel(), mutation);

    expect(diff.addedEdges).toHaveLength(1);
    expect(diff.addedEdges[0].id).toBeTruthy();
    expect(diff.addedEdges[0].source).toEqual({ node_id: "n1", port_id: "p1" });
  });

  test("collects removed node/edge ids and param-changed node ids", () => {
    const mutation = baseMutation({
      remove_nodes: ["n1"],
      remove_edges: ["e1"],
      set_params: { n2: { threshold: 0.5 } },
    });

    const diff = computeGhostDiff(emptyModel(), mutation);

    expect(diff.removedNodeIds).toEqual(new Set(["n1"]));
    expect(diff.removedEdgeIds).toEqual(new Set(["e1"]));
    expect(diff.paramChangedNodeIds).toEqual(new Set(["n2"]));
  });

  test("a mutation with no changes produces an empty diff", () => {
    const diff = computeGhostDiff(emptyModel(), baseMutation());

    expect(diff.addedNodes).toEqual([]);
    expect(diff.addedEdges).toEqual([]);
    expect(diff.removedNodeIds.size).toBe(0);
    expect(diff.removedEdgeIds.size).toBe(0);
    expect(diff.paramChangedNodeIds.size).toBe(0);
  });

  test("does not mutate the input model or mutation", () => {
    const model = emptyModel();
    const modelCopy = structuredClone(model);
    const mutation = baseMutation({
      add_nodes: [{ type: "a", ports: [], params: [] }],
    });
    const mutationCopy = structuredClone(mutation);

    computeGhostDiff(model, mutation);

    expect(model).toEqual(modelCopy);
    expect(mutation).toEqual(mutationCopy);
  });
});
