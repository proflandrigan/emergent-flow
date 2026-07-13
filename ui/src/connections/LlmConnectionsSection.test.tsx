import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { LlmConnectionsSection } from "./LlmConnectionsSection";

afterEach(() => {
  vi.restoreAllMocks();
});

const mockProfile = {
  name: "my_openai",
  kind: "llm",
  provider: "openai",
  api_key_env: "OPENAI_API_KEY",
};

test("renders empty state when no profiles are configured", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ connections: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<LlmConnectionsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("llm-connections-empty")).toBeInTheDocument();
  });
});

test("renders a profile row with name and provider", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ connections: [mockProfile] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<LlmConnectionsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("llm-connection-row-my_openai")).toBeInTheDocument();
  });
  expect(screen.getByText("my_openai")).toBeInTheDocument();
  expect(screen.getByText("openai")).toBeInTheDocument();
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

  render(<LlmConnectionsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("llm-connection-new-button")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("llm-connection-new-button"));

  await waitFor(() => {
    expect(screen.getByTestId("llm-connection-form")).toBeInTheDocument();
  });

  fireEvent.change(screen.getByTestId("llm-form-name"), {
    target: { value: "my_openai" },
  });
  fireEvent.change(screen.getByTestId("llm-form-provider"), {
    target: { value: "openai" },
  });
  fireEvent.change(screen.getByTestId("llm-form-api-key-env"), {
    target: { value: "OPENAI_API_KEY" },
  });

  fireEvent.click(screen.getByTestId("llm-form-save"));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/connections",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"kind":"llm"'),
      }),
    );
  });

  await waitFor(() => {
    expect(screen.getByTestId("llm-connections-empty")).toBeInTheDocument();
  });
});

test("edit form is pre-filled and issues PUT request", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch");
  fetchMock.mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify({ connections: [mockProfile] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );

  render(<LlmConnectionsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("llm-connection-row-my_openai")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("llm-connection-edit-my_openai"));

  await waitFor(() => {
    expect(screen.getByTestId("llm-connection-form")).toBeInTheDocument();
  });

  expect(screen.getByTestId("llm-form-provider")).toHaveValue("openai");
  expect(screen.getByTestId("llm-form-name")).toBeDisabled();

  fireEvent.click(screen.getByTestId("llm-form-save"));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/connections/my_openai",
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
          new Response(JSON.stringify({ connections: [mockProfile] }), {
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
    }
    return Promise.resolve(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  render(<LlmConnectionsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("llm-connection-row-my_openai")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("llm-connection-delete-my_openai"));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/connections/my_openai",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  await waitFor(() => {
    expect(screen.getByTestId("llm-connections-empty")).toBeInTheDocument();
  });
});

test("empty api_key_env shows error and does not POST", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch");
  fetchMock.mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify({ connections: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );

  render(<LlmConnectionsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("llm-connection-new-button")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("llm-connection-new-button"));

  await waitFor(() => {
    expect(screen.getByTestId("llm-connection-form")).toBeInTheDocument();
  });

  fireEvent.change(screen.getByTestId("llm-form-name"), {
    target: { value: "my_openai" },
  });
  fireEvent.change(screen.getByTestId("llm-form-provider"), {
    target: { value: "openai" },
  });

  fireEvent.click(screen.getByTestId("llm-form-save"));

  await waitFor(() => {
    expect(screen.getByTestId("llm-form-error")).toBeInTheDocument();
  });

  expect(fetchMock).not.toHaveBeenCalledWith(
    "/connections",
    expect.objectContaining({ method: "POST" }),
  );
});
