import { beforeEach, describe, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import type { SessionEvent } from "../generated/session_event";
import * as sessionClient from "./sessionClient";
import { useSessionStore } from "./sessionStore";

vi.mock("./sessionClient", () => ({
  createSession: vi.fn(),
  getSession: vi.fn(),
  deleteSession: vi.fn(),
  replaceSessionGraph: vi.fn(),
  proposeMutation: vi.fn(),
  acceptProposal: vi.fn(),
  rejectProposal: vi.fn(),
  subscribeToSessionEvents: vi.fn(),
  createReview: vi.fn(),
  addReviewComment: vi.fn(),
}));

function emptyGraph() {
  return { paradigm: "functional" as const, nodes: {}, edges: {} };
}

function fakeSession(
  overrides: Partial<sessionClient.GraphSession> = {},
): sessionClient.GraphSession {
  return {
    id: "sess-1",
    graph: emptyGraph(),
    version: 0,
    proposals: {},
    ...overrides,
  };
}

// Captures the onEvent callback subscribeToSessionEvents was given, so tests can simulate
// SSE frames arriving.
let capturedOnEvent: ((event: SessionEvent) => void) | null = null;

beforeEach(() => {
  vi.clearAllMocks();
  useGraphStore.getState().reset();
  useSessionStore.getState().leave();
  capturedOnEvent = null;
  vi.mocked(sessionClient.subscribeToSessionEvents).mockImplementation(
    (_id, onEvent) => {
      capturedOnEvent = onEvent;
      return { close: vi.fn() };
    },
  );
});

describe("createAndJoin", () => {
  test("creates a session seeded from the current canvas graph and loads the server's graph back", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );

    await useSessionStore.getState().createAndJoin();

    expect(sessionClient.createSession).toHaveBeenCalledTimes(1);
    const state = useSessionStore.getState();
    expect(state.sessionId).toBe("abc");
    expect(state.version).toBe(0);
    expect(state.status).toBe("connected");
    expect(sessionClient.subscribeToSessionEvents).toHaveBeenCalledWith(
      "abc",
      expect.any(Function),
    );
  });

  test("sets status error on failure", async () => {
    vi.mocked(sessionClient.createSession).mockRejectedValue(new Error("boom"));

    await useSessionStore.getState().createAndJoin();

    const state = useSessionStore.getState();
    expect(state.status).toBe("error");
    expect(state.error).toBe("boom");
  });
});

describe("join", () => {
  test("loads the existing session's graph and proposals", async () => {
    const proposal: sessionClient.StoredProposal = {
      id: "p1",
      mutation: { base_version: 0 },
      diagnostics: { diagnostics: [], edge_compatibility: {} },
      status: "pending",
    };
    vi.mocked(sessionClient.getSession).mockResolvedValue(
      fakeSession({ id: "xyz", version: 2, proposals: { p1: proposal } }),
    );

    await useSessionStore.getState().join("xyz");

    const state = useSessionStore.getState();
    expect(state.sessionId).toBe("xyz");
    expect(state.version).toBe(2);
    expect(state.proposals.p1).toEqual(proposal);
  });
});

describe("pushLocalGraph", () => {
  test("pushes toIR() with the current expected version and updates state on success", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    vi.mocked(sessionClient.replaceSessionGraph).mockResolvedValue(
      fakeSession({ id: "abc", version: 1 }),
    );

    await useSessionStore.getState().pushLocalGraph();

    expect(sessionClient.replaceSessionGraph).toHaveBeenCalledWith(
      "abc",
      expect.any(Object),
      0,
    );
    expect(useSessionStore.getState().version).toBe(1);
    expect(useSessionStore.getState().rebaseNeeded).toBe(false);
  });

  test("sets rebaseNeeded (not a silent overwrite) on a stale_version rejection", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    vi.mocked(sessionClient.replaceSessionGraph).mockRejectedValue(
      new Error(
        "stale_version: session 'abc': expected version 0, but the session is at version 3.",
      ),
    );

    await useSessionStore.getState().pushLocalGraph();

    const state = useSessionStore.getState();
    expect(state.rebaseNeeded).toBe(true);
    expect(state.rebaseMessage).toContain("stale_version");
    // The local graph must NOT have been silently replaced.
    expect(state.version).toBe(0);
  });
});

describe("propose / accept / reject", () => {
  test("propose stores the returned proposal", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const proposal: sessionClient.StoredProposal = {
      id: "p1",
      mutation: { base_version: 0 },
      diagnostics: { diagnostics: [], edge_compatibility: {} },
      status: "pending",
    };
    vi.mocked(sessionClient.proposeMutation).mockResolvedValue(proposal);

    const result = await useSessionStore
      .getState()
      .propose({ base_version: 0 });

    expect(result).toEqual(proposal);
    expect(useSessionStore.getState().proposals.p1).toEqual(proposal);
  });

  test("accept loads the returned graph into useGraphStore", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    vi.mocked(sessionClient.acceptProposal).mockResolvedValue(
      fakeSession({
        id: "abc",
        version: 1,
        graph: { paradigm: "functional", nodes: {}, edges: {} },
      }),
    );

    await useSessionStore.getState().accept("p1");

    expect(sessionClient.acceptProposal).toHaveBeenCalledWith("abc", "p1");
    expect(useSessionStore.getState().version).toBe(1);
  });

  test("reject updates proposals without touching the canvas graph", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const loadIRSpy = vi.spyOn(useGraphStore.getState(), "loadIR");
    vi.mocked(sessionClient.rejectProposal).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );

    await useSessionStore.getState().reject("p1");

    expect(sessionClient.rejectProposal).toHaveBeenCalledWith("abc", "p1");
    expect(loadIRSpy).not.toHaveBeenCalled();
  });
});

describe("SSE event handling", () => {
  test("proposal_added refreshes proposals but does not reload the canvas graph", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const proposal: sessionClient.StoredProposal = {
      id: "p2",
      mutation: { base_version: 0 },
      diagnostics: { diagnostics: [], edge_compatibility: {} },
      status: "pending",
    };
    vi.mocked(sessionClient.getSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0, proposals: { p2: proposal } }),
    );
    const loadIRSpy = vi.spyOn(useGraphStore.getState(), "loadIR");

    expect(capturedOnEvent).not.toBeNull();
    await capturedOnEvent?.({
      type: "proposal_added",
      session_id: "abc",
      proposal_id: "p2",
    });

    expect(useSessionStore.getState().proposals.p2).toEqual(proposal);
    expect(loadIRSpy).not.toHaveBeenCalled();
  });

  test("proposal_accepted reloads the canvas graph from the server", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    vi.mocked(sessionClient.getSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 1 }),
    );
    const loadIRSpy = vi.spyOn(useGraphStore.getState(), "loadIR");

    await capturedOnEvent?.({
      type: "proposal_accepted",
      session_id: "abc",
      proposal_id: "p1",
      version: 1,
    });

    expect(loadIRSpy).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().version).toBe(1);
  });

  test("events for a different session id are ignored", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    await capturedOnEvent?.({
      type: "graph_replaced",
      session_id: "some-other-session",
      version: 99,
    });

    expect(sessionClient.getSession).not.toHaveBeenCalled();
    expect(useSessionStore.getState().version).toBe(0);
  });
});

describe("leave", () => {
  test("resets connection state and closes the subscription", async () => {
    const close = vi.fn();
    vi.mocked(sessionClient.subscribeToSessionEvents).mockReturnValue({
      close,
    });
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    useSessionStore.getState().leave();

    expect(close).toHaveBeenCalledTimes(1);
    const state = useSessionStore.getState();
    expect(state.sessionId).toBeNull();
    expect(state.status).toBe("idle");
  });
});

describe("postReview / postReviewComment / applyFix", () => {
  test("postReview stores the returned thread", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const thread: sessionClient.ReviewThread = {
      id: "r1",
      author: "ml_engineer",
      findings: [],
      comments: [],
      fix: null,
      status: "open",
    };
    vi.mocked(sessionClient.createReview).mockResolvedValue(thread);

    const result = await useSessionStore
      .getState()
      .postReview({ author: "ml_engineer" });

    expect(result).toEqual(thread);
    expect(useSessionStore.getState().reviews.r1).toEqual(thread);
  });

  test("postReviewComment updates the thread", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const updated: sessionClient.ReviewThread = {
      id: "r1",
      author: "ml_engineer",
      findings: [],
      comments: [{ id: "c1", author: "human", text: "ok" }],
      fix: null,
      status: "open",
    };
    vi.mocked(sessionClient.addReviewComment).mockResolvedValue(updated);

    await useSessionStore
      .getState()
      .postReviewComment("r1", { author: "human", text: "ok" });

    expect(useSessionStore.getState().reviews.r1.comments).toHaveLength(1);
  });

  test("applyFix proposes the fix mutation and accepts the resulting proposal", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const fixMutation = { base_version: 0, description: "fix it" };
    useSessionStore.setState({
      reviews: {
        r1: {
          id: "r1",
          author: "ml_engineer",
          findings: [],
          comments: [],
          fix: fixMutation,
          status: "open",
        },
      },
    });
    const proposal: sessionClient.StoredProposal = {
      id: "p1",
      mutation: fixMutation,
      diagnostics: { diagnostics: [], edge_compatibility: {} },
      status: "pending",
    };
    vi.mocked(sessionClient.proposeMutation).mockResolvedValue(proposal);
    vi.mocked(sessionClient.acceptProposal).mockResolvedValue(
      fakeSession({ id: "abc", version: 1 }),
    );

    await useSessionStore.getState().applyFix("r1");

    expect(sessionClient.proposeMutation).toHaveBeenCalledWith(
      "abc",
      fixMutation,
    );
    expect(sessionClient.acceptProposal).toHaveBeenCalledWith("abc", "p1");
  });

  test("applyFix is a no-op when the review has no fix", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();
    useSessionStore.setState({
      reviews: {
        r1: {
          id: "r1",
          author: "ml_engineer",
          findings: [],
          comments: [],
          fix: null,
          status: "open",
        },
      },
    });

    await useSessionStore.getState().applyFix("r1");

    expect(sessionClient.proposeMutation).not.toHaveBeenCalled();
  });
});
