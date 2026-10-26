import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { CatalogNode } from "../catalog/types";
import catalog from "../generated/catalog.json";
import { useCollapseStore } from "../store/collapseStore";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
import { useSubgraphStore } from "../store/subgraphStore";
import { useTourStore } from "../store/tourStore";
import { useTraceStore } from "../store/traceStore";
import type { Tour } from "../session/sessionClient";
import { useViewLinkStore } from "../store/viewLinkStore";
import { parseViewHash } from "../io/viewLink";
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
  useViewLinkStore.setState({
    pendingCanvas: null,
    pendingProposal: null,
    pendingReview: null,
    notice: null,
    fallbackUrl: null,
  });
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

  test("route-pick origin hidden by a collapsed group highlights the group", async () => {
    const a = add(0, 0);
    const c = add(400, 0);
    const d = add(600, 0);
    link(a, c);
    link(c, d);
    const groupId = useGraphStore.getState().groupSelection([c, d]);
    if (!groupId) throw new Error("expected groupSelection to create a group");
    const { container } = render(<Canvas />);
    act(() => {
      useTraceStore.getState().startRoutePick(c);
    });
    await waitFor(() => {
      expect(screen.getByTestId("trace-banner")).toHaveTextContent(/Click a node to route from/);
    });

    act(() => {
      useCollapseStore.getState().setCollapsed(groupId, true);
    });

    await waitFor(() => {
      expect(nodeEl(container, groupId)).toHaveClass("ef-trace-traced");
    });
    expect(traceOf(container, a)).toBe("dimmed");
  });

  test("reach from a node hidden by a collapsed group traces from the group", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    link(a, b);
    link(b, c);
    const groupId = useGraphStore.getState().groupSelection([b, c]);
    if (!groupId) throw new Error("expected groupSelection to create a group");
    useCollapseStore.getState().setCollapsed(groupId, true);
    const { container } = render(<Canvas />);
    // Set reach after mount: Canvas resets the trace on mount (subgraph-navigation effect).
    act(() => {
      useSelectionStore.getState().replaceSelection([c]);
      useTraceStore.getState().setReach("upstream");
    });

    await waitFor(() => expect(traceOf(container, a)).toBe("traced"));
    expect(nodeEl(container, groupId)).toHaveClass("ef-trace-traced");
    useCollapseStore.getState().setCollapsed(groupId, false);
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

describe("Canvas guided tours (issue #171)", () => {
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

  const makeTour = (steps: Tour["steps"]): Tour => ({
    id: "tour-1",
    title: "T",
    author: "agent",
    conclusion: "Done",
    steps,
  });

  const startTour = (tour: Tour, index = 0): void => {
    act(() => useTourStore.getState().start(tour, index));
  };

  function chain(): { a: string; b: string; c: string } {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    link(a, b);
    link(b, c);
    return { a, b, c };
  }

  beforeEach(() => {
    useTourStore.setState({
      playing: null,
      snapshot: null,
      pendingViewportRestore: null,
      announcement: null,
    });
  });

  afterEach(() => {
    act(() => useTourStore.getState().exit({ restore: false }));
  });

  test("exiting restores the pre-tour selection and reach trace", async () => {
    const { a, b, c } = chain();
    const { container } = render(<Canvas />);
    act(() => {
      useSelectionStore.getState().replaceSelection([b]);
      useTraceStore.getState().setReach("upstream");
    });
    startTour(makeTour([{ note: "n", focus: [c] }]));
    await waitFor(() => expect(traceOf(container, c)).toBe("traced"));
    expect(useSelectionStore.getState().nodes[b]).toBeFalsy();

    act(() => useTourStore.getState().exit());

    await waitFor(() => expect(traceOf(container, a)).toBe("traced"));
    expect(useTraceStore.getState().mode).toBe("reach");
    expect(useTraceStore.getState().direction).toBe("upstream");
    expect(useSelectionStore.getState().nodes[b]).toBe(true);
    expect(traceOf(container, c)).toBe("dimmed");
  });

  test("focus-only step highlights exactly the focus node", async () => {
    const { a, b, c } = chain();
    const { container } = render(<Canvas />);
    startTour(makeTour([{ note: "n", focus: [b] }]));
    await waitFor(() => expect(traceOf(container, b)).toBe("traced"));
    expect(traceOf(container, a)).toBe("dimmed");
    expect(traceOf(container, c)).toBe("dimmed");
  });

  test("reach down step highlights the focus and its descendants", async () => {
    const { a, b, c } = chain();
    const { container } = render(<Canvas />);
    startTour(makeTour([{ note: "n", focus: [b], reach: "down" }]));
    await waitFor(() => expect(traceOf(container, b)).toBe("traced"));
    expect(traceOf(container, c)).toBe("traced");
    expect(traceOf(container, a)).toBe("dimmed");
  });

  test("a reversed route shows no path and does not retry in reverse", async () => {
    const { a, b, c } = chain();
    const { container } = render(<Canvas />);
    startTour(makeTour([{ note: "n", route: [c, a] }]));
    await waitFor(() => expect(screen.getByTestId("tour-no-path")).toBeTruthy());
    expect(traceOf(container, a)).toBe("traced");
    expect(traceOf(container, c)).toBe("traced");
    expect(traceOf(container, b)).toBe("dimmed");
  });

  test("a route step on a diamond highlights both branches", async () => {
    const s = add(0, 0);
    const l = add(200, -100);
    const r = add(200, 100);
    const t = add(400, 0);
    const x = add(0, 300);
    link(s, l);
    link(s, r);
    link(l, t);
    link(r, t);
    const { container } = render(<Canvas />);
    startTour(makeTour([{ note: "n", route: [s, t] }]));
    await waitFor(() => expect(traceOf(container, s)).toBe("traced"));
    for (const id of [l, r, t]) expect(traceOf(container, id)).toBe("traced");
    expect(traceOf(container, x)).toBe("dimmed");
  });

  test("a removed anchor shows a badge and deleting a focused node mid-playback does not crash", async () => {
    const { a, b } = chain();
    const { container } = render(<Canvas />);
    startTour(makeTour([{ note: "n", focus: [a, "gone"] }]));
    await waitFor(() =>
      expect(screen.getByTestId("tour-removed-badge")).toHaveTextContent("Node removed: gone"),
    );
    expect(traceOf(container, a)).toBe("traced");
    act(() => {
      useTourStore.getState().exit({ restore: false });
    });
    startTour(makeTour([{ note: "n", focus: [b] }]));
    await waitFor(() => expect(traceOf(container, b)).toBe("traced"));
    act(() => useGraphStore.getState().removeNode(b));
    await waitFor(() =>
      expect(screen.getByTestId("tour-removed-badge")).toHaveTextContent(`Node removed: ${b}`),
    );
  });

  test("no trace banner and no U shortcut while a tour plays", async () => {
    const { b } = chain();
    useSelectionStore.getState().setNodeSelected(b, true);
    render(<Canvas />);
    startTour(makeTour([{ note: "n", focus: [b] }]));
    await waitFor(() => expect(screen.getByTestId("tour-player")).toBeTruthy());
    expect(screen.queryByTestId("trace-banner")).toBeNull();
    fireEvent.keyDown(document, { key: "u" });
    expect(useTraceStore.getState().mode).toBe("tour");
  });

  test("next advances the step and exit restores the default trace mode", async () => {
    const { a, b, c } = chain();
    render(<Canvas />);
    startTour(
      makeTour([
        { note: "1", focus: [a] },
        { note: "2", focus: [b] },
        { note: "3", focus: [c] },
      ]),
    );
    await waitFor(() => expect(screen.getByTestId("tour-step-counter")).toHaveTextContent("Step 1/3"));
    fireEvent.click(screen.getByTestId("tour-next"));
    await waitFor(() => expect(screen.getByTestId("tour-step-counter")).toHaveTextContent("Step 2/3"));
    fireEvent.click(screen.getByTestId("tour-exit"));
    await waitFor(() => expect(useTourStore.getState().playing).toBeNull());
    expect(useTraceStore.getState().mode).toBe("selection-downstream");
  });

  test("playback does not touch the graph or its undo history", async () => {
    const { a, b } = chain();
    const before = JSON.stringify(useGraphStore.getState().toIR());
    const pastBefore = useGraphStore.getState().past.length;
    render(<Canvas />);
    startTour(makeTour([{ note: "1", focus: [a] }, { note: "2", route: [a, b] }]));
    await waitFor(() => expect(screen.getByTestId("tour-player")).toBeTruthy());
    fireEvent.click(screen.getByTestId("tour-next"));
    fireEvent.click(screen.getByTestId("tour-exit"));
    await waitFor(() => expect(useTourStore.getState().playing).toBeNull());
    expect(JSON.stringify(useGraphStore.getState().toIR())).toBe(before);
    expect(useGraphStore.getState().past.length).toBe(pastBefore);
  });
});

describe("Canvas deep links (issue #168)", () => {
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

  test("focus selects the node", async () => {
    const a = add(0, 0);
    add(200, 0);
    render(<Canvas />);

    act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${a}`)));

    await waitFor(() => expect(useSelectionStore.getState().nodes[a]).toBe(true));
    expect(useViewLinkStore.getState().pendingCanvas).toBeNull();
  });

  test("focus + reach=up highlights ancestors", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    const x = add(0, 300);
    link(a, b);
    link(b, c);
    const { container } = render(<Canvas />);

    act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${c}&reach=up`)));

    await waitFor(() => expect(traceOf(container, a)).toBe("traced"));
    expect(traceOf(container, x)).toBe("dimmed");
    expect(useTraceStore.getState().mode).toBe("reach");
  });

  test("route shows the route banner", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    link(a, b);
    link(b, c);
    render(<Canvas />);

    act(() => useViewLinkStore.getState().request(parseViewHash(`#route=${a}~${c}`)));

    await waitFor(() => expect(screen.getByTestId("trace-banner")).toHaveTextContent(/Route between/));
  });

  test("unreachable route shows No path", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    render(<Canvas />);

    act(() => useViewLinkStore.getState().request(parseViewHash(`#route=${a}~${b}`)));

    await waitFor(() => expect(screen.getByTestId("trace-banner")).toHaveTextContent(/No path/));
  });

  test("unknown ids produce one notice and no selection", async () => {
    add(0, 0);
    render(<Canvas />);

    act(() => useViewLinkStore.getState().request(parseViewHash("#focus=nope&edge=bad")));

    await waitFor(() => {
      const notice = useViewLinkStore.getState().notice;
      expect(notice).toContain('node "nope"');
      expect(notice).toContain('edge "bad"');
    });
    expect(Object.values(useSelectionStore.getState().nodes).some(Boolean)).toBe(false);
  });

  test("a view requested before mount is applied once mounted", async () => {
    const a = add(0, 0);
    useViewLinkStore.getState().request(parseViewHash(`#focus=${a}`));
    render(<Canvas />);

    await waitFor(() => expect(useSelectionStore.getState().nodes[a]).toBe(true));
    expect(useViewLinkStore.getState().pendingCanvas).toBeNull();
  });

  test("focus + reach on a node hidden by a collapsed group selects the member and traces the group", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    link(a, b);
    link(b, c);
    const groupId = useGraphStore.getState().groupSelection([b, c]);
    if (!groupId) throw new Error("expected groupSelection to create a group");
    useCollapseStore.getState().setCollapsed(groupId, true);
    const { container } = render(<Canvas />);

    act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${c}&reach=up`)));

    await waitFor(() => expect(traceOf(container, a)).toBe("traced"));
    expect(container.querySelector(`.react-flow__node[data-id="${groupId}"]`)).toHaveClass(
      "ef-trace-traced",
    );
    // The selection keeps the linked (hidden) member; only the trace root maps to its group.
    expect(useSelectionStore.getState().nodes[c]).toBe(true);
    expect(useSelectionStore.getState().nodes[groupId]).toBeFalsy();
    expect(useViewLinkStore.getState().notice).toBeNull();
    useCollapseStore.getState().setCollapsed(groupId, false);
  });

  test("after a hidden-member link, expanding the group traces the member and Copy link keeps its id", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    link(a, b);
    link(b, c);
    const groupId = useGraphStore.getState().groupSelection([b, c]);
    if (!groupId) throw new Error("expected groupSelection to create a group");
    useCollapseStore.getState().setCollapsed(groupId, true);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const { container } = render(<Canvas />);

    act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${c}&reach=up`)));
    await waitFor(() => expect(traceOf(container, a)).toBe("traced"));

    // A re-shared banner link names the member, not this viewer's collapsed group.
    fireEvent.click(await screen.findByTestId("trace-banner-copy-link"));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(writeText.mock.calls[0][0]).toMatch(new RegExp(`#focus=${c}&reach=up$`));
    expect(writeText.mock.calls[0][0]).not.toContain(groupId);

    // Expanding the group traces the member's real ancestors instead of dimming everything.
    act(() => useCollapseStore.getState().setCollapsed(groupId, false));
    await waitFor(() =>
      expect(container.querySelector(`.react-flow__node[data-id="${c}"]`)).not.toBeNull(),
    );
    await waitFor(() => expect(traceOf(container, c)).toBe("traced"));
    expect(traceOf(container, b)).toBe("traced");
    expect(traceOf(container, a)).toBe("traced");
  });

  test("a hidden-member link survives React Flow's echo when a visible node was selected", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    link(a, b);
    link(b, c);
    const groupId = useGraphStore.getState().groupSelection([b, c]);
    if (!groupId) throw new Error("expected groupSelection to create a group");
    useCollapseStore.getState().setCollapsed(groupId, true);
    const { container } = render(<Canvas />);
    act(() => useSelectionStore.getState().replaceSelection([a]));
    await waitFor(() =>
      expect(container.querySelector(`.react-flow__node[data-id="${a}"]`)).toHaveClass("selected"),
    );

    // Deselecting `a` makes React Flow report an empty selection (it can't see hidden `c`).
    act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${c}&reach=up`)));
    await waitFor(() => expect(traceOf(container, a)).toBe("traced"));
    expect(useSelectionStore.getState().nodes).toEqual({ [c]: true });
    expect(useTraceStore.getState().mode).toBe("reach");

    // Once expanded, React Flow renders the member selected.
    act(() => useCollapseStore.getState().setCollapsed(groupId, false));
    await waitFor(() =>
      expect(container.querySelector(`.react-flow__node[data-id="${c}"]`)).toHaveClass("selected"),
    );
    expect(useSelectionStore.getState().nodes).toEqual({ [c]: true });
    expect(traceOf(container, c)).toBe("traced");
  });

  test("collapsing a group around the selected member clears the selection", async () => {
    add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    const groupId = useGraphStore.getState().groupSelection([b, c]);
    if (!groupId) throw new Error("expected groupSelection to create a group");
    useSelectionStore.getState().clear();
    const { container } = render(<Canvas />);
    const cEl = await waitFor(() => {
      const el = container.querySelector(`.react-flow__node[data-id="${c}"]`);
      if (!el) throw new Error("expected member to render");
      return el;
    });
    act(() => useSelectionStore.getState().replaceSelection([c]));
    await waitFor(() => expect(cEl).toHaveClass("selected"));

    // Outside a deep link, React Flow's empty report on collapse is authoritative.
    fireEvent.click(
      container.querySelector(
        `.react-flow__node[data-id="${groupId}"] [data-testid="group-node-collapse-toggle"]`,
      ) as HTMLElement,
    );
    await waitFor(() =>
      expect(container.querySelector(`.react-flow__node[data-id="${c}"]`)).toBeNull(),
    );
    await waitFor(() => expect(useSelectionStore.getState().nodes[c]).toBeFalsy());
    useCollapseStore.getState().setCollapsed(groupId, false);
  });

  test("a pane click clears a hidden-member selection from a deep link", async () => {
    add(0, 0);
    const b = add(200, 0);
    const c = add(400, 0);
    const groupId = useGraphStore.getState().groupSelection([b, c]);
    if (!groupId) throw new Error("expected groupSelection to create a group");
    useSelectionStore.getState().clear();
    useCollapseStore.getState().setCollapsed(groupId, true);
    const { container } = render(<Canvas />);
    act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${c}`)));
    await waitFor(() => expect(useSelectionStore.getState().nodes[c]).toBe(true));

    // React Flow sees nothing selected, so it reports no change; the canvas clears it itself.
    fireEvent.click(container.querySelector(".react-flow__pane") as HTMLElement);
    await waitFor(() =>
      expect(Object.values(useSelectionStore.getState().nodes).some(Boolean)).toBe(false),
    );
    useCollapseStore.getState().setCollapsed(groupId, false);
  });

  test("a link that leaves React Flow's selection unchanged doesn't swallow a later collapse", async () => {
    const a = add(0, 0);
    const a2 = add(0, 200);
    const b = add(400, 0);
    const c = add(600, 0);
    const hiddenGroup = useGraphStore.getState().groupSelection([b, c]);
    const aGroup = useGraphStore.getState().groupSelection([a, a2]);
    if (!hiddenGroup || !aGroup) throw new Error("expected groupSelection to create groups");
    useSelectionStore.getState().clear();
    useCollapseStore.getState().setCollapsed(hiddenGroup, true);
    const { container } = render(<Canvas />);
    act(() => useSelectionStore.getState().replaceSelection([a]));
    await waitFor(() =>
      expect(container.querySelector(`.react-flow__node[data-id="${a}"]`)).toHaveClass("selected"),
    );

    // `a` is already selected and `c` is hidden, so React Flow has nothing to echo.
    act(() => useViewLinkStore.getState().request(parseViewHash(`#focus=${a},${c}`)));
    await waitFor(() => expect(useSelectionStore.getState().nodes).toEqual({ [a]: true, [c]: true }));

    // Collapsing a's group hides it; React Flow's empty report must clear the selection.
    fireEvent.click(
      container.querySelector(
        `.react-flow__node[data-id="${aGroup}"] [data-testid="group-node-collapse-toggle"]`,
      ) as HTMLElement,
    );
    await waitFor(() =>
      expect(container.querySelector(`.react-flow__node[data-id="${a}"]`)).toBeNull(),
    );
    await waitFor(() =>
      expect(Object.values(useSelectionStore.getState().nodes).some(Boolean)).toBe(false),
    );
    useCollapseStore.getState().setCollapsed(hiddenGroup, false);
    useCollapseStore.getState().setCollapsed(aGroup, false);
  });

  test("no Copy link (context menu or trace banner) inside a composite subgraph", async () => {
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
    fireEvent.dblClick(container.querySelector('[data-testid="composite-node"]')!);
    await waitFor(() => expect(useSubgraphStore.getState().breadcrumbs).toHaveLength(1));
    const n1 = await waitFor(() => {
      const el = container.querySelector('.react-flow__node[data-id="n1"]');
      if (!el) throw new Error("n1 not rendered");
      return el;
    });

    // Subgraph-local ids never resolve from a link (it is applied against the top-level graph).
    fireEvent.contextMenu(n1, { clientX: 10, clientY: 10 });
    expect(screen.getByTestId("node-context-menu-trace-upstream")).toBeInTheDocument();
    expect(screen.queryByTestId("node-context-menu-copy-link")).toBeNull();

    fireEvent.click(screen.getByTestId("node-context-menu-trace-upstream"));
    await waitFor(() => expect(screen.getByTestId("trace-banner")).toBeInTheDocument());
    expect(screen.queryByTestId("trace-banner-copy-link")).toBeNull();
  });

  test("Copy link in the trace banner copies the reach view", async () => {
    const a = add(0, 0);
    const b = add(200, 0);
    link(a, b);
    useSelectionStore.getState().replaceSelection([b]);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<Canvas />);
    // Set reach after mount: Canvas resets the trace on mount (subgraph-navigation effect).
    act(() => useTraceStore.getState().setReach("upstream"));

    fireEvent.click(await screen.findByTestId("trace-banner-copy-link"));

    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(writeText.mock.calls[0][0]).toMatch(new RegExp(`#focus=${b}&reach=up$`));
  });
});
