import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import {
  type SchemaRow,
  buildRelationTree,
  SchemaBrowserPanel,
} from "./SchemaBrowserPanel";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("buildRelationTree", () => {
  test("groups rows by database, schema, and table", () => {
    const rows: SchemaRow[] = [
      {
        database: "mydb",
        schema: "public",
        table: "users",
        column: null,
        data_type: null,
        nullable: null,
      },
      {
        database: "mydb",
        schema: "public",
        table: "orders",
        column: null,
        data_type: null,
        nullable: null,
      },
      {
        database: "mydb",
        schema: "analytics",
        table: "events",
        column: null,
        data_type: null,
        nullable: null,
      },
      {
        database: "otherdb",
        schema: "public",
        table: "products",
        column: null,
        data_type: null,
        nullable: null,
      },
    ];

    const tree = buildRelationTree(rows);

    expect(tree).toHaveLength(2);
    expect(tree[0].name).toBe("mydb");
    expect(tree[1].name).toBe("otherdb");

    expect(tree[0].schemas).toHaveLength(2);
    expect(tree[0].schemas[0].name).toBe("analytics");
    expect(tree[0].schemas[0].tables).toEqual(["events"]);
    expect(tree[0].schemas[1].name).toBe("public");
    expect(tree[0].schemas[1].tables).toEqual(["orders", "users"]);

    expect(tree[1].schemas).toHaveLength(1);
    expect(tree[1].schemas[0].name).toBe("public");
    expect(tree[1].schemas[0].tables).toEqual(["products"]);
  });

  test("uses fallback labels when database or schema is null", () => {
    const rows: SchemaRow[] = [
      {
        database: null,
        schema: null,
        table: "items",
        column: null,
        data_type: null,
        nullable: null,
      },
    ];

    const tree = buildRelationTree(rows);

    expect(tree).toHaveLength(1);
    expect(tree[0].name).toBe("(default)");
    expect(tree[0].schemas).toHaveLength(1);
    expect(tree[0].schemas[0].name).toBe("(default)");
    expect(tree[0].schemas[0].tables).toEqual(["items"]);
  });
});

describe("SchemaBrowserPanel", () => {
  test("shows empty hint when no connection selected", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ connections: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    render(<SchemaBrowserPanel />);

    expect(screen.getByTestId("schema-no-connection")).toBeInTheDocument();
  });

  test("selecting a connection fetches schema and renders table rows", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "http://127.0.0.1:8765/connections" || url === "/connections") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              connections: [
                {
                  name: "myconn",
                  dialect: "postgres",
                  auth_method: "password_env",
                },
              ],
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            rows: [
              {
                database: "mydb",
                schema: "public",
                table: "users",
                column: null,
                data_type: null,
                nullable: null,
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    });

    render(<SchemaBrowserPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("schema-connection-picker")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect((screen.getByTestId("schema-connection-picker") as HTMLSelectElement).options.length).toBe(2);
    });

    fireEvent.change(screen.getByTestId("schema-connection-picker"), {
      target: { value: "myconn" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("schema-table-users")).toBeInTheDocument();
    });
  });

  test("clicking table expand triggers ?relation= fetch and renders columns", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("relation=")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              rows: [
                {
                  database: null,
                  schema: null,
                  table: "users",
                  column: "id",
                  data_type: "integer",
                  nullable: false,
                },
                {
                  database: null,
                  schema: null,
                  table: "users",
                  column: "name",
                  data_type: "text",
                  nullable: true,
                },
              ],
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      if (url === "http://127.0.0.1:8765/connections" || url === "/connections") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              connections: [
                {
                  name: "myconn",
                  dialect: "postgres",
                  auth_method: "password_env",
                },
              ],
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            rows: [
              {
                database: "mydb",
                schema: "public",
                table: "users",
                column: null,
                data_type: null,
                nullable: null,
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    });

    render(<SchemaBrowserPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("schema-connection-picker")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect((screen.getByTestId("schema-connection-picker") as HTMLSelectElement).options.length).toBe(2);
    });

    fireEvent.change(screen.getByTestId("schema-connection-picker"), {
      target: { value: "myconn" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("schema-table-users")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("schema-table-users"));

    await waitFor(() => {
      expect(
        screen.getByTestId("schema-column-users-id"),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByTestId("schema-column-users-name"),
    ).toBeInTheDocument();
    expect(f).toHaveBeenCalledWith(
      expect.stringContaining("relation="),
    );
  });

  test("does not re-fetch columns on collapse/re-expand", async () => {
    let relationCallCount = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("relation=")) {
        relationCallCount++;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              rows: [
                {
                  database: null,
                  schema: null,
                  table: "users",
                  column: "id",
                  data_type: "integer",
                  nullable: false,
                },
              ],
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      if (url === "http://127.0.0.1:8765/connections" || url === "/connections") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              connections: [
                {
                  name: "myconn",
                  dialect: "postgres",
                  auth_method: "password_env",
                },
              ],
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            rows: [
              {
                database: "mydb",
                schema: "public",
                table: "users",
                column: null,
                data_type: null,
                nullable: null,
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    });

    render(<SchemaBrowserPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("schema-connection-picker")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect((screen.getByTestId("schema-connection-picker") as HTMLSelectElement).options.length).toBe(2);
    });

    fireEvent.change(screen.getByTestId("schema-connection-picker"), {
      target: { value: "myconn" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("schema-table-users")).toBeInTheDocument();
    });

    // First expand
    fireEvent.click(screen.getByTestId("schema-table-users"));

    await waitFor(() => {
      expect(
        screen.getByTestId("schema-column-users-id"),
      ).toBeInTheDocument();
    });

    // Collapse
    fireEvent.click(screen.getByTestId("schema-table-users"));

    // Need to wait for re-render after collapse
    await waitFor(() => {
      expect(
        screen.queryByTestId("schema-column-users-id"),
      ).not.toBeInTheDocument();
    });

    // Re-expand
    fireEvent.click(screen.getByTestId("schema-table-users"));

    await waitFor(() => {
      expect(
        screen.getByTestId("schema-column-users-id"),
      ).toBeInTheDocument();
    });

    expect(relationCallCount).toBe(1);
  });

  test("same-named table in two schemas expands/fetches independently, scoped by database+schema", async () => {
    const relationCalls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("relation=")) {
        relationCalls.push(url);
        const columnName = url.includes("schema=analytics") ? "region" : "id";
        return Promise.resolve(
          new Response(
            JSON.stringify({
              rows: [
                {
                  database: "mydb",
                  schema: url.includes("schema=analytics") ? "analytics" : "public",
                  table: "users",
                  column: columnName,
                  data_type: "text",
                  nullable: false,
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      if (url === "http://127.0.0.1:8765/connections" || url === "/connections") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              connections: [{ name: "myconn", dialect: "postgres", auth_method: "password_env" }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            rows: [
              {
                database: "mydb",
                schema: "public",
                table: "users",
                column: null,
                data_type: null,
                nullable: null,
              },
              {
                database: "mydb",
                schema: "analytics",
                table: "users",
                column: null,
                data_type: null,
                nullable: null,
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    });

    render(<SchemaBrowserPanel />);

    await waitFor(() => {
      expect(
        (screen.getByTestId("schema-connection-picker") as HTMLSelectElement).options.length,
      ).toBe(2);
    });

    fireEvent.change(screen.getByTestId("schema-connection-picker"), {
      target: { value: "myconn" },
    });

    await waitFor(() => {
      expect(screen.getAllByTestId("schema-table-users")).toHaveLength(2);
    });

    // buildRelationTree sorts schemas alphabetically, so "analytics" renders before "public".
    const [analyticsRow, publicRow] = screen.getAllByTestId("schema-table-users");

    fireEvent.click(analyticsRow);
    await waitFor(() => expect(relationCalls).toHaveLength(1));
    expect(relationCalls[0]).toContain("schema=analytics");

    fireEvent.click(publicRow);
    await waitFor(() => expect(relationCalls).toHaveLength(2));
    expect(relationCalls[1]).toContain("schema=public");
    expect(relationCalls[1]).not.toContain("schema=analytics");

    // Both tables are independently expanded and cached under separate columns.
    await waitFor(() => {
      expect(screen.getAllByTestId(/^schema-columns-loading-users$|^schema-column-users-/)).not.toHaveLength(0);
    });
  });
});
