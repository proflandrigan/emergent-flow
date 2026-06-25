import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useGraphStore } from "./graphStore";
import { useLiveValidation } from "./useLiveValidation";
import { useValidationStore } from "./validationStore";

beforeEach(() => {
  useGraphStore.getState().reset();
  useValidationStore.getState().clear();
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

function Host() {
  useLiveValidation(0);
  return null;
}

test("writes edge_compatibility on a successful validate", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        diagnostics: {
          diagnostics: [
            { severity: "error", code: "type_incompatible", message: "boom", edge_id: "e1" },
          ],
          edge_compatibility: { e1: false },
        },
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    ),
  );

  addNode();
  render(<Host />);

  await waitFor(() =>
    expect(useValidationStore.getState().edgeCompatibility).toEqual({ e1: false }),
  );
});

test("never fetches for an empty graph", () => {
  const f = vi.spyOn(globalThis, "fetch");

  render(<Host />);

  expect(f).not.toHaveBeenCalled();
});

test("setError on 422", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ error: "GraphValidationError: bad" }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    }),
  );

  addNode();
  render(<Host />);

  await waitFor(() => expect(useValidationStore.getState().status).toBe("error"));
});
