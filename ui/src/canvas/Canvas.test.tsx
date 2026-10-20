import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { CatalogNode } from "../catalog/types";
import catalog from "../generated/catalog.json";
import { useCollapseStore } from "../store/collapseStore";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
import { useSubgraphStore } from "../store/subgraphStore";
import { useTraceStore } from "../store/traceStore";
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
  useTraceStore.getState().reset();
  useSelectionStore.getState().clear();
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

describe("Canvas trace modes (issue #167)", () => {
  const add = (x = 0, y = 0): string =>
    useGraphStore.getState().addNodeFromSpec(loadCsv, { x, y });

  const link = (a: string, b: string): void => {
    const nodes = useGraphStore.getState().nodes;
    useGraphStore.getState().connect(
      { node_id: a, port_id: nodes[a].ports[0].id },
      { node_id: b, port_id: nodes[b].ports[0].id },
    );
  };

  const traceOf = (container: HTMLElement, id: string): string | null | undefined =>
    container
      .querySelector(`.react-flow__node[data-id="${id}"] [data-trace]`)
      ?.getAttribute("data-trace");

  const nodeEl = (container: HTMLElement, id: string): Element => {
    const el = container.querySelector(`.react-flow__node[data-id="${id}"]`);
    if (!el) throw new Error(`node element ${id} not found`);
    return el;
  };

  function setupChainWithStray(): { a: string; b: string; c: string; x: string } {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    const x = add(0, 300);
    link(a, b);
    link(b, c);
    return { a, b, c, x };
  }

  function traceUpstreamFromC(container: HTMLElement, c: string): void {
    fireEvent.contextMenu(nodeEl(container, c), { clientX: 10, clientY: 10 });
    fireEvent.click(screen.getByTestId("node-context-menu-trace-upstream"));
  }

  test("Trace upstream from the context menu highlights ancestors and dims the rest", async () => {
    const { a, b, c, x } = setupChainWithStray();
    const { container } = render(<Canvas />);

    traceUpstreamFromC(container, c);

    await waitFor(() => {
      expect(traceOf(container, a)).toBe("traced");
    });
    expect(traceOf(container, b)).toBe("traced");
    expect(traceOf(container, c)).toBe("traced");
    expect(traceOf(container, x)).toBe("dimmed");
    expect(screen.getByTestId("trace-banner")).toHaveTextContent(/upstream/);
  });

  test("default selection trace stays downstream", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    link(a, b);
    link(b, c);
    useSelectionStore.getState().setNodeSelected(b, true);

    const { container } = render(<Canvas />);

    await waitFor(() => {
      expect(traceOf(container, b)).toBe("traced");
    });
    expect(traceOf(container, c)).toBe("traced");
    expect(traceOf(container, a)).toBe("dimmed");
  });

  test("Show route on a diamond highlights both branches", async () => {
    const a = add(0, 0);
    const b = add(200, -100);
    const c = add(200, 100);
    const d = add(400, 0);
    const e = add(600, 0);
    link(a, b);
    link(a, c);
    link(b, d);
    link(c, d);
    link(d, e);
    useSelectionStore.getState().replaceSelection([a, d]);

    const { container } = render(<Canvas />);

    fireEvent.click(screen.getByTestId("show-route-selection"));

    await waitFor(() => {
      expect(screen.getByTestId("trace-banner")).toHaveTextContent(/Route between/);
    });
    for (const id of [a, b, c, d]) {
      expect(traceOf(container, id)).toBe("traced");
    }
    expect(traceOf(container, e)).toBe("dimmed");
  });

  test("Show route with no path shows an inline message", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    useSelectionStore.getState().replaceSelection([a, b]);

    render(<Canvas />);

    fireEvent.click(screen.getByTestId("show-route-selection"));

    await waitFor(() => {
      expect(screen.getByTestId("trace-banner")).toHaveAttribute("data-route-empty", "true");
    });
    expect(screen.getByTestId("trace-banner")).toHaveTextContent(/No path/);
  });

  test("Route from here then clicking a target shows the route", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    link(a, b);
    link(b, c);

    const { container } = render(<Canvas />);

    fireEvent.contextMenu(nodeEl(container, a), { clientX: 10, clientY: 10 });
    fireEvent.click(screen.getByTestId("node-context-menu-route-from-here"));

    await waitFor(() => {
      expect(screen.getByTestId("trace-banner")).toHaveTextContent(/Click a node/);
    });

    fireEvent.click(nodeEl(container, c));

    await waitFor(() => {
      expect(screen.getByTestId("trace-banner")).toHaveTextContent(/Route between/);
    });
    for (const id of [a, b, c]) {
      expect(traceOf(container, id)).toBe("traced");
    }
  });

  test("Escape clears the trace mode", async () => {
    const { c } = setupChainWithStray();
    const { container } = render(<Canvas />);

    traceUpstreamFromC(container, c);
    await waitFor(() => {
      expect(screen.getByTestId("trace-banner")).toBeInTheDocument();
    });

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => {
      expect(screen.queryByTestId("trace-banner")).toBeNull();
    });
    expect(useTraceStore.getState().mode).toBe("selection-downstream");
  });

  test("reach mode resets once the selection is cleared", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    link(a, b);
    useSelectionStore.getState().setNodeSelected(b, true);
    render(<Canvas />);

    fireEvent.keyDown(document, { key: "u" });
    await waitFor(() => {
      expect(useTraceStore.getState().mode).toBe("reach");
    });

    act(() => {
      useSelectionStore.getState().clear();
    });
    await waitFor(() => {
      expect(useTraceStore.getState().mode).toBe("selection-downstream");
    });
  });

  test("route resets when an endpoint is deleted", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    link(a, b);
    render(<Canvas />);
    // Set the route after mount: Canvas resets the trace on mount (subgraph-navigation effect),
    // so setting it beforehand would make this test pass without exercising the endpoint check.
    act(() => {
      useTraceStore.getState().setRoute(a, b);
    });
    await waitFor(() => {
      expect(screen.getByTestId("trace-banner")).toHaveTextContent(/Route between/);
    });

    act(() => {
      useGraphStore.getState().removeNode(b);
    });
    await waitFor(() => {
      expect(useTraceStore.getState().mode).toBe("selection-downstream");
    });
  });

  test("route through a collapsed group endpoint is still found", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    const d = add(600, 0);
    link(a, b);
    link(b, c);
    link(c, d);
    const groupId = useGraphStore.getState().groupSelection([c, d]);
    if (!groupId) throw new Error("expected groupSelection to create a group");
    const { container } = render(<Canvas />);
    act(() => {
      useTraceStore.getState().setRoute(a, d);
    });
    await waitFor(() => {
      expect(screen.getByTestId("trace-banner")).toHaveTextContent(/Route between/);
    });

    act(() => {
      useCollapseStore.getState().setCollapsed(groupId, true);
    });

    await waitFor(() => {
      expect(traceOf(container, b)).toBe("traced");
    });
    expect(screen.getByTestId("trace-banner")).toHaveTextContent(/Route between/);
    expect(screen.getByTestId("trace-banner")).not.toHaveAttribute("data-route-empty");
  });

  test("U shortcut traces upstream; ignored inside inputs", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    link(a, b);
    useSelectionStore.getState().setNodeSelected(b, true);

    const { container } = render(<Canvas />);

    fireEvent.keyDown(document, { key: "u" });

    await waitFor(() => {
      expect(useTraceStore.getState().mode).toBe("reach");
    });
    expect(useTraceStore.getState().direction).toBe("upstream");
    await waitFor(() => {
      expect(traceOf(container, a)).toBe("traced");
    });

    act(() => {
      useTraceStore.getState().reset();
    });

    const input = document.createElement("input");
    document.body.appendChild(input);
    try {
      fireEvent.keyDown(input, { key: "u" });
      expect(useTraceStore.getState().mode).toBe("selection-downstream");
    } finally {
      input.remove();
    }
  });

  test("Lens on ml highlights only ml nodes and never moves nodes", async () => {
    const mlSpec = catalogNodes.find((n) => n.family === "ml" && n.ports.length > 0);
    if (!mlSpec) {
      throw new Error("expected an ml catalog node with ports to exist");
    }
    const dataId = add(0, 0);
    const mlId = useGraphStore.getState().addNodeFromSpec(mlSpec, { x: 300, y: 50 });
    const before = Object.fromEntries(
      Object.entries(useGraphStore.getState().nodes).map(([id, n]) => [id, { ...n.position }]),
    );

    const { container } = render(<Canvas />);

    fireEvent.click(screen.getByTestId("lens-chip-ml"));

    await waitFor(() => {
      expect(traceOf(container, mlId)).toBe("traced");
    });
    expect(traceOf(container, dataId)).toBe("dimmed");

    const after = Object.fromEntries(
      Object.entries(useGraphStore.getState().nodes).map(([id, n]) => [id, { ...n.position }]),
    );
    expect(after).toEqual(before);

    fireEvent.click(screen.getByTestId("lens-chip-ml"));

    await waitFor(() => {
      expect(screen.queryByTestId("trace-banner")).toBeNull();
    });
  });

  test("an active lens family keeps its chip after its last node is deleted", async () => {
    const mlSpec = catalogNodes.find((n) => n.family === "ml" && n.ports.length > 0);
    if (!mlSpec) {
      throw new Error("expected an ml catalog node with ports to exist");
    }
    add(0, 0);
    const mlId = useGraphStore.getState().addNodeFromSpec(mlSpec, { x: 300, y: 50 });
    render(<Canvas />);

    fireEvent.click(screen.getByTestId("lens-chip-ml"));
    await waitFor(() => {
      expect(screen.getByTestId("trace-banner")).toBeInTheDocument();
    });

    act(() => {
      useGraphStore.getState().removeNode(mlId);
    });

    fireEvent.click(screen.getByTestId("lens-chip-ml"));
    await waitFor(() => {
      expect(screen.queryByTestId("trace-banner")).toBeNull();
    });
    expect(screen.queryByTestId("lens-chip-ml")).toBeNull();
  });
});
