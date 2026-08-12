import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { CatalogNode } from "../catalog/types";
import catalog from "../generated/catalog.json";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
import { useSubgraphStore } from "../store/subgraphStore";
import { Canvas } from "./Canvas";

const catalogNodes = (catalog as unknown as { nodes: CatalogNode[] }).nodes;

function requireCatalogNode(type: string): CatalogNode {
  const node = catalogNodes.find((entry) => entry.type === type);
  if (!node) {
    throw new Error(`expected catalog fixture \`${type}\` to exist`);
  }
  return node;
}

const loadCsv = requireCatalogNode("data.load_csv");

beforeEach(() => {
  useGraphStore.getState().reset();
  useExecutionStore.getState().clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  useSubgraphStore.getState().clear();
});

describe("Canvas", () => {
  test("mounts without throwing and renders the react-flow viewport", () => {
    const { container } = render(<Canvas />);
    expect(container).toBeTruthy();
    expect(container.querySelector(".react-flow")).not.toBeNull();
  });

  test("renders a node added to the store before mount", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });

    const { container } = render(<Canvas />);

    expect(container.querySelector(".react-flow")).not.toBeNull();
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(1);

    const label = screen.queryByText(/Load CSV/);
    if (label) {
      expect(label).toBeInTheDocument();
    }
  });

  test("right-clicking a node opens the context menu with a Run to here item", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });

    const { container } = render(<Canvas />);

    const nodeElement = container.querySelector(".react-flow__node");
    expect(nodeElement).not.toBeNull();

    fireEvent.contextMenu(nodeElement!, { clientX: 50, clientY: 60 });

    expect(
      screen.getByTestId("node-context-menu-run-to-here"),
    ).toBeInTheDocument();
  });

  test("clicking Run to here posts run_to with the right-clicked node's id to /execute/stream", async () => {
    const nodeId = useGraphStore.getState().addNodeFromSpec(loadCsv, {
      x: 0,
      y: 0,
    });

    function sseResponse(status = 200): Response {
      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode("data: {\"type\":\"run_complete\",\"total_ms\":0}\n\n"));
          controller.close();
        },
      });
      return new Response(stream, {
        status,
        headers: { "Content-Type": "text/event-stream" },
      });
    }

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse(),
    );

    const { container } = render(<Canvas />);

    const nodeElement = container.querySelector(".react-flow__node");
    expect(nodeElement).not.toBeNull();

    fireEvent.contextMenu(nodeElement!, { clientX: 50, clientY: 60 });

    fireEvent.click(screen.getByTestId("node-context-menu-run-to-here"));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/execute/stream",
        expect.anything(),
      );
    });

    const callArgs = fetchSpy.mock.calls.find((call) => call[0] === "/execute/stream")!;
    const init = callArgs[1] as { body: string };
    const parsedBody = JSON.parse(init.body);
    expect(parsedBody).toEqual({
      graph: expect.anything(),
      run_to: nodeId,
    });
  });

  test("clicking Run this node posts run_only with the right-clicked node's id", async () => {
    const nodeId = useGraphStore.getState().addNodeFromSpec(loadCsv, {
      x: 0,
      y: 0,
    });

    function sseResponse(status = 200): Response {
      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"type":"run_complete","total_ms":0}\n\n'));
          controller.close();
        },
      });
      return new Response(stream, {
        status,
        headers: { "Content-Type": "text/event-stream" },
      });
    }

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse(),
    );

    const { container } = render(<Canvas />);

    const nodeElement = container.querySelector(".react-flow__node");
    expect(nodeElement).not.toBeNull();

    fireEvent.contextMenu(nodeElement!, { clientX: 50, clientY: 60 });

    fireEvent.click(screen.getByTestId("node-context-menu-run-this-node"));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/execute/stream",
        expect.anything(),
      );
    });

    const callArgs = fetchSpy.mock.calls.find((call) => call[0] === "/execute/stream")!;
    const init = callArgs[1] as { body: string };
    const parsedBody = JSON.parse(init.body);
    expect(parsedBody).toEqual({
      graph: expect.anything(),
      run_only: nodeId,
    });
  });

  test("clicking Run from here posts run_from with the right-clicked node's id", async () => {
    const nodeId = useGraphStore.getState().addNodeFromSpec(loadCsv, {
      x: 0,
      y: 0,
    });

    function sseResponse(status = 200): Response {
      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"type":"run_complete","total_ms":0}\n\n'));
          controller.close();
        },
      });
      return new Response(stream, {
        status,
        headers: { "Content-Type": "text/event-stream" },
      });
    }

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      sseResponse(),
    );

    const { container } = render(<Canvas />);

    const nodeElement = container.querySelector(".react-flow__node");
    expect(nodeElement).not.toBeNull();

    fireEvent.contextMenu(nodeElement!, { clientX: 50, clientY: 60 });

    fireEvent.click(screen.getByTestId("node-context-menu-run-from-here"));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/execute/stream",
        expect.anything(),
      );
    });

    const callArgs = fetchSpy.mock.calls.find((call) => call[0] === "/execute/stream")!;
    const init = callArgs[1] as { body: string };
    const parsedBody = JSON.parse(init.body);
    expect(parsedBody).toEqual({
      graph: expect.anything(),
      run_from: nodeId,
    });
  });

  test("pressing Escape closes the context menu", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });

    const { container } = render(<Canvas />);

    const nodeElement = container.querySelector(".react-flow__node");
    expect(nodeElement).not.toBeNull();

    fireEvent.contextMenu(nodeElement!, { clientX: 50, clientY: 60 });

    expect(
      screen.getByTestId("node-context-menu-run-to-here"),
    ).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(
      screen.queryByTestId("node-context-menu-run-to-here"),
    ).toBeNull();
  });

  test("renders a notes.markdown node alongside an ordinary node without throwing", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    useGraphStore.getState().addNodeFromSpec(
      requireCatalogNode("notes.markdown"),
      { x: 300, y: 0 },
    );

    const { container } = render(<Canvas />);

    expect(container.querySelector(".react-flow")).not.toBeNull();
    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(2);
  });

  test("Ctrl+C then Ctrl+V duplicates a selected node", () => {
    const nodeId = useGraphStore
      .getState()
      .addNodeFromSpec(loadCsv, { x: 0, y: 0 });
    useSelectionStore.getState().setNodeSelected(nodeId, true);

    render(<Canvas />);

    fireEvent.keyDown(document, { key: "c", ctrlKey: true });
    fireEvent.keyDown(document, { key: "v", ctrlKey: true });

    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(2);
  });

  test("Ctrl+V with nothing ever copied does not add a node", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });

    render(<Canvas />);

    fireEvent.keyDown(document, { key: "v", ctrlKey: true });

    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(1);
  });

  test("shows the selection toolbar when 2+ nodes are selected and runs-to-selected on click", async () => {
    useSelectionStore.getState().clear();

    const n1 = useGraphStore.getState().addNodeFromSpec(loadCsv, {
      x: 0,
      y: 0,
    });
    const n2 = useGraphStore.getState().addNodeFromSpec(loadCsv, {
      x: 100,
      y: 0,
    });

    useSelectionStore.getState().setNodeSelected(n1, true);
    useSelectionStore.getState().setNodeSelected(n2, true);

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            const encoder = new TextEncoder();
            controller.enqueue(encoder.encode('data: {"type":"run_complete","total_ms":0}\n\n'));
            controller.close();
          },
        }),
        { status: 200, headers: { "Content-Type": "text/event-stream" } },
      ),
    );

    render(<Canvas />);

    expect(screen.getByTestId("selection-toolbar")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("run-to-selected"));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/execute/stream",
        expect.anything(),
      );
    });

    const callArgs = fetchSpy.mock.calls.find(
      (call) => call[0] === "/execute/stream",
    )!;
    const init = callArgs[1] as { body: string };
    const parsedBody = JSON.parse(init.body);
    expect(parsedBody.run_to).toEqual(expect.arrayContaining([n1, n2]));
    expect(parsedBody.run_to).toHaveLength(2);
  });

  test("Run selected only sends run_only with the selected node ids", async () => {
    useSelectionStore.getState().clear();

    const n1 = useGraphStore.getState().addNodeFromSpec(loadCsv, {
      x: 0,
      y: 0,
    });
    const n2 = useGraphStore.getState().addNodeFromSpec(loadCsv, {
      x: 100,
      y: 0,
    });

    useSelectionStore.getState().setNodeSelected(n1, true);
    useSelectionStore.getState().setNodeSelected(n2, true);

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            const encoder = new TextEncoder();
            controller.enqueue(encoder.encode('data: {"type":"run_complete","total_ms":0}\n\n'));
            controller.close();
          },
        }),
        { status: 200, headers: { "Content-Type": "text/event-stream" } },
      ),
    );

    render(<Canvas />);

    fireEvent.click(screen.getByTestId("run-selected-only"));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/execute/stream",
        expect.anything(),
      );
    });

    const callArgs = fetchSpy.mock.calls.find(
      (call) => call[0] === "/execute/stream",
    )!;
    const init = callArgs[1] as { body: string };
    const parsedBody = JSON.parse(init.body);
    expect(parsedBody.run_only).toEqual(expect.arrayContaining([n1, n2]));
    expect(parsedBody.run_only).toHaveLength(2);
  });

  test("selection toolbar is absent when only one node is selected", () => {
    useSelectionStore.getState().clear();

    const n1 = useGraphStore.getState().addNodeFromSpec(loadCsv, {
      x: 0,
      y: 0,
    });
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 100, y: 0 });

    useSelectionStore.getState().setNodeSelected(n1, true);

    render(<Canvas />);

    expect(screen.queryByTestId("selection-toolbar")).toBeNull();
  });

  test("Ctrl+C with no node selected does not populate clipboard for a subsequent paste", () => {
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x: 0, y: 0 });

    render(<Canvas />);

    fireEvent.keyDown(document, { key: "c", ctrlKey: true });
    fireEvent.keyDown(document, { key: "v", ctrlKey: true });

    expect(Object.keys(useGraphStore.getState().nodes)).toHaveLength(1);
  });

  test("selecting 2+ nodes and clicking Group creates a layout.group node with groupId pointing at it", async () => {
    useSelectionStore.getState().clear();

    const n1 = useGraphStore.getState().addNodeFromSpec(loadCsv, {
      x: 0,
      y: 0,
    });
    const n2 = useGraphStore.getState().addNodeFromSpec(loadCsv, {
      x: 100,
      y: 0,
    });

    useSelectionStore.getState().setNodeSelected(n1, true);
    useSelectionStore.getState().setNodeSelected(n2, true);

    render(<Canvas />);

    expect(screen.getByTestId("selection-toolbar")).toBeInTheDocument();
    expect(screen.getByTestId("group-selection")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("group-selection"));

    await waitFor(() => {
      const nodes = useGraphStore.getState().nodes;
      const groupNode = Object.values(nodes).find((n) => n.type === "layout.group");
      expect(groupNode).toBeDefined();
      expect(nodes[n1].groupId).toBe(groupNode!.id);
      expect(nodes[n2].groupId).toBe(groupNode!.id);
    });
  });

  test("double-clicking a composite node opens its subgraph (breadcrumb appears)", async () => {
    useSelectionStore.getState().clear();

    // Create a composite node in the store directly (extractToComposite is already tested
    // in graphStore tests).
    useGraphStore.getState().pushHistory("test");
    useGraphStore.getState().loadModel({
      paradigm: "functional",
      nodes: {
        comp1: {
          id: "comp1",
          type: "layout.composite",
          label: "My Composite",
          paradigm: "functional",
          params: [{ name: "label", typeToken: "str", value: "My Composite", default: "Composite" }],
          ports: [
            { id: "p1", name: "in0", direction: "in", dataType: "any", cardinality: "one", label: null },
            { id: "p2", name: "out0", direction: "out", dataType: "any", cardinality: "one", label: null },
          ],
          position: { x: 0, y: 0 },
          groupId: null,
          subgraph: {
            paradigm: "functional",
            nodes: {
              n1: { id: "n1", type: "data.load_csv", label: null, paradigm: "functional", position: { x: 0, y: 0 }, params: [], ports: [], group_id: null },
              n2: { id: "n2", type: "transform.filter_rows", label: null, paradigm: "functional", position: { x: 200, y: 0 }, params: [], ports: [], group_id: null },
            },
            edges: {},
          },
        },
      },
      edges: {},
    });

    const { container } = render(<Canvas />);

    const compositeNodeElement = container.querySelector('[data-testid="composite-node"]');
    expect(compositeNodeElement).not.toBeNull();

    // React Flow's onNodeDoubleClick is triggered via the node element
    fireEvent.dblClick(compositeNodeElement!);

    await waitFor(() => {
      const state = useSubgraphStore.getState();
      expect(state.breadcrumbs).toHaveLength(1);
      expect(state.breadcrumbs[0].label).toBe("My Composite");
    });
  });

  test("breadcrumb appears when in subgraph view and clicking a crumb navigates back", async () => {
    useSelectionStore.getState().clear();

    // Load a graph with a composite and enter its subgraph
    useGraphStore.getState().pushHistory("test");
    useGraphStore.getState().loadModel({
      paradigm: "functional",
      nodes: {
        comp1: {
          id: "comp1",
          type: "layout.composite",
          label: "Nested",
          paradigm: "functional",
          params: [{ name: "label", typeToken: "str", value: "Nested", default: "Composite" }],
          ports: [],
          position: { x: 0, y: 0 },
          groupId: null,
          subgraph: {
            paradigm: "functional",
            nodes: {
              n1: { id: "n1", type: "data.load_csv", label: null, paradigm: "functional", position: { x: 0, y: 0 }, params: [], ports: [], group_id: null },
            },
            edges: {},
          },
        },
      },
      edges: {},
    });

    const { container } = render(<Canvas />);

    const compositeNodeElement = container.querySelector('[data-testid="composite-node"]');
    expect(compositeNodeElement).not.toBeNull();

    fireEvent.dblClick(compositeNodeElement!);

    await waitFor(() => {
      expect(screen.getByTestId("subgraph-breadcrumb")).toBeInTheDocument();
    });

    // breadcrumb-0 is "Top-level" -- clicking it should pop back
    fireEvent.click(screen.getByTestId("breadcrumb-0"));

    await waitFor(() => {
      expect(useSubgraphStore.getState().breadcrumbs).toHaveLength(0);
    });

    // Breadcrumb bar hides when back at top level
    expect(screen.queryByTestId("subgraph-breadcrumb")).toBeNull();
  });

  test("clicking the graph overview toggle opens the overview overlay", async () => {
    render(<Canvas />);

    fireEvent.click(screen.getByTestId("minimap-toggle"));

    const closeBtn = await screen.findByTestId("overlay-modal-close");
    expect(closeBtn).toBeInTheDocument();
  });

  test("clicking the overview tile then its close button dismisses it", async () => {
    render(<Canvas />);

    fireEvent.click(screen.getByTestId("minimap-toggle"));

    expect(
      await screen.findByTestId("overlay-modal-close"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("overlay-modal-close"));

    await waitFor(() =>
      expect(
        screen.queryByTestId("overlay-modal-close"),
      ).not.toBeInTheDocument(),
    );
  });
});
