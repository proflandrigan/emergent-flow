import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import * as sessionClient from "./sessionClient";
import { GatePanel } from "./GatePanel";
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
}));

function gate(overrides: Partial<sessionClient.Gate> = {}): sessionClient.Gate {
  return {
    id: "g1",
    phase: "review",
    kind: "confirm",
    description: "Confirm the analysis",
    status: "open",
    decisions: [],
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
    status: "idle",
    error: null,
    rebaseNeeded: false,
    rebaseMessage: null,
  });
});

test("renders nothing when there is no active session", () => {
  const { container } = render(<GatePanel />);
  expect(container).toBeEmptyDOMElement();
});

test("renders an empty state when the session has no gates", () => {
  useSessionStore.setState({ sessionId: "abc" });
  render(<GatePanel />);
  expect(screen.getByTestId("gate-panel-empty")).toBeInTheDocument();
});

test("renders a gate card with phase, kind, status, and description", () => {
  useSessionStore.setState({
    sessionId: "abc",
    gates: { g1: gate() },
  });

  render(<GatePanel />);

  expect(screen.getByText("review — confirm")).toBeInTheDocument();
  expect(screen.getByText("Confirm the analysis")).toBeInTheDocument();
  expect(screen.getByTestId("gate-status")).toHaveTextContent("open");
});

test("renders decisions", () => {
  useSessionStore.setState({
    sessionId: "abc",
    gates: {
      g1: gate({
        decisions: [{ id: "d1", author: "human", text: "looks good" }],
      }),
    },
  });

  render(<GatePanel />);

  expect(screen.getByTestId("gate-decision")).toHaveTextContent(
    "human: looks good",
  );
});

test("Gate open banner appears only when at least one gate is open and shows the right count", () => {
  useSessionStore.setState({
    sessionId: "abc",
    gates: {
      g1: gate({ status: "open" }),
      g2: gate({ id: "g2", status: "closed" }),
    },
  });

  render(<GatePanel />);

  expect(screen.getByTestId("gate-open-banner")).toHaveTextContent(
    "1 gate(s) open",
  );
});

test("Gate open banner does not appear when no gates are open", () => {
  useSessionStore.setState({
    sessionId: "abc",
    gates: { g1: gate({ status: "closed" }) },
  });

  render(<GatePanel />);

  expect(screen.queryByTestId("gate-open-banner")).not.toBeInTheDocument();
});

test("clicking Close does NOT immediately call closeGateRequest but reveals the confirm control", () => {
  useSessionStore.setState({
    sessionId: "abc",
    gates: { g1: gate() },
  });

  render(<GatePanel />);

  fireEvent.click(screen.getByTestId("gate-close"));

  expect(sessionClient.closeGateRequest).not.toHaveBeenCalled();
  expect(screen.getByTestId("gate-close-confirm")).toBeInTheDocument();
  expect(screen.getByTestId("gate-close-cancel")).toBeInTheDocument();
});

test("clicking Confirm close calls closeGateRequest", async () => {
  vi.mocked(sessionClient.closeGateRequest).mockResolvedValue(
    gate({ status: "closed" }),
  );

  useSessionStore.setState({
    sessionId: "abc",
    gates: { g1: gate() },
  });

  render(<GatePanel />);

  fireEvent.click(screen.getByTestId("gate-close"));
  fireEvent.click(screen.getByTestId("gate-close-confirm"));

  await vi.waitFor(() => {
    expect(sessionClient.closeGateRequest).toHaveBeenCalledWith("abc", "g1");
  });
});

test("clicking Skip calls skipGateRequest", async () => {
  vi.mocked(sessionClient.skipGateRequest).mockResolvedValue(
    gate({ status: "skipped" }),
  );

  useSessionStore.setState({
    sessionId: "abc",
    gates: { g1: gate() },
  });

  render(<GatePanel />);

  fireEvent.click(screen.getByTestId("gate-skip"));

  await vi.waitFor(() => {
    expect(sessionClient.skipGateRequest).toHaveBeenCalledWith("abc", "g1");
  });
});

test("submitting the decision form calls postGateDecision and clears the input", async () => {
  vi.mocked(sessionClient.postGateDecision).mockResolvedValue(
    gate({
      decisions: [{ id: "d1", author: "human", text: "proceed" }],
    }),
  );

  useSessionStore.setState({
    sessionId: "abc",
    gates: { g1: gate() },
  });

  render(<GatePanel />);

  fireEvent.change(screen.getByTestId("gate-decision-input"), {
    target: { value: "proceed" },
  });
  fireEvent.click(screen.getByTestId("gate-decision-submit"));

  await vi.waitFor(() => {
    expect(sessionClient.postGateDecision).toHaveBeenCalledWith("abc", "g1", {
      author: "human",
      text: "proceed",
    });
  });

  const input = screen.getByTestId("gate-decision-input") as HTMLInputElement;
  expect(input.value).toBe("");
});
