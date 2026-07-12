import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { WarehouseConnectionsSection } from "./WarehouseConnectionsSection";

afterEach(() => {
  vi.restoreAllMocks();
});

const mockProfile = {
  name: "warehouse_prod",
  dialect: "postgres",
  auth_method: "password_env",
  coordinates: {},
  credential_refs: {},
  limits: {},
  write_enabled: false,
};

test("renders empty state when no profiles are configured", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ connections: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<WarehouseConnectionsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("connections-empty")).toBeInTheDocument();
  });
});

test("renders a profile row with name and dialect", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({ connections: [mockProfile] }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    ),
  );

  render(<WarehouseConnectionsSection />);

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
        JSON.stringify({ connections: [mockProfile] }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
  });

  render(<WarehouseConnectionsSection />);

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
        JSON.stringify({ connections: [mockProfile] }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
  });

  render(<WarehouseConnectionsSection />);

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

test("create form issues POST and returns to list view", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch");
  fetchMock.mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify({ connections: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );

  render(<WarehouseConnectionsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("connection-new-button")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("connection-new-button"));

  await waitFor(() => {
    expect(screen.getByTestId("warehouse-connection-form")).toBeInTheDocument();
  });

  fireEvent.change(screen.getByTestId("warehouse-form-name"), {
    target: { value: "test_db" },
  });
  fireEvent.change(screen.getByTestId("warehouse-form-dialect"), {
    target: { value: "postgres" },
  });

  fireEvent.click(screen.getByTestId("warehouse-form-save"));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/connections",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"kind":"warehouse"'),
      }),
    );
  });

  await waitFor(() => {
    expect(screen.getByTestId("connections-empty")).toBeInTheDocument();
  });
});

test("edit form is pre-filled and issues PUT request", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch");
  fetchMock.mockImplementation(() =>
    Promise.resolve(
      new Response(
        JSON.stringify({ connections: [mockProfile] }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    ),
  );

  render(<WarehouseConnectionsSection />);

  await waitFor(() => {
    expect(
      screen.getByTestId("connection-row-warehouse_prod"),
    ).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("connection-edit-warehouse_prod"));

  await waitFor(() => {
    expect(screen.getByTestId("warehouse-connection-form")).toBeInTheDocument();
  });

  expect(screen.getByTestId("warehouse-form-dialect")).toHaveValue("postgres");
  expect(screen.getByTestId("warehouse-form-name")).toBeDisabled();

  fireEvent.click(screen.getByTestId("warehouse-form-save"));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/connections/warehouse_prod",
      expect.objectContaining({ method: "PUT" }),
    );
  });
});

test("delete button issues DELETE request and removes row", async () => {
  let getCalls = 0;
  const fetchMock = vi.spyOn(globalThis, "fetch");
  fetchMock.mockImplementation((input, init) => {
    const method = init?.method ?? "GET";
    if (method === "DELETE") {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (method === "GET") {
      getCalls++;
      if (getCalls === 1) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ connections: [mockProfile] }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({ connections: [] }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    }
    return Promise.resolve(
      new Response(
        JSON.stringify({}),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
  });

  render(<WarehouseConnectionsSection />);

  await waitFor(() => {
    expect(
      screen.getByTestId("connection-row-warehouse_prod"),
    ).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("connection-delete-warehouse_prod"));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/connections/warehouse_prod",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  await waitFor(() => {
    expect(screen.getByTestId("connections-empty")).toBeInTheDocument();
  });
});

test("invalid JSON in coordinates shows error and does not POST", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch");
  fetchMock.mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify({ connections: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );

  render(<WarehouseConnectionsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("connection-new-button")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("connection-new-button"));

  await waitFor(() => {
    expect(screen.getByTestId("warehouse-connection-form")).toBeInTheDocument();
  });

  fireEvent.change(screen.getByTestId("warehouse-form-name"), {
    target: { value: "test_db" },
  });
  fireEvent.change(screen.getByTestId("warehouse-form-dialect"), {
    target: { value: "postgres" },
  });
  fireEvent.change(screen.getByTestId("warehouse-form-coordinates"), {
    target: { value: "not valid json" },
  });

  fireEvent.click(screen.getByTestId("warehouse-form-save"));

  await waitFor(() => {
    expect(screen.getByTestId("warehouse-form-error")).toBeInTheDocument();
  });

  expect(fetchMock).not.toHaveBeenCalledWith(
    "/connections",
    expect.objectContaining({ method: "POST" }),
  );
});
