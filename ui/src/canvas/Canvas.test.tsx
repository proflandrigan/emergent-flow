import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { CatalogNode } from "../catalog/types";
import catalog from "../generated/catalog.json";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
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

  test("shows the selection toolbar when 2+ nodes are selected and runs them on click", async () => {
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

    fireEvent.click(screen.getByTestId("run-selected"));

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
});
