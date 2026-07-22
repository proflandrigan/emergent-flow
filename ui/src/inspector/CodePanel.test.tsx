import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { CodePanel } from "./CodePanel";

beforeEach(() => {
  useGraphStore.getState().reset();
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

test("renders highlighted code on a successful compile", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ code: "x = 1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  addNode();
  render(<CodePanel debounceMs={0} />);

  await waitFor(() =>
    expect(screen.getByTestId("code-output")).toHaveTextContent("x = 1"),
  );
});

test("renders the server's error message on a 422", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ error: "CodegenError: boom" }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    }),
  );

  addNode();
  render(<CodePanel debounceMs={0} />);

  await waitFor(() =>
    expect(screen.getByTestId("code-error")).toHaveTextContent("boom"),
  );
});

test("shows the empty state and never calls fetch for an empty graph", () => {
  const f = vi.spyOn(globalThis, "fetch");

  render(<CodePanel debounceMs={0} />);

  expect(screen.getByTestId("code-empty")).toBeInTheDocument();
  expect(f).not.toHaveBeenCalled();
});

test("highlights the line matching highlightVarName", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ code: "x = 1\ny = x + 1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  addNode();
  render(<CodePanel debounceMs={0} highlightVarName="y" />);

  await waitFor(() =>
    expect(screen.getByTestId("code-output")).toHaveTextContent("y = x + 1"),
  );

  const highlighted = screen.getByTestId("code-highlighted-line");
  expect(highlighted).toBeInTheDocument();
  expect(highlighted).toHaveTextContent("y = x + 1");
});

test("does not highlight any line when highlightVarName is null", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ code: "x = 1\ny = x + 1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  addNode();
  render(<CodePanel debounceMs={0} highlightVarName={null} />);

  await waitFor(() =>
    expect(screen.getByTestId("code-output")).toHaveTextContent("x = 1"),
  );

  expect(screen.queryByTestId("code-highlighted-line")).not.toBeInTheDocument();
});
