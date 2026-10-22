import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { useGraphStore } from "../store/graphStore";
import * as sessionClient from "./sessionClient";
import { ReviewPanel } from "./ReviewPanel";
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

function reviewThread(
  overrides: Partial<sessionClient.ReviewThread> = {},
): sessionClient.ReviewThread {
  return {
    id: "r1",
    author: "ml_engineer",
    findings: [],
    comments: [],
    fix: null,
    status: "open",
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
  const { container } = render(<ReviewPanel />);
  expect(container).toBeEmptyDOMElement();
});

test("renders an empty state when the session has no reviews", () => {
  useSessionStore.setState({ sessionId: "abc" });
  render(<ReviewPanel />);
  expect(screen.getByTestId("review-panel-empty")).toBeInTheDocument();
});

test("renders a thread's author, findings, and comments", () => {
  useSessionStore.setState({
    sessionId: "abc",
    reviews: {
      r1: reviewThread({
        findings: [
          {
            severity: "warning",
            code: "w1",
            message: "possible grain mismatch",
            node_id: "n1",
          },
        ],
        comments: [{ id: "c1", author: "human", text: "good catch" }],
      }),
    },
  });

  render(<ReviewPanel />);

  expect(screen.getByText("ml_engineer")).toBeInTheDocument();
  expect(screen.getByText("possible grain mismatch")).toBeInTheDocument();
  expect(screen.getByTestId("review-comment")).toHaveTextContent("good catch");
});

test("shows Apply fix only when a fix mutation is attached", () => {
  useSessionStore.setState({
    sessionId: "abc",
    reviews: { r1: reviewThread({ fix: { base_version: 0 } }) },
  });

  render(<ReviewPanel />);

  expect(screen.getByTestId("review-apply-fix")).toBeInTheDocument();
});

test("does not show Apply fix when there is no fix", () => {
  useSessionStore.setState({
    sessionId: "abc",
    reviews: { r1: reviewThread() },
  });

  render(<ReviewPanel />);

  expect(screen.queryByTestId("review-apply-fix")).not.toBeInTheDocument();
});

test("highlightId marks only the matching thread", () => {
  useSessionStore.setState({
    sessionId: "abc",
    reviews: { r1: reviewThread(), r2: reviewThread({ id: "r2" }) },
  });

  render(<ReviewPanel highlightId="r2" />);

  const threads = screen.getAllByTestId("review-thread");
  expect(threads[0]).not.toHaveAttribute("data-highlighted");
  expect(threads[1]).toHaveAttribute("data-highlighted", "true");
});

test("Copy link writes a URL ending with the review fragment", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
  useSessionStore.setState({
    sessionId: "abc",
    reviews: { r1: reviewThread() },
  });

  render(<ReviewPanel />);
  fireEvent.click(screen.getByTestId("review-copy-link"));

  await waitFor(() =>
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/#review=r1$/)),
  );
});

test("Reply posts a comment authored by human and clears the input", async () => {
  vi.mocked(sessionClient.addReviewComment).mockResolvedValue(
    reviewThread({ comments: [{ id: "c1", author: "human", text: "ok" }] }),
  );
  useSessionStore.setState({
    sessionId: "abc",
    reviews: { r1: reviewThread() },
  });

  render(<ReviewPanel />);
  fireEvent.change(screen.getByTestId("review-reply-input"), {
    target: { value: "ok" },
  });
  fireEvent.click(screen.getByTestId("review-reply-submit"));

  await vi.waitFor(() => {
    expect(sessionClient.addReviewComment).toHaveBeenCalledWith("abc", "r1", {
      author: "human",
      text: "ok",
    });
  });
});
