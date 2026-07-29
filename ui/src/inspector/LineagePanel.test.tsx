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

test("resolves hop port ids to the node's port names, not raw ids", async () => {
  // The server's `/lineage` DTO carries port *ids* (opaque UUIDs -- see
  // `emergentflow/research/lineage.py`), never port names, mirroring how the IR keys edges
  // by id everywhere else. Build real nodes with named ports via `addNodeFromSpec` (which
  // mints a fresh UUID per port, just like the server) so this test fails if the panel ever
  // regresses to rendering the id verbatim.
  const upstreamId = useGraphStore.getState().addNodeFromSpec(
    {
      type: "data.load_csv",
      version: 1,
      family: "data",
      label: "Load CSV",
      paradigm: "functional",
      ports: [{ name: "frame", direction: "out", data_type: "DataFrame" }],
      params: [],
    },
    { x: 0, y: 0 },
  );
  const targetId = useGraphStore.getState().addNodeFromSpec(
    {
      type: "research.assert_data",
      version: 1,
      family: "research",
      label: "Gate",
      paradigm: "functional",
      ports: [{ name: "frame", direction: "in", data_type: "DataFrame" }],
      params: [],
    },
    { x: 100, y: 0 },
  );
  const upstreamPortId = useGraphStore.getState().nodes[upstreamId].ports[0].id;
  const targetPortId = useGraphStore.getState().nodes[targetId].ports[0].id;

  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        lineage: {
          target_node_id: targetId,
          nodes: [
            { node_id: upstreamId, node_type: "data.load_csv", label: "Load CSV" },
            { node_id: targetId, node_type: "research.assert_data", label: "Gate" },
          ],
          edges: [
            {
              source_node_id: upstreamId,
              source_port: upstreamPortId,
              target_node_id: targetId,
              target_port: targetPortId,
            },
          ],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  render(<LineagePanel nodeId={targetId} debounceMs={0} />);

  await waitFor(() => {
    const hop = screen.getByTestId("lineage-hop");
    expect(hop).toHaveTextContent("frame → frame");
    expect(hop).not.toHaveTextContent(upstreamPortId);
    expect(hop).not.toHaveTextContent(targetPortId);
  });
});

test("falls back to the raw port id when the port is no longer in the graph", async () => {
  // A lineage can outlive the graph shape it was traced from (the node was deleted between
  // the trace and the render). Rendering blank would be worse than showing the id.
  const nodeId = addNode();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        lineage: {
          target_node_id: nodeId,
          nodes: [
            { node_id: "node:gone", node_type: "data.load_csv", label: "Load CSV" },
            { node_id: nodeId, node_type: "research.assert_data", label: "Gate" },
          ],
          edges: [
            {
              source_node_id: "node:gone",
              source_port: "port:vanished",
              target_node_id: nodeId,
              target_port: "port:also-vanished",
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
    expect(hop).toHaveTextContent("port:vanished");
    expect(hop).toHaveTextContent("port:also-vanished");
  });
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
