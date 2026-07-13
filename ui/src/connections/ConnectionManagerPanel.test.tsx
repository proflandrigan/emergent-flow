import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { ConnectionManagerPanel } from "./ConnectionManagerPanel";

afterEach(() => {
  vi.restoreAllMocks();
});

test("renders empty state when no profiles are configured", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ connections: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<ConnectionManagerPanel />);

  await waitFor(() => {
    expect(screen.getByTestId("connections-empty")).toBeInTheDocument();
  });
  expect(screen.getByText(/connections\.toml/)).toBeInTheDocument();
});

test("renders a profile row with name and dialect", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        connections: [
          {
            name: "warehouse_prod",
            dialect: "postgres",
            auth_method: "password_env",
            coordinates: {},
            credential_refs: {},
            limits: {},
            write_enabled: false,
          },
        ],
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    ),
  );

  render(<ConnectionManagerPanel />);

  await waitFor(() => {
    expect(
      screen.getByTestId("connection-row-warehouse_prod"),
    ).toBeInTheDocument();
  });
  expect(screen.getByText("warehouse_prod")).toBeInTheDocument();
  expect(screen.getByText(/postgres/)).toBeInTheDocument();
});

test("test button shows success message on successful test", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.includes("/connections/")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            name: "warehouse_prod",
            ok: true,
            message:
              "Profile 'warehouse_prod' (postgres) is valid.",
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
          connections: [
            {
              name: "warehouse_prod",
              dialect: "postgres",
              auth_method: "password_env",
              coordinates: {},
              credential_refs: {},
              limits: {},
              write_enabled: false,
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

  render(<ConnectionManagerPanel />);

  await waitFor(() => {
    expect(
      screen.getByTestId("connection-row-warehouse_prod"),
    ).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("connection-test-warehouse_prod"));

  await waitFor(() => {
    expect(
      screen.getByTestId("connection-status-warehouse_prod"),
    ).toHaveTextContent("Profile 'warehouse_prod' (postgres) is valid.");
  });
});

test("test button shows error message on 422 failure", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.includes("/connections/")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            error:
              "UnknownConnectionError: warehouse_prod not found",
          }),
          {
            status: 422,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    }
    return Promise.resolve(
      new Response(
        JSON.stringify({
          connections: [
            {
              name: "warehouse_prod",
              dialect: "postgres",
              auth_method: "password_env",
              coordinates: {},
              credential_refs: {},
              limits: {},
              write_enabled: false,
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

  render(<ConnectionManagerPanel />);

  await waitFor(() => {
    expect(
      screen.getByTestId("connection-row-warehouse_prod"),
    ).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("connection-test-warehouse_prod"));

  await waitFor(() => {
    expect(
      screen.getByTestId("connection-status-warehouse_prod"),
    ).toHaveTextContent("UnknownConnectionError: warehouse_prod not found");
  });
});

test("renders all three sections together", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.includes("/sessions")) {
      return Promise.resolve(
        new Response(JSON.stringify({ sessions: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify({ connections: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  render(<ConnectionManagerPanel />);

  expect(screen.getByText("Warehouses")).toBeInTheDocument();
  expect(screen.getByText("LLM Credentials")).toBeInTheDocument();
  expect(screen.getByText("Coding Agents")).toBeInTheDocument();

  await waitFor(() => {
    expect(screen.getByTestId("connections-empty")).toBeInTheDocument();
  });
});
