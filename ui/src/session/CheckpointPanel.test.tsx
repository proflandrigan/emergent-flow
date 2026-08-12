import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { useGraphStore } from "../store/graphStore";
import * as sessionClient from "./sessionClient";
import { CheckpointPanel } from "./CheckpointPanel";
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
  revertCheckpoint: vi.fn(),
  listCheckpoints: vi.fn(),
}));

function checkpoint(
  overrides: Partial<sessionClient.Checkpoint> = {},
): sessionClient.Checkpoint {
  return {
    id: "cp-1",
    kind: "edit",
    author: "ml_engineer",
    description: "added a cleaning step",
    timestamp: 1000,
    base_version: 0,
    resulting_version: 1,
    mutation: { base_version: 0 },
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useGraphStore.getState().reset();
  useSessionStore.setState({
    sessionId: "abc",
    version: 1,
    proposals: {},
    reviews: {},
    gates: {},
    chat: {
      backend: "claude",
      backend_thread_id: null,
      active_persona: null,
      turns: [],
    },
    attempts: {},
    checkpoints: {},
    status: "connected",
    error: null,
    rebaseNeeded: false,
    rebaseMessage: null,
  });
});

test("renders checkpoints sorted newest-first", () => {
  useSessionStore.setState({
    checkpoints: {
      older: checkpoint({
        id: "older",
        description: "older",
        timestamp: 1000,
        resulting_version: 1,
      }),
      newer: checkpoint({
        id: "newer",
        description: "newer",
        timestamp: 3000,
        resulting_version: 2,
      }),
      middle: checkpoint({
        id: "middle",
        description: "middle",
        timestamp: 2000,
        resulting_version: 2,
      }),
    },
  });

  render(<CheckpointPanel />);

  const rows = screen.getAllByTestId("checkpoint-row");
  expect(rows).toHaveLength(3);
  expect(rows[0]).toHaveTextContent("newer");
  expect(rows[1]).toHaveTextContent("middle");
  expect(rows[2]).toHaveTextContent("older");
});

test("shows kind badge, author, description, and version range", () => {
  useSessionStore.setState({
    checkpoints: {
      cp1: checkpoint({
        id: "cp1",
        kind: "edit",
        author: "ml_engineer",
        description: "added a cleaning step",
        base_version: 0,
        resulting_version: 1,
      }),
      cp2: checkpoint({
        id: "cp2",
        kind: "revert",
        author: "human",
        description: "",
        base_version: 1,
        resulting_version: 0,
      }),
    },
  });

  render(<CheckpointPanel />);

  const rows = screen.getAllByTestId("checkpoint-row");
  const editRow = rows[0];
  expect(editRow).toHaveTextContent("Edit");
  expect(editRow).toHaveTextContent("ml_engineer");
  expect(editRow).toHaveTextContent("added a cleaning step");
  expect(editRow).toHaveTextContent("v0 → v1");

  const revertRow = rows[1];
  expect(revertRow).toHaveTextContent("Revert");
  expect(revertRow).toHaveTextContent("human");
  expect(revertRow).toHaveTextContent("Agent edit");
  expect(revertRow).toHaveTextContent("v1 → v0");
});

test("only the latest edit offers a Revert button", () => {
  useSessionStore.setState({
    version: 2,
    checkpoints: {
      latest: checkpoint({
        id: "latest",
        kind: "edit",
        resulting_version: 2,
      }),
      older: checkpoint({
        id: "older",
        kind: "edit",
        resulting_version: 1,
      }),
      revert: checkpoint({
        id: "revert",
        kind: "revert",
        resulting_version: 2,
      }),
    },
  });

  render(<CheckpointPanel />);

  expect(
    screen.getByTestId("checkpoint-revert-button-latest"),
  ).toBeInTheDocument();
  expect(
    screen.queryByTestId("checkpoint-revert-button-older"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByTestId("checkpoint-revert-button-revert"),
  ).not.toBeInTheDocument();
});

test("clicking revert calls sessionClient.revertCheckpoint and disables the button while loading", async () => {
  let resolveRevert: (value: sessionClient.GraphSession) => void = () => {};
  vi.mocked(sessionClient.revertCheckpoint).mockReturnValue(
    new Promise((resolve) => {
      resolveRevert = resolve;
    }),
  );
  useSessionStore.setState({
    version: 1,
    checkpoints: {
      cp1: checkpoint({ id: "cp1", resulting_version: 1 }),
    },
  });

  render(<CheckpointPanel />);

  const button = screen.getByTestId("checkpoint-revert-button-cp1");
  fireEvent.click(button);

  expect(sessionClient.revertCheckpoint).toHaveBeenCalledWith("abc", "cp1");
  expect(button).toBeDisabled();
  expect(button).toHaveTextContent("Reverting…");

  resolveRevert({
    id: "abc",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 1,
    proposals: {},
    collab: {
      reviews: {},
      gates: {},
      chat: {
        backend: "claude",
        backend_thread_id: null,
        active_persona: null,
        turns: [],
      },
      checkpoints: {
        cp1: checkpoint({ id: "cp1", resulting_version: 1 }),
      },
    },
  });
  await vi.waitFor(() => {
    expect(button).not.toBeDisabled();
  });
});

test("refresh calls sessionClient.listCheckpoints", async () => {
  vi.mocked(sessionClient.listCheckpoints).mockResolvedValue({
    checkpoints: [],
  });

  render(<CheckpointPanel />);
  fireEvent.click(screen.getByTestId("checkpoint-refresh-button"));

  await vi.waitFor(() => {
    expect(sessionClient.listCheckpoints).toHaveBeenCalledWith("abc");
  });
});

test("renders an empty state when there are no checkpoints", () => {
  render(<CheckpointPanel />);
  expect(screen.getByText("No checkpoints yet.")).toBeInTheDocument();
});
