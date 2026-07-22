import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
import { StepsPanel } from "./StepsPanel";

beforeEach(() => {
  useGraphStore.getState().reset();
  useSelectionStore.setState({ nodes: {}, edges: {} });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function addNode() {
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

const mockSteps = [
  {
    step: 0,
    node_id: "n-load",
    node_label: "Load CSV",
    status: "ok",
    inputs: [],
    outputs: [
      {
        var_name: "load_csv_frame",
        port_name: "frame",
        payload: { kind: "scalar" as const, value: 42 },
      },
    ],
  },
  {
    step: 1,
    node_id: "n-transform",
    node_label: "Filter Rows",
    status: "ok",
    inputs: [
      {
        var_name: "load_csv_frame",
        port_name: "frame",
        payload: { kind: "table" as const, columns: ["x"], dtypes: ["int64"], shape: [3, 1], head: [{ x: 1 }], truncated: false },
      },
    ],
    outputs: [
      {
        var_name: "filter_rows_frame",
        port_name: "frame",
        payload: { kind: "table" as const, columns: ["x"], dtypes: ["int64"], shape: [2, 1], head: [{ x: 1 }], truncated: false },
      },
    ],
  },
];

test("shows the empty state and never calls fetch for an empty graph", () => {
  const f = vi.spyOn(globalThis, "fetch");

  render(<StepsPanel onViewInCode={vi.fn()} debounceMs={0} />);

  expect(screen.getByTestId("steps-empty")).toBeInTheDocument();
  expect(f).not.toHaveBeenCalled();
});

test("renders step traces from a successful inspect response", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ payload_version: 2, steps: mockSteps }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  addNode();
  render(<StepsPanel onViewInCode={vi.fn()} debounceMs={0} />);

  await waitFor(() =>
    expect(screen.getByTestId("steps-list")).toBeInTheDocument(),
  );

  expect(screen.getAllByTestId("steps-var-row").length).toBe(3);
  expect(screen.getByTestId("payload-scalar")).toHaveTextContent("42");
  expect(screen.getAllByTestId("payload-table").length).toBe(2);
});

test("renders the server's error message on a failing inspect", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ error: "InspectError: boom" }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    }),
  );

  addNode();
  render(<StepsPanel onViewInCode={vi.fn()} debounceMs={0} />);

  await waitFor(() =>
    expect(screen.getByTestId("steps-error")).toHaveTextContent("boom"),
  );
});

test("clicking an output variable selects its producing node", async () => {
  const nodeId = addNode();

  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        payload_version: 2,
        steps: [
          {
            step: 0,
            node_id: nodeId,
            node_label: "L",
            status: "ok",
            inputs: [],
            outputs: [
              {
                var_name: "result_var",
                port_name: "out",
                payload: { kind: "scalar", value: 99 },
              },
            ],
          },
        ],
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    ),
  );

  render(<StepsPanel onViewInCode={vi.fn()} debounceMs={0} />);

  await waitFor(() =>
    expect(screen.getByTestId("steps-list")).toBeInTheDocument(),
  );

  fireEvent.click(screen.getByTestId("steps-var-select"));

  expect(useSelectionStore.getState().nodes[nodeId]).toBe(true);
});

test("clicking view-in-code calls onViewInCode with the var_name", async () => {
  const onViewInCode = vi.fn();

  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        payload_version: 2,
        steps: [
          {
            step: 0,
            node_id: "n-test",
            node_label: "Test",
            status: "ok",
            inputs: [],
            outputs: [
              {
                var_name: "my_var",
                port_name: "out",
                payload: { kind: "scalar", value: 1 },
              },
            ],
          },
        ],
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    ),
  );

  addNode();
  render(<StepsPanel onViewInCode={onViewInCode} debounceMs={0} />);

  await waitFor(() =>
    expect(screen.getByTestId("steps-list")).toBeInTheDocument(),
  );

  fireEvent.click(screen.getByTestId("steps-view-in-code"));

  expect(onViewInCode).toHaveBeenCalledWith("my_var");
});
