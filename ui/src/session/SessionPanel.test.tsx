import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { useGraphStore } from "../store/graphStore";
import * as sessionClient from "./sessionClient";
import { SessionPanel } from "./SessionPanel";
import { useSessionStore } from "./sessionStore";

vi.mock("./sessionClient", () => ({
  createSession: vi.fn(),
  getSession: vi.fn(),
  deleteSession: vi.fn(),
  replaceSessionGraph: vi.fn(),
  proposeMutation: vi.fn(),
  acceptProposal: vi.fn(),
  rejectProposal: vi.fn(),
  subscribeToSessionEvents: vi.fn(() => ({ close: vi.fn() })),
}));

function fakeSession(
  overrides: Partial<sessionClient.GraphSession> = {},
): sessionClient.GraphSession {
  return {
    id: "sess-1",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 0,
    proposals: {},
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useGraphStore.getState().reset();
  useSessionStore.setState({
    sessionId: null,
    version: null,
    proposals: {},
    status: "idle",
    error: null,
    rebaseNeeded: false,
    rebaseMessage: null,
  });
});

test("shows the start/join form when there is no active session", () => {
  render(<SessionPanel />);
  expect(screen.getByTestId("session-start")).toBeInTheDocument();
  expect(screen.getByTestId("session-join-input")).toBeInTheDocument();
});

test("Start session calls createAndJoin and renders the active session view", async () => {
  vi.mocked(sessionClient.createSession).mockResolvedValue(
    fakeSession({ id: "abc" }),
  );

  render(<SessionPanel />);
  fireEvent.click(screen.getByTestId("session-start"));

  await waitFor(() => {
    expect(screen.getByText("Session abc")).toBeInTheDocument();
  });
  expect(sessionClient.createSession).toHaveBeenCalledTimes(1);
});

test("Join calls join with the typed session id", async () => {
  vi.mocked(sessionClient.getSession).mockResolvedValue(
    fakeSession({ id: "xyz" }),
  );

  render(<SessionPanel />);
  fireEvent.change(screen.getByTestId("session-join-input"), {
    target: { value: "xyz" },
  });
  fireEvent.click(screen.getByTestId("session-join"));

  await waitFor(() => {
    expect(sessionClient.getSession).toHaveBeenCalledWith("xyz");
  });
});

test("shows the error message when connecting fails", async () => {
  vi.mocked(sessionClient.createSession).mockRejectedValue(
    new Error("server unreachable"),
  );

  render(<SessionPanel />);
  fireEvent.click(screen.getByTestId("session-start"));

  await waitFor(() => {
    expect(screen.getByTestId("session-error")).toHaveTextContent(
      "server unreachable",
    );
  });
});

test("Leave session returns to the start/join form", async () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
  });

  render(<SessionPanel />);
  expect(screen.getByText("Session abc")).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("session-leave"));

  expect(screen.getByTestId("session-start")).toBeInTheDocument();
});

test("shows the rebase banner and dismisses it", () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    rebaseNeeded: true,
    rebaseMessage: "stale_version: ...",
  });

  render(<SessionPanel />);
  expect(screen.getByTestId("session-rebase-banner")).toHaveTextContent(
    "stale_version",
  );

  fireEvent.click(screen.getByTestId("session-rebase-dismiss"));

  expect(screen.queryByTestId("session-rebase-banner")).not.toBeInTheDocument();
});
