import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { useExecutionStore } from "../store/executionStore";
import { ExecutionToolbar } from "./ExecutionToolbar";

beforeEach(() => {
  useGraphStore.getState().reset();
  useExecutionStore.getState().clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function addNode() {
  useGraphStore.getState().addNodeFromSpec(
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

function sseResponse(events: Record<string, unknown>[], status = 200): Response {
  const body = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(body));
      controller.close();
    },
  });
  return new Response(stream, {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}

test("Execute posts to /execute/stream and writes per-node results into the store", async () => {
  const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    sseResponse([
      { type: "node_start", node_id: "n1", label: "L", current: 1, total: 1 },
      { type: "node_ok", node_id: "n1", elapsed_ms: 5, results: { out: { kind: "scalar", value: 1 } } },
      { type: "run_complete", total_ms: 5 },
    ]),
  );

  addNode();
  render(<ExecutionToolbar />);

  fireEvent.click(screen.getByTestId("exec-run"));

  await waitFor(() =>
    expect(useExecutionStore.getState().statuses).toHaveProperty("n1"),
  );
  expect(useExecutionStore.getState().statuses.n1).toEqual({ status: "ok" });
  expect(useExecutionStore.getState().results.n1).toEqual({
    out: { kind: "scalar", value: 1 },
  });
  expect(useExecutionStore.getState().running).toBe(false);
  expect(useExecutionStore.getState().progress).toBeNull();
  expect(f).toHaveBeenCalledWith("/execute/stream", expect.anything());
});

test("Execute on empty graph shows a banner and never fetches", async () => {
  const f = vi.spyOn(globalThis, "fetch");

  render(<ExecutionToolbar />);

  fireEvent.click(screen.getByTestId("exec-run"));

  await waitFor(() =>
    expect(screen.getByTestId("exec-error")).toHaveTextContent(
      "Add nodes before executing.",
    ),
  );
  expect(f).not.toHaveBeenCalled();
});

test("Execute surfaces a 422 error from the eager-validation path (non-stream JSON body)", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({ error: "GraphValidationError: bad" }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    ),
  );

  addNode();
  render(<ExecutionToolbar />);

  fireEvent.click(screen.getByTestId("exec-run"));

  await waitFor(() =>
    expect(screen.getByTestId("exec-error")).toHaveTextContent("bad"),
  );
  expect(useExecutionStore.getState().error).toMatch(/bad/);
});

test("Execute surfaces a node_error event without aborting the run", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    sseResponse([
      { type: "node_start", node_id: "n1", label: "L", current: 1, total: 1 },
      { type: "node_error", node_id: "n1", elapsed_ms: 5, error: "ValueError: boom" },
      { type: "run_complete", total_ms: 5 },
    ]),
  );

  addNode();
  render(<ExecutionToolbar />);

  fireEvent.click(screen.getByTestId("exec-run"));

  await waitFor(() =>
    expect(useExecutionStore.getState().statuses.n1).toEqual({
      status: "error",
      error: "ValueError: boom",
    }),
  );
  expect(useExecutionStore.getState().running).toBe(false);
});

test("Execute surfaces a run_error event", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    sseResponse([
      { type: "node_start", node_id: "n1", label: "L", current: 1, total: 1 },
      { type: "run_error", error: "RuntimeError: declarative graph blew up" },
    ]),
  );

  addNode();
  render(<ExecutionToolbar />);

  fireEvent.click(screen.getByTestId("exec-run"));

  await waitFor(() =>
    expect(screen.getByTestId("exec-error")).toHaveTextContent("declarative graph blew up"),
  );
  expect(useExecutionStore.getState().error).toMatch(/declarative graph blew up/);
});

test("Download on empty graph shows a banner and never fetches", async () => {
  const f = vi.spyOn(globalThis, "fetch");

  render(<ExecutionToolbar />);

  fireEvent.click(screen.getByTestId("exec-download"));

  await waitFor(() =>
    expect(screen.getByTestId("exec-error")).toHaveTextContent(
      "Add nodes before downloading.",
    ),
  );
  expect(f).not.toHaveBeenCalled();
});

test("Download posts the graph to /compile", async () => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:mock"),
    revokeObjectURL: vi.fn(),
  });
  const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ code: "x = 1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  addNode();
  render(<ExecutionToolbar />);

  fireEvent.click(screen.getByTestId("exec-download"));

  await waitFor(() => expect(f).toHaveBeenCalledWith("/compile", expect.anything()));
});
