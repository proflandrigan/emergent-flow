import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { CodingAgentsSection } from "./CodingAgentsSection";
import { useSessionStore } from "../session/sessionStore";

afterEach(() => {
  vi.restoreAllMocks();
});

test("renders help text unconditionally", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    () => new Promise(() => {
      /* never resolves */
    }),
  );

  render(<CodingAgentsSection />);

  expect(screen.getByTestId("coding-agents-help")).toBeInTheDocument();
});

test("renders empty state when GET /sessions returns zero sessions", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ sessions: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<CodingAgentsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("coding-agents-empty")).toBeInTheDocument();
  });
});

test("renders session rows with derived fields", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        sessions: [
          { id: "sess-1", version: 2, graph: { nodes: { a: {}, b: {} } }, proposals: {} },
        ],
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    ),
  );

  render(<CodingAgentsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("session-row-sess-1")).toBeInTheDocument();
  });
  expect(screen.getByTestId("session-row-sess-1")).toHaveTextContent("2 nodes");
  expect(screen.getByTestId("session-row-sess-1")).toHaveTextContent("v2");
});

test("renders auth-required on 401", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(null, { status: 401 }),
  );

  render(<CodingAgentsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("coding-agents-auth-required")).toBeInTheDocument();
  });
});

test("renders error when fetch rejects", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Network failure"));

  render(<CodingAgentsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("coding-agents-error")).toBeInTheDocument();
  });
});

test("clicking End session issues DELETE request", async () => {
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
            JSON.stringify({
              sessions: [
                { id: "sess-1", version: 1, graph: { nodes: { a: {} } }, proposals: {} },
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
        new Response(JSON.stringify({ sessions: [] }), {
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

  render(<CodingAgentsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("session-row-sess-1")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByTestId("session-end-sess-1"));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      "/sessions/sess-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  await waitFor(() => {
    expect(screen.getByTestId("coding-agents-empty")).toBeInTheDocument();
  });
});

test("clicking Join calls sessionStore.join", async () => {
  const joinSpy = vi
    .spyOn(useSessionStore.getState(), "join")
    .mockResolvedValue(undefined);
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        sessions: [
          { id: "sess-1", version: 1, graph: { nodes: { a: {} } }, proposals: {} },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  render(<CodingAgentsSection />);

  await waitFor(() => {
    expect(screen.getByTestId("session-row-sess-1")).toBeInTheDocument();
  });
  fireEvent.click(screen.getByTestId("session-join-sess-1"));

  await waitFor(() => {
    expect(joinSpy).toHaveBeenCalledWith("sess-1");
  });
});
