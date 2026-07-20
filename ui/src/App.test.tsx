import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { useSessionStore } from "./session/sessionStore";

vi.mock("./session/sessionClient", () => ({
  createSession: vi.fn().mockResolvedValue({
    id: "app-test-session",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 0,
    proposals: {},
  }),
  getSession: vi.fn(),
  deleteSession: vi.fn(),
  replaceSessionGraph: vi.fn(),
  proposeMutation: vi.fn(),
  consultSession: vi.fn(),
  acceptProposal: vi.fn(),
  rejectProposal: vi.fn(),
  subscribeToSessionEvents: vi.fn(() => ({ close: vi.fn() })),
  createReview: vi.fn(),
  addReviewComment: vi.fn(),
  createGate: vi.fn(),
  closeGateRequest: vi.fn(),
  skipGateRequest: vi.fn(),
  postGateDecision: vi.fn(),
  startChat: vi.fn(),
  stopChatTurn: vi.fn(),
  endChat: vi.fn(),
  getAvailableAgents: vi.fn().mockResolvedValue([]),
}));

afterEach(() => {
  vi.clearAllMocks();
  useSessionStore.setState({
    sessionId: null,
    version: null,
    proposals: {},
    reviews: {},
    gates: {},
    chat: { backend: null, backend_thread_id: null, active_persona: null, turns: [] },
    status: "idle",
    error: null,
    rebaseNeeded: false,
    rebaseMessage: null,
  });
});

// App fires two fetches on mount (/healthz and the palette's /catalog). A `Response` body is
// single-use, so the mock must return a FRESH response per call (and route by URL) — a shared
// mockResolvedValue(Response) would let whichever fetch reads second hit "body already read".
function mockHealth(status: string) {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    let body: unknown;
    if (url.includes("/catalog")) {
      body = { nodes: [] };
    } else if (url.includes("/connections")) {
      body = { connections: [] };
    } else {
      body = { status };
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
}

test("renders the canvas heading", () => {
  mockHealth("ok");
  render(<App />);
  expect(
    screen.getByRole("heading", { name: /Emergent Flow/ }),
  ).toBeInTheDocument();
});

test("shows the server status as ok when /healthz is healthy", async () => {
  mockHealth("ok");
  render(<App />);
  await waitFor(() =>
    expect(screen.getByTestId("server-status")).toHaveTextContent("ok"),
  );
});

test("shows unreachable when the health request fails", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(
    new Error("connection refused"),
  );
  render(<App />);
  await waitFor(() =>
    expect(screen.getByTestId("server-status")).toHaveTextContent(
      "unreachable",
    ),
  );
});

test("Browse schema overflow item opens the schema browser panel", async () => {
  mockHealth("ok");
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByText("Browse schema"));

  await waitFor(() => {
    expect(screen.getByTestId("schema-no-connection")).toBeInTheDocument();
  });
});

test("the overflow menu closes on outside click and on Escape", async () => {
  mockHealth("ok");
  render(<App />);

  const toggle = screen.getByRole("button", { name: "More actions" });

  fireEvent.click(toggle);
  expect(screen.getByRole("menu")).toBeInTheDocument();

  // The outside-click listener attaches on the next tick (App.tsx) so the click that just
  // opened the menu doesn't bubble into it and immediately close what it opened -- let that
  // tick pass before simulating a click elsewhere.
  await new Promise((resolve) => setTimeout(resolve, 0));

  fireEvent.click(document.body);
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();

  fireEvent.click(toggle);
  expect(screen.getByRole("menu")).toBeInTheDocument();

  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});

test("Manage connections overflow item opens the connections panel", async () => {
  mockHealth("ok");
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByText("Manage connections"));

  await waitFor(() => {
    expect(screen.getByTestId("connections-empty")).toBeInTheDocument();
  });
});

test("Start chat overflow item opens the chat modal", async () => {
  mockHealth("ok");
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: "More actions" }));
  fireEvent.click(screen.getByText("Start chat"));

  await waitFor(() => {
    expect(screen.getByTestId("chat-connecting")).toBeInTheDocument();
  });
  await waitFor(() => {
    expect(screen.getByTestId("chat-backend-picker")).toBeInTheDocument();
  });
});
