import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { useGraphStore } from "../store/graphStore";
import * as sessionClient from "./sessionClient";
import { ChatModal } from "./ChatModal";
import { useSessionStore } from "./sessionStore";

vi.mock("./sessionClient", () => ({
  createSession: vi.fn(),
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
  getAvailableAgents: vi.fn(),
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
    reviews: {},
    gates: {},
    chat: { backend: null, backend_thread_id: null, turns: [] },
    status: "idle",
    error: null,
    rebaseNeeded: false,
    rebaseMessage: null,
  });
  vi.mocked(sessionClient.getAvailableAgents).mockResolvedValue([
    "claude",
    "opencode",
  ]);
});

test("auto-creates a session on mount when none is active", async () => {
  vi.mocked(sessionClient.createSession).mockResolvedValue(
    fakeSession({ id: "abc" }),
  );

  render(<ChatModal onClose={vi.fn()} />);

  await waitFor(() => {
    expect(sessionClient.createSession).toHaveBeenCalledTimes(1);
  });
});

test("shows the backend picker once a session exists and no chat is active", async () => {
  vi.mocked(sessionClient.createSession).mockResolvedValue(
    fakeSession({ id: "abc" }),
  );

  render(<ChatModal onClose={vi.fn()} />);

  await waitFor(() => {
    expect(screen.getByTestId("chat-backend-select")).toBeInTheDocument();
  });
});

test("shows a message when no agent CLIs are detected", async () => {
  vi.mocked(sessionClient.createSession).mockResolvedValue(
    fakeSession({ id: "abc" }),
  );
  vi.mocked(sessionClient.getAvailableAgents).mockResolvedValue([]);

  render(<ChatModal onClose={vi.fn()} />);

  await waitFor(() => {
    expect(screen.getByTestId("chat-no-agents")).toBeInTheDocument();
  });
});

test("Start chat starts the chat with the selected backend and typed message", async () => {
  vi.mocked(sessionClient.createSession).mockResolvedValue(
    fakeSession({ id: "abc" }),
  );
  vi.mocked(sessionClient.startChat).mockResolvedValue({
    id: "turn-1",
    backend: "claude",
    user_message: "hello",
    narration: [],
    agent_message: null,
    status: "running",
    error: null,
  });

  render(<ChatModal onClose={vi.fn()} />);

  await waitFor(() => {
    expect(screen.getByTestId("chat-backend-select")).toBeInTheDocument();
  });
  fireEvent.change(screen.getByTestId("chat-draft-message"), {
    target: { value: "hello" },
  });
  fireEvent.click(screen.getByTestId("chat-start-button"));

  await waitFor(() => {
    expect(sessionClient.startChat).toHaveBeenCalledWith("abc", {
      backend: "claude",
      message: "hello",
    });
  });
});

test("shows the active view once a chat backend is set", () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: {
      backend: "claude",
      backend_thread_id: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "hello",
          narration: [],
          agent_message: "Hi there.",
          status: "completed",
          error: null,
        },
      ],
    },
  });

  render(<ChatModal onClose={vi.fn()} />);

  expect(screen.getByTestId("chat-active-view")).toHaveTextContent("claude");
  expect(screen.getByTestId("chat-end-button")).not.toBeDisabled();
});

test("End chat button is disabled while the latest turn is running", () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: {
      backend: "claude",
      backend_thread_id: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "hello",
          narration: [],
          agent_message: null,
          status: "running",
          error: null,
        },
      ],
    },
  });

  render(<ChatModal onClose={vi.fn()} />);

  expect(screen.getByTestId("chat-end-button")).toBeDisabled();
});

test("End chat calls the store's endChat action", async () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: {
      backend: "claude",
      backend_thread_id: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "hello",
          narration: [],
          agent_message: "done",
          status: "completed",
          error: null,
        },
      ],
    },
  });
  vi.mocked(sessionClient.endChat).mockResolvedValue(
    fakeSession({
      id: "abc",
      collab: {
        reviews: {},
        gates: {},
        chat: { backend: null, backend_thread_id: null, turns: [] },
      },
    }),
  );

  render(<ChatModal onClose={vi.fn()} />);
  fireEvent.click(screen.getByTestId("chat-end-button"));

  await waitFor(() => {
    expect(sessionClient.endChat).toHaveBeenCalledWith("abc");
  });
});

test("renders each turn's user message, narration, and agent reply", () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: {
      backend: "claude",
      backend_thread_id: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "add a cleaning step",
          narration: ["proposing mutation: add node clean.drop_na"],
          agent_message: "Added the node.",
          status: "completed",
          error: null,
        },
      ],
    },
  });

  render(<ChatModal onClose={vi.fn()} />);

  const turnEl = screen.getByTestId("chat-turn");
  expect(turnEl).toHaveTextContent("add a cleaning step");
  expect(turnEl).toHaveTextContent(
    "proposing mutation: add node clean.drop_na",
  );
  expect(turnEl).toHaveTextContent("Added the node.");
});

test("Send posts a new message with the existing backend", async () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: {
      backend: "claude",
      backend_thread_id: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "hello",
          narration: [],
          agent_message: "hi",
          status: "completed",
          error: null,
        },
      ],
    },
  });
  vi.mocked(sessionClient.startChat).mockResolvedValue({
    id: "turn-2",
    backend: "claude",
    user_message: "again",
    narration: [],
    agent_message: null,
    status: "running",
    error: null,
  });

  render(<ChatModal onClose={vi.fn()} />);
  fireEvent.change(screen.getByTestId("chat-message-input"), {
    target: { value: "again" },
  });
  fireEvent.click(screen.getByTestId("chat-send-button"));

  await waitFor(() => {
    expect(sessionClient.startChat).toHaveBeenCalledWith("abc", {
      backend: "claude",
      message: "again",
    });
  });
});

test("shows a Stop button instead of Send while the latest turn is running, and Stop calls stopChat", async () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: {
      backend: "claude",
      backend_thread_id: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "hello",
          narration: [],
          agent_message: null,
          status: "running",
          error: null,
        },
      ],
    },
  });
  vi.mocked(sessionClient.stopChatTurn).mockResolvedValue({
    id: "turn-1",
    backend: "claude",
    user_message: "hello",
    narration: [],
    agent_message: null,
    status: "interrupted",
    error: null,
  });

  render(<ChatModal onClose={vi.fn()} />);
  expect(screen.queryByTestId("chat-send-button")).not.toBeInTheDocument();
  expect(screen.getByTestId("chat-message-input")).toBeDisabled();

  fireEvent.click(screen.getByTestId("chat-stop-button"));

  await waitFor(() => {
    expect(sessionClient.stopChatTurn).toHaveBeenCalledWith("abc", "turn-1");
  });
});

test("Collapse button switches to the pill view, which expands back on click", () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: { backend: "claude", backend_thread_id: null, turns: [] },
  });

  render(<ChatModal onClose={vi.fn()} />);
  expect(screen.getByTestId("chat-active-view")).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("chat-collapse-button"));

  expect(screen.queryByTestId("chat-active-view")).not.toBeInTheDocument();
  expect(screen.getByTestId("chat-modal-pill")).toHaveTextContent("claude chat");

  fireEvent.click(screen.getByTestId("chat-modal-pill"));

  expect(screen.getByTestId("chat-active-view")).toBeInTheDocument();
});

test("the pill shows a working indicator while a turn is running", () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: {
      backend: "claude",
      backend_thread_id: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "hello",
          narration: [],
          agent_message: null,
          status: "running",
          error: null,
        },
      ],
    },
  });

  render(<ChatModal onClose={vi.fn()} />);
  fireEvent.click(screen.getByTestId("chat-collapse-button"));

  expect(screen.getByTestId("chat-modal-pill")).toHaveTextContent(
    "claude is working",
  );
});

test("the dock's close button calls onClose", () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: {
      backend: "claude",
      backend_thread_id: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "hello",
          narration: [],
          agent_message: "hi",
          status: "completed",
          error: null,
        },
      ],
    },
  });
  const onClose = vi.fn();

  render(<ChatModal onClose={onClose} />);
  fireEvent.click(screen.getByTestId("chat-dock-close"));

  expect(onClose).toHaveBeenCalledTimes(1);
});

test("a failed turn's activity log auto-expands", () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: {
      backend: "claude",
      backend_thread_id: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "add a cleaning step",
          narration: ["proposing mutation: add node clean.drop_na"],
          agent_message: null,
          status: "failed",
          error: "boom",
        },
      ],
    },
  });

  render(<ChatModal onClose={vi.fn()} />);

  const details = screen.getByTestId(
    "chat-turn-activity",
  ) as HTMLDetailsElement;
  expect(details.open).toBe(true);
  expect(screen.getByTestId("chat-turn-activity-summary")).toHaveTextContent(
    "Worked through 1 step",
  );
});

test("a completed turn's activity log stays collapsed by default", () => {
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    status: "connected",
    chat: {
      backend: "claude",
      backend_thread_id: null,
      turns: [
        {
          id: "turn-1",
          backend: "claude",
          user_message: "add a cleaning step",
          narration: ["proposing mutation: add node clean.drop_na"],
          agent_message: "Added the node.",
          status: "completed",
          error: null,
        },
      ],
    },
  });

  render(<ChatModal onClose={vi.fn()} />);

  const details = screen.getByTestId(
    "chat-turn-activity",
  ) as HTMLDetailsElement;
  expect(details.open).toBe(false);
});
