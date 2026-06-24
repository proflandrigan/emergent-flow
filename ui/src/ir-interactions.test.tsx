// Epic 5 Story 3 (integration coverage): proves that the realistic canvas interactions --
// adding a node via the palette UI and connecting two ports -- produce valid,
// referentially-coherent IR. Complements the store-level unit tests in
// `store/graphStore.test.ts` (which exercise the actions directly) by also driving the
// palette-click path through a real render, then asserting IR-schema-shaped invariants.

import { render, screen, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { useGraphStore } from "./store/graphStore";
import type { CatalogNode } from "./catalog/types";
import catalog from "./generated/catalog.json";
import type { Graph } from "./generated/ir";

const nodes = (catalog as unknown as { nodes: CatalogNode[] }).nodes;

function requireNode(type: string): CatalogNode {
  const n = nodes.find((e) => e.type === type);
  if (!n) {
    throw new Error(`fixture ${type} missing`);
  }
  return n;
}

beforeEach(() => {
  useGraphStore.getState().reset();
  // Force offline so the palette/App use the committed catalog + show "unreachable"
  // deterministically (no real server in unit tests).
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
});

afterEach(() => vi.restoreAllMocks());

// Checks the IR-schema invariants that every produced graph must satisfy: maps keyed by their
// own id, and every edge endpoint referencing a real node + a real port on that node.
function assertCoherent(graph: Graph): true {
  for (const [id, node] of Object.entries(graph.nodes ?? {})) {
    expect(node.id).toBe(id);
  }
  for (const [id, edge] of Object.entries(graph.edges ?? {})) {
    expect(edge.id).toBe(id);

    const sourceNode = graph.nodes?.[edge.source.node_id];
    expect(sourceNode).toBeDefined();
    expect(
      (sourceNode?.ports ?? []).some((p) => p.id === edge.source.port_id),
    ).toBe(true);

    const targetNode = graph.nodes?.[edge.target.node_id];
    expect(targetNode).toBeDefined();
    expect(
      (targetNode?.ports ?? []).some((p) => p.id === edge.target.port_id),
    ).toBe(true);
  }
  return true;
}

test("adding a node via the palette UI produces IR with that node", () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: /Load CSV/ }));

  const graph = useGraphStore.getState().toIR();
  const entries = Object.entries(graph.nodes ?? {});
  expect(entries).toHaveLength(1);

  const [, node] = entries[0];
  expect(node.type).toBe("data.load_csv");
  const ports = node.ports ?? [];
  expect(ports.length).toBeGreaterThan(0);
  for (const port of ports) {
    expect(port.id).toBeTruthy();
  }
  expect(graph.paradigm).toBe("functional");
});

test("connecting two ports produces an edge with coherent endpoints", () => {
  const a = useGraphStore
    .getState()
    .addNodeFromSpec(requireNode("data.load_csv"), { x: 0, y: 0 });
  const b = useGraphStore
    .getState()
    .addNodeFromSpec(requireNode("clean.impute_missing"), { x: 200, y: 0 });

  const aPorts = useGraphStore.getState().nodes[a].ports;
  const bPorts = useGraphStore.getState().nodes[b].ports;
  const aOut = aPorts.find((p) => p.direction === "out") ?? aPorts[0];
  const bIn = bPorts.find((p) => p.direction === "in") ?? bPorts[0];
  expect(aOut).toBeDefined();
  expect(bIn).toBeDefined();

  const edgeId = useGraphStore
    .getState()
    .connect({ node_id: a, port_id: aOut.id }, { node_id: b, port_id: bIn.id });
  expect(edgeId).not.toBeNull();

  const graph = useGraphStore.getState().toIR();
  const edgeEntries = Object.entries(graph.edges ?? {});
  expect(edgeEntries).toHaveLength(1);

  const [, edge] = edgeEntries[0];
  expect(Object.keys(graph.nodes ?? {})).toContain(edge.source.node_id);
  expect(Object.keys(graph.nodes ?? {})).toContain(edge.target.node_id);

  const sourceNode = graph.nodes?.[edge.source.node_id];
  const targetNode = graph.nodes?.[edge.target.node_id];
  expect(
    (sourceNode?.ports ?? []).some((p) => p.id === edge.source.port_id),
  ).toBe(true);
  expect(
    (targetNode?.ports ?? []).some((p) => p.id === edge.target.port_id),
  ).toBe(true);
});

test("IR stays referentially coherent after a build", () => {
  const a = useGraphStore
    .getState()
    .addNodeFromSpec(requireNode("data.load_csv"), { x: 0, y: 0 });
  const b = useGraphStore
    .getState()
    .addNodeFromSpec(requireNode("clean.impute_missing"), { x: 200, y: 0 });

  const aPorts = useGraphStore.getState().nodes[a].ports;
  const bPorts = useGraphStore.getState().nodes[b].ports;
  const aOut = aPorts.find((p) => p.direction === "out") ?? aPorts[0];
  const bIn = bPorts.find((p) => p.direction === "in") ?? bPorts[0];
  expect(aOut).toBeDefined();
  expect(bIn).toBeDefined();

  useGraphStore
    .getState()
    .connect({ node_id: a, port_id: aOut.id }, { node_id: b, port_id: bIn.id });

  const graph = useGraphStore.getState().toIR();
  expect(assertCoherent(graph)).toBe(true);
});
