import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { LineagePanel } from "./LineagePanel";

beforeEach(() => {
  useGraphStore.getState().reset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function addNode(): string {
  return useGraphStore.getState().addNodeFromSpec(
    {
      type: "t",
      version: 1,
      family: "f",
      label: "L",
      paradigm: "functional",
      ports: [],
      params: [],
    },
    { x: 0, y: 0 },
  );
}

test("renders the traced chain with a target marker", async () => {
  const nodeId = addNode();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        lineage: {
          target_node_id: nodeId,
          nodes: [
            { node_id: "node:1", node_type: "data.load_csv", label: "Load CSV" },
            { node_id: "node:2", node_type: "clean.parse_dates", label: null },
            { node_id: nodeId, node_type: "research.assert_data", label: "Gate" },
          ],
          edges: [
            {
              source_node_id: "node:1",
              source_port: "frame",
              target_node_id: "node:2",
              target_port: "frame",
            },
            {
              source_node_id: "node:2",
              source_port: "frame",
              target_node_id: nodeId,
              target_port: "frame",
            },
          ],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  render(<LineagePanel nodeId={nodeId} debounceMs={0} />);

  await waitFor(() => expect(screen.getByTestId("lineage-chain")).toBeInTheDocument());

  expect(screen.getAllByTestId(/^lineage-(node|target)$/)).toHaveLength(3);
  expect(screen.getByTestId("lineage-target")).toHaveTextContent("Gate");
  expect(screen.getByTestId("lineage-summary")).toHaveTextContent("3");
  expect(screen.getByTestId("lineage-summary")).toHaveTextContent("2");
});

test("falls back to node_type when label is null", async () => {
  const nodeId = addNode();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        lineage: {
          target_node_id: nodeId,
          nodes: [{ node_id: nodeId, node_type: "clean.parse_dates", label: null }],
          edges: [],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  render(<LineagePanel nodeId={nodeId} debounceMs={0} />);

  await waitFor(() =>
    expect(screen.getByTestId("lineage-target")).toHaveTextContent("clean.parse_dates"),
  );
});

test("renders the port hop between consecutive nodes", async () => {
  const nodeId = addNode();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        lineage: {
          target_node_id: nodeId,
          nodes: [
            { node_id: "node:1", node_type: "data.load_csv", label: "Load CSV" },
            { node_id: nodeId, node_type: "research.assert_data", label: "Gate" },
          ],
          edges: [
            {
              source_node_id: "node:1",
              source_port: "frame",
              target_node_id: nodeId,
              target_port: "frame",
            },
          ],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  render(<LineagePanel nodeId={nodeId} debounceMs={0} />);

  await waitFor(() => {
    const hop = screen.getByTestId("lineage-hop");
    expect(hop).toHaveTextContent("frame");
    expect(hop).toHaveTextContent("frame");
  });
});

test("shows the no-selection empty state and never calls fetch", () => {
  addNode();
  const f = vi.spyOn(globalThis, "fetch");

  render(<LineagePanel nodeId={null} debounceMs={0} />);

  expect(screen.getByTestId("lineage-empty-no-selection")).toBeInTheDocument();
  expect(f).not.toHaveBeenCalled();
});

test("shows the empty-graph state and never calls fetch", () => {
  const f = vi.spyOn(globalThis, "fetch");

  render(<LineagePanel nodeId="node:1" debounceMs={0} />);

  expect(screen.getByTestId("lineage-empty")).toBeInTheDocument();
  expect(f).not.toHaveBeenCalled();
});

test("renders the server's error message on a non-2xx", async () => {
  const nodeId = addNode();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ error: "CodegenError: boom" }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<LineagePanel nodeId={nodeId} debounceMs={0} />);

  await waitFor(() => expect(screen.getByTestId("lineage-error")).toHaveTextContent("boom"));
});

test("renders a fetch failure message", async () => {
  const nodeId = addNode();
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));

  render(<LineagePanel nodeId={nodeId} debounceMs={0} />);

  await waitFor(() =>
    expect(screen.getByTestId("lineage-error")).toHaveTextContent("Could not reach server"),
  );
});

test("renders a single-node lineage with no hops", async () => {
  const nodeId = addNode();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        lineage: {
          target_node_id: nodeId,
          nodes: [{ node_id: nodeId, node_type: "research.assert_data", label: "Gate" }],
          edges: [],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  render(<LineagePanel nodeId={nodeId} debounceMs={0} />);

  await waitFor(() => expect(screen.getByTestId("lineage-chain")).toBeInTheDocument());

  expect(screen.queryAllByTestId("lineage-hop")).toHaveLength(0);
});
