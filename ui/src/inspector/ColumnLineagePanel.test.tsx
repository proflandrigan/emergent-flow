import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { ColumnLineagePanel } from "./ColumnLineagePanel";
import { PayloadView } from "./PayloadView";

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

test("traces and renders a column's derivation steps", async () => {
  const nodeId = addNode();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        lineage: {
          target_node_id: nodeId,
          target_column: "revenue_log",
          nodes: [
            { node_id: "s", node_type: "data.load_csv", label: "Load", column: "revenue", role: "source" },
            {
              node_id: "d",
              node_type: "clean.derive_column",
              label: "Derive",
              column: "revenue_log",
              role: "derived",
              source_column: "revenue",
              detail: "derived from revenue",
            },
          ],
          edges: [],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  render(<ColumnLineagePanel nodeId={nodeId} column="revenue_log" debounceMs={0} />);

  await waitFor(() => expect(screen.getByTestId("column-lineage")).toBeInTheDocument());
  expect(screen.getByTestId("column-lineage-header")).toHaveTextContent("revenue_log");
  expect(screen.getAllByTestId("column-lineage-step")).toHaveLength(2);
  expect(screen.getAllByTestId("column-lineage-step")[1]).toHaveTextContent("Derive");
  expect(screen.getAllByTestId("column-lineage-step")[1]).toHaveTextContent("revenue_log");
});

test("shows the no-column prompt when none selected", () => {
  const nodeId = addNode();
  render(<ColumnLineagePanel nodeId={nodeId} column={null} debounceMs={0} />);
  expect(screen.getByTestId("column-lineage-empty-no-column")).toBeInTheDocument();
});

test("shows the no-selection prompt when no node selected", () => {
  render(<ColumnLineagePanel nodeId={null} column="x" debounceMs={0} />);
  expect(screen.getByTestId("column-lineage-empty-no-selection")).toBeInTheDocument();
});

test("renders a server error", async () => {
  const nodeId = addNode();
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ error: "CodegenError: boom" }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    }),
  );
  render(<ColumnLineagePanel nodeId={nodeId} column="c" debounceMs={0} />);
  await waitFor(() =>
    expect(screen.getByTestId("column-lineage-error")).toHaveTextContent("boom"),
  );
});

test("table headers are clickable and call onColumnClick", async () => {
  const onColumnClick = vi.fn();
  const payload = {
    kind: "table" as const,
    columns: ["a", "b"],
    dtypes: ["int", "int"],
    shape: [1, 2] as [number, number],
    head: [{ a: 1, b: 2 }],
    truncated: false,
  };

  render(<PayloadView payload={payload} onColumnClick={onColumnClick} />);

  const headers = screen.getAllByTestId("payload-column-header");
  expect(headers).toHaveLength(2);
  fireEvent.click(headers[0]);
  expect(onColumnClick).toHaveBeenCalledWith("a");
});

test("table headers are plain text when no click handler given", () => {
  const payload = {
    kind: "table" as const,
    columns: ["a"],
    dtypes: ["int"],
    shape: [1, 1] as [number, number],
    head: [{ a: 1 }],
    truncated: false,
  };
  render(<PayloadView payload={payload} />);
  expect(screen.queryAllByTestId("payload-column-header")).toHaveLength(0);
});
