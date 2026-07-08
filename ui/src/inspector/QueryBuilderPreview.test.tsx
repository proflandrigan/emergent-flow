import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import catalogJson from "../generated/catalog.json";
import type { Catalog, CatalogNode } from "../catalog/types";
import { useGraphStore } from "../store/graphStore";
import { ConfigForm } from "./ConfigForm";

const catalog = catalogJson as unknown as Catalog;

function spec(type: string): CatalogNode {
  const found = catalog.nodes.find((n) => n.type === type);
  if (!found) {
    throw new Error(`catalog node not found: ${type}`);
  }
  return found;
}

beforeEach(() => {
  useGraphStore.getState().reset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("data.query_builder triggers /compile-spec and shows the returned SQL", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("/compile-spec")) {
      return new Response(JSON.stringify({ sql: "SELECT name FROM sales" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("data.query_builder"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "source", "sales");
  useGraphStore.getState().setParam(id, "select", ["name"]);
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  await waitFor(() =>
    expect(screen.getByTestId("query-builder-sql-preview")).toHaveTextContent(
      "SELECT name FROM sales",
    ),
  );
});

test("data.query_builder Estimate cost button fetches /execute_node and shows cost badge", async () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("data.query_builder"), { x: 0, y: 0 });
  useGraphStore.getState().setParam(id, "source", "sales");
  useGraphStore.getState().setParam(id, "select", ["name"]);
  const node = useGraphStore.getState().nodes[id];

  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("/compile-spec")) {
      return new Response(JSON.stringify({ sql: "SELECT name FROM sales" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(
      JSON.stringify({
        payload_version: 2,
        results: {
          [id]: {
            frame: {
              kind: "record",
              type: "QueryResult",
              fields: {
                bytes_scanned: { kind: "scalar", value: 4096 },
                cost_usd: { kind: "scalar", value: 0.0005 },
              },
            },
          },
        },
        statuses: { [id]: { status: "ok" } },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });

  render(<ConfigForm node={node} />);

  await waitFor(() =>
    expect(screen.getByTestId("query-builder-sql-preview")).toHaveTextContent(
      "SELECT name FROM sales",
    ),
  );

  fireEvent.click(screen.getByTestId("query-builder-estimate-cost"));

  await waitFor(() =>
    expect(screen.getByTestId("query-builder-cost-badge")).toBeInTheDocument(),
  );
  expect(screen.getByTestId("query-builder-cost-badge")).toHaveTextContent("4,096 bytes scanned");
  expect(screen.getByTestId("query-builder-cost-badge")).toHaveTextContent("$0.000500 estimated");
});

test("data.sql_query does NOT render query-builder-specific elements", () => {
  const id = useGraphStore
    .getState()
    .addNodeFromSpec(spec("data.sql_query"), { x: 0, y: 0 });
  const node = useGraphStore.getState().nodes[id];
  render(<ConfigForm node={node} />);

  expect(screen.queryByTestId("query-builder-sql-preview")).not.toBeInTheDocument();
  expect(
    screen.queryByTestId("query-builder-estimate-cost"),
  ).not.toBeInTheDocument();
});
