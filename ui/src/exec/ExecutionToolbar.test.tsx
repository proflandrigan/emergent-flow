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

test("Execute writes results into the store", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        payload_version: 1,
        results: { n1: { out: { kind: "scalar", value: 1 } } },
        statuses: { n1: { status: "ok" } },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  addNode();
  render(<ExecutionToolbar />);

  fireEvent.click(screen.getByTestId("exec-run"));

  await waitFor(() =>
    expect(useExecutionStore.getState().statuses).toHaveProperty("n1"),
  );
  expect(useExecutionStore.getState().running).toBe(false);
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

test("Execute surfaces a 422 error", async () => {
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
