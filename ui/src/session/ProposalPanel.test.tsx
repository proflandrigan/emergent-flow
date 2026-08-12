import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import type { NodeModel } from "../store/model";
import * as sessionClient from "./sessionClient";
import { ProposalPanel } from "./ProposalPanel";
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
  createGate: vi.fn(),
  closeGateRequest: vi.fn(),
  skipGateRequest: vi.fn(),
  postGateDecision: vi.fn(),
}));

function pendingProposal(
  overrides: Partial<sessionClient.StoredProposal> = {},
): sessionClient.StoredProposal {
  return {
    id: "p1",
    mutation: {
      base_version: 0,
      author: "ml_engineer",
      description: "add a describe node",
    },
    diagnostics: { diagnostics: [], edge_compatibility: {} },
    status: "pending",
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

test("renders nothing when there is no active session", () => {
  const { container } = render(<ProposalPanel />);
  expect(container).toBeEmptyDOMElement();
});

test("renders an empty state when the session has no proposals", () => {
  useSessionStore.setState({ sessionId: "abc" });

  render(<ProposalPanel />);

  expect(screen.getByTestId("proposal-panel-empty")).toBeInTheDocument();
});

test("renders author, description, and a clean verdict for a proposal with no diagnostics", () => {
  useSessionStore.setState({
    sessionId: "abc",
    proposals: { p1: pendingProposal() },
  });

  render(<ProposalPanel />);

  expect(screen.getByText("ml_engineer")).toBeInTheDocument();
  expect(screen.getByText("add a describe node")).toBeInTheDocument();
  expect(screen.getByTestId("proposal-verdict-clean")).toBeInTheDocument();
});

test("renders each diagnostic finding when present", () => {
  useSessionStore.setState({
    sessionId: "abc",
    proposals: {
      p1: pendingProposal({
        diagnostics: {
          diagnostics: [
            { severity: "warning", code: "w1", message: "check this" },
          ],
          edge_compatibility: {},
        },
      }),
    },
  });

  render(<ProposalPanel />);

  expect(screen.getByTestId("proposal-diagnostics")).toHaveTextContent(
    "check this",
  );
});

test("Accept calls sessionStore.accept for the right proposal id", async () => {
  vi.mocked(sessionClient.acceptProposal).mockResolvedValue({
    id: "abc",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 1,
    proposals: {},
  });
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    proposals: { p1: pendingProposal() },
  });

  render(<ProposalPanel />);
  fireEvent.click(screen.getByTestId("proposal-accept"));

  await vi.waitFor(() => {
    expect(sessionClient.acceptProposal).toHaveBeenCalledWith("abc", "p1");
  });
});

test("Reject calls sessionStore.reject for the right proposal id", async () => {
  vi.mocked(sessionClient.rejectProposal).mockResolvedValue({
    id: "abc",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 0,
    proposals: {},
  });
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    proposals: { p1: pendingProposal() },
  });

  render(<ProposalPanel />);
  fireEvent.click(screen.getByTestId("proposal-reject"));

  await vi.waitFor(() => {
    expect(sessionClient.rejectProposal).toHaveBeenCalledWith("abc", "p1");
  });
});

test("Edit into own merges the mutation's added nodes into the canvas graph and rejects the proposal", async () => {
  vi.mocked(sessionClient.rejectProposal).mockResolvedValue({
    id: "abc",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 0,
    proposals: {},
  });
  const proposal = pendingProposal({
    mutation: {
      base_version: 0,
      author: "ml_engineer",
      add_nodes: [{ type: "stats.describe", ports: [], params: [] }],
    },
  });
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    proposals: { p1: proposal },
  });

  render(<ProposalPanel />);
  fireEvent.click(screen.getByTestId("proposal-edit-into-own"));

  const nodes = Object.values(useGraphStore.getState().nodes) as NodeModel[];
  expect(nodes.some((n) => n.type === "stats.describe")).toBe(true);

  await vi.waitFor(() => {
    expect(sessionClient.rejectProposal).toHaveBeenCalledWith("abc", "p1");
  });
});

test("edit-into-own re-flows the merged graph with tidyLayout", async () => {
  vi.mocked(sessionClient.rejectProposal).mockResolvedValue({
    id: "abc",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 0,
    proposals: {},
  });
  const loadModel = vi.fn();
  const tidyLayout = vi.fn();
  const getStateSpy = vi
    .spyOn(useGraphStore, "getState")
    .mockReturnValue({
      ...useGraphStore.getState(),
      loadModel,
      tidyLayout,
    });
  const proposal = pendingProposal({
    mutation: {
      base_version: 0,
      author: "ml_engineer",
      add_nodes: [{ type: "stats.describe", ports: [], params: [] }],
    },
  });
  useSessionStore.setState({
    sessionId: "abc",
    version: 0,
    proposals: { p1: proposal },
  });

  render(<ProposalPanel />);
  fireEvent.click(screen.getByTestId("proposal-edit-into-own"));

  expect(loadModel).toHaveBeenCalled();
  expect(tidyLayout).toHaveBeenCalled();
  expect(loadModel.mock.invocationCallOrder[0]).toBeLessThan(
    tidyLayout.mock.invocationCallOrder[0],
  );

  getStateSpy.mockRestore();
});

test("a decided proposal shows its status instead of action buttons", () => {
  useSessionStore.setState({
    sessionId: "abc",
    proposals: { p1: pendingProposal({ status: "accepted" }) },
  });

  render(<ProposalPanel />);

  expect(screen.getByTestId("proposal-status")).toHaveTextContent("accepted");
  expect(screen.queryByTestId("proposal-accept")).not.toBeInTheDocument();
});
