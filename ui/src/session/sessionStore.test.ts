import { waitFor } from "@testing-library/react";
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
  consultSession: vi.fn(),
  acceptProposal: vi.fn(),
  rejectProposal: vi.fn(),
  subscribeToSessionEvents: vi.fn(),
  createReview: vi.fn(),
  addReviewComment: vi.fn(),
  createGate: vi.fn(),
  closeGateRequest: vi.fn(),
  skipGateRequest: vi.fn(),
  postGateDecision: vi.fn(),
  startChat: vi.fn(),
  stopChatTurn: vi.fn(),
  endChat: vi.fn(),
  applyDirectMutation: vi.fn(),
  revertCheckpoint: vi.fn(),
  listCheckpoints: vi.fn(),
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
    collab: {
      reviews: {},
      gates: {},
      chat: {
        backend: null,
        backend_thread_id: null,
        active_persona: null,
        turns: [],
      },
      checkpoints: {},
    },
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

describe("consult", () => {
  test("consult stores the returned proposal", async () => {
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
    vi.mocked(sessionClient.consultSession).mockResolvedValue(proposal);

    const result = await useSessionStore
      .getState()
      .consult({ persona: "data_modeller", node_ids: ["n1"], ask: "x" });

    expect(result).toEqual(proposal);
    expect(useSessionStore.getState().proposals.p1).toEqual(proposal);
    expect(sessionClient.consultSession).toHaveBeenCalledWith("abc", {
      persona: "data_modeller",
      node_ids: ["n1"],
      ask: "x",
    });
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

  test("proposal_accepted reloads the graph with reflow enabled", async () => {
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
    expect(loadIRSpy).toHaveBeenCalledWith(
      { paradigm: "functional", nodes: {}, edges: {} },
      { reflow: true },
    );
    expect(useSessionStore.getState().version).toBe(1);
  });

  test("graph_changed event reloads graph and adds agent chat turn", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    vi.mocked(sessionClient.getSession).mockResolvedValue(
      fakeSession({
        id: "abc",
        version: 2,
        graph: { paradigm: "functional", nodes: {}, edges: {} },
        collab: {
          checkpoints: {},
          reviews: {},
          gates: {},
          chat: {
            backend: null,
            backend_thread_id: null,
            active_persona: null,
            turns: [],
          },
        },
      }),
    );
    const loadIRSpy = vi.spyOn(useGraphStore.getState(), "loadIR");

    await capturedOnEvent?.({
      type: "graph_changed",
      session_id: "abc",
      checkpoint_id: "cp-1",
      author: "agent",
      description: "Added a node",
      version: 2,
    });

    expect(loadIRSpy).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().version).toBe(2);
    const turns = useSessionStore.getState().chat.turns;
    expect(turns).toHaveLength(1);
    expect(turns[0].backend).toBe("agent");
    expect(turns[0].agent_message).toBe("Added a node");
    expect(turns[0].status).toBe("completed");
  });

  test("graph_reverted event reloads graph and adds agent chat turn", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    vi.mocked(sessionClient.getSession).mockResolvedValue(
      fakeSession({
        id: "abc",
        version: 1,
        graph: { paradigm: "functional", nodes: {}, edges: {} },
        collab: {
          checkpoints: {},
          reviews: {},
          gates: {},
          chat: {
            backend: null,
            backend_thread_id: null,
            active_persona: null,
            turns: [],
          },
        },
      }),
    );
    const loadIRSpy = vi.spyOn(useGraphStore.getState(), "loadIR");

    await capturedOnEvent?.({
      type: "graph_reverted",
      session_id: "abc",
      reverted_checkpoint_id: "cp-1",
      author: "agent",
      version: 1,
    });

    expect(loadIRSpy).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().version).toBe(1);
    const turns = useSessionStore.getState().chat.turns;
    expect(turns).toHaveLength(1);
    expect(turns[0].backend).toBe("agent");
    // No description on the event -- falls back to the attributed default.
    expect(turns[0].agent_message).toBe("agent applied a graph change.");
  });

  test("graph_changed appends to existing chat turns rather than replacing them", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const existingTurn: sessionClient.ChatTurn = {
      id: "turn-1",
      backend: "claude",
      user_message: "hello",
      narration: [],
      agent_message: "done",
      status: "completed",
      error: null,
    };
    vi.mocked(sessionClient.getSession).mockResolvedValue(
      fakeSession({
        id: "abc",
        version: 2,
        collab: {
          checkpoints: {},
          reviews: {},
          gates: {},
          chat: {
            backend: null,
            backend_thread_id: null,
            active_persona: null,
            turns: [existingTurn],
          },
        },
      }),
    );

    await capturedOnEvent?.({
      type: "graph_changed",
      session_id: "abc",
      checkpoint_id: "cp-1",
      author: "agent",
      description: "Edited a node",
      version: 2,
    });

    const turns = useSessionStore.getState().chat.turns;
    expect(turns).toHaveLength(2);
    expect(turns[0]).toEqual(existingTurn);
    expect(turns[1].agent_message).toBe("Edited a node");
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

  test("a burst of events while a refresh is in flight coalesces into one trailing refresh", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    let resolveFirst: (session: sessionClient.GraphSession) => void = () => {};
    const first = new Promise<sessionClient.GraphSession>((resolve) => {
      resolveFirst = resolve;
    });
    vi.mocked(sessionClient.getSession)
      .mockReturnValueOnce(first)
      .mockResolvedValue(fakeSession({ id: "abc", version: 3 }));

    // Three events arrive back to back, before the first GET resolves. The store's real
    // `subscribe()` wraps the handler as `(event) => void handleSessionEvent(event)`, so
    // `capturedOnEvent` (matching that signature) doesn't hand back a promise to await --
    // the burst is fire-and-forget here exactly as it is for a real SSE subscription.
    capturedOnEvent?.({
      type: "proposal_added",
      session_id: "abc",
      proposal_id: "p1",
    });
    capturedOnEvent?.({
      type: "proposal_added",
      session_id: "abc",
      proposal_id: "p2",
    });
    capturedOnEvent?.({
      type: "proposal_added",
      session_id: "abc",
      proposal_id: "p3",
    });

    resolveFirst(fakeSession({ id: "abc", version: 1 }));
    await waitFor(() => expect(useSessionStore.getState().version).toBe(3));

    // Only two GETs total: one in flight, one trailing for the coalesced p2/p3 burst --
    // not three, one per event.
    expect(sessionClient.getSession).toHaveBeenCalledTimes(2);
  });
});

describe("applyDirectMutation / revertCheckpoint / listCheckpoints", () => {
  test("applyDirectMutation action calls the client and refreshes state", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const mutation = { base_version: 0, description: "agent edit" };
    vi.mocked(sessionClient.applyDirectMutation).mockResolvedValue(
      fakeSession({
        id: "abc",
        version: 1,
        graph: { paradigm: "functional", nodes: {}, edges: {} },
        collab: {
          reviews: {},
          gates: {},
          chat: {
            backend: null,
            backend_thread_id: null,
            active_persona: null,
            turns: [],
          },
          checkpoints: {
            "cp-1": {
              id: "cp-1",
              kind: "edit",
              author: "agent",
              description: "agent edit",
              timestamp: 123,
              base_version: 0,
              resulting_version: 1,
              mutation,
            },
          },
        },
      }),
    );
    const loadIRSpy = vi.spyOn(useGraphStore.getState(), "loadIR");

    await useSessionStore.getState().applyDirectMutation(mutation, "agent");

    expect(sessionClient.applyDirectMutation).toHaveBeenCalledWith(
      "abc",
      mutation,
      "agent",
      undefined,
    );
    expect(loadIRSpy).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().version).toBe(1);
    expect(useSessionStore.getState().checkpoints["cp-1"].kind).toBe("edit");
  });

  test("revertCheckpoint action calls the client and refreshes state", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    vi.mocked(sessionClient.revertCheckpoint).mockResolvedValue(
      fakeSession({
        id: "abc",
        version: 0,
        graph: { paradigm: "functional", nodes: {}, edges: {} },
        collab: {
          reviews: {},
          gates: {},
          chat: {
            backend: null,
            backend_thread_id: null,
            active_persona: null,
            turns: [],
          },
          checkpoints: {
            "cp-1": {
              id: "cp-1",
              kind: "revert",
              author: "agent",
              description: "reverted",
              timestamp: 456,
              base_version: 1,
              resulting_version: 0,
              mutation: { base_version: 1 },
            },
          },
        },
      }),
    );
    const loadIRSpy = vi.spyOn(useGraphStore.getState(), "loadIR");

    await useSessionStore.getState().revertCheckpoint("cp-1");

    expect(sessionClient.revertCheckpoint).toHaveBeenCalledWith("abc", "cp-1");
    expect(loadIRSpy).toHaveBeenCalledTimes(1);
    expect(useSessionStore.getState().version).toBe(0);
    expect(useSessionStore.getState().checkpoints["cp-1"].kind).toBe("revert");
  });

  test("listCheckpoints action calls the client and stores the checkpoints", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const checkpoint: sessionClient.Checkpoint = {
      id: "cp-1",
      kind: "edit",
      author: "agent",
      description: "agent edit",
      timestamp: 123,
      base_version: 0,
      resulting_version: 1,
      mutation: { base_version: 0 },
    };
    vi.mocked(sessionClient.listCheckpoints).mockResolvedValue({
      checkpoints: [checkpoint],
    });

    await useSessionStore.getState().listCheckpoints();

    expect(sessionClient.listCheckpoints).toHaveBeenCalledWith("abc");
    expect(useSessionStore.getState().checkpoints["cp-1"]).toEqual(checkpoint);
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

describe("gates", () => {
  test("openGate stores the returned gate", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const gate: sessionClient.Gate = {
      id: "g1",
      phase: "review",
      kind: "confirm",
      description: "Confirm the analysis",
      status: "open",
      decisions: [],
    };
    vi.mocked(sessionClient.createGate).mockResolvedValue(gate);

    const result = await useSessionStore.getState().openGate({
      phase: "review",
      kind: "confirm",
      description: "Confirm the analysis",
    });

    expect(result).toEqual(gate);
    expect(useSessionStore.getState().gates.g1).toEqual(gate);
    expect(sessionClient.createGate).toHaveBeenCalledWith("abc", {
      phase: "review",
      kind: "confirm",
      description: "Confirm the analysis",
    });
  });

  test("closeGate updates the stored gate's status", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    useSessionStore.setState({
      gates: {
        g1: {
          id: "g1",
          phase: "review",
          kind: "confirm",
          description: "",
          status: "open",
          decisions: [],
        },
      },
    });

    const closed: sessionClient.Gate = {
      id: "g1",
      phase: "review",
      kind: "confirm",
      description: "",
      status: "closed",
      decisions: [],
    };
    vi.mocked(sessionClient.closeGateRequest).mockResolvedValue(closed);

    await useSessionStore.getState().closeGate("g1");

    expect(useSessionStore.getState().gates.g1.status).toBe("closed");
    expect(sessionClient.closeGateRequest).toHaveBeenCalledWith("abc", "g1");
  });

  test("skipGate updates the stored gate's status", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    useSessionStore.setState({
      gates: {
        g1: {
          id: "g1",
          phase: "review",
          kind: "confirm",
          description: "",
          status: "open",
          decisions: [],
        },
      },
    });

    const skipped: sessionClient.Gate = {
      id: "g1",
      phase: "review",
      kind: "confirm",
      description: "",
      status: "skipped",
      decisions: [],
    };
    vi.mocked(sessionClient.skipGateRequest).mockResolvedValue(skipped);

    await useSessionStore.getState().skipGate("g1");

    expect(useSessionStore.getState().gates.g1.status).toBe("skipped");
    expect(sessionClient.skipGateRequest).toHaveBeenCalledWith("abc", "g1");
  });

  test("addGateDecision updates the stored gate's decisions", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    useSessionStore.setState({
      gates: {
        g1: {
          id: "g1",
          phase: "review",
          kind: "confirm",
          description: "",
          status: "open",
          decisions: [],
        },
      },
    });

    const updated: sessionClient.Gate = {
      id: "g1",
      phase: "review",
      kind: "confirm",
      description: "",
      status: "open",
      decisions: [{ id: "d1", author: "human", text: "proceed" }],
    };
    vi.mocked(sessionClient.postGateDecision).mockResolvedValue(updated);

    await useSessionStore
      .getState()
      .addGateDecision("g1", { author: "human", text: "proceed" });

    expect(useSessionStore.getState().gates.g1.decisions).toHaveLength(1);
    expect(useSessionStore.getState().gates.g1.decisions[0].text).toBe(
      "proceed",
    );
    expect(sessionClient.postGateDecision).toHaveBeenCalledWith("abc", "g1", {
      author: "human",
      text: "proceed",
    });
  });
});

describe("chat", () => {
  test("startChat posts to the session and stores the returned turn", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const turn: sessionClient.ChatTurn = {
      id: "turn-1",
      backend: "claude",
      user_message: "hello",
      narration: [],
      agent_message: null,
      status: "running",
      error: null,
    };
    vi.mocked(sessionClient.startChat).mockResolvedValue(turn);

    const result = await useSessionStore.getState().startChat("claude", "hello");

    expect(sessionClient.startChat).toHaveBeenCalledWith("abc", {
      backend: "claude",
      message: "hello",
    });
    expect(result).toEqual(turn);
    const state = useSessionStore.getState();
    expect(state.chat.backend).toBe("claude");
    expect(state.chat.turns).toEqual([turn]);
  });

  test("startChat throws when there is no active session", async () => {
    await expect(
      useSessionStore.getState().startChat("claude", "hello"),
    ).rejects.toThrow("no active session");
  });

  test("startChat sets error state and rethrows on failure", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();
    vi.mocked(sessionClient.startChat).mockRejectedValue(new Error("boom"));

    await expect(
      useSessionStore.getState().startChat("claude", "hello"),
    ).rejects.toThrow("boom");
    expect(useSessionStore.getState().error).toBe("boom");
  });

  test("stopChat replaces the matching turn with the resolved one", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();
    const runningTurn: sessionClient.ChatTurn = {
      id: "turn-1",
      backend: "claude",
      user_message: "hello",
      narration: [],
      agent_message: null,
      status: "running",
      error: null,
    };
    vi.mocked(sessionClient.startChat).mockResolvedValue(runningTurn);
    await useSessionStore.getState().startChat("claude", "hello");

    const interruptedTurn: sessionClient.ChatTurn = {
      ...runningTurn,
      status: "interrupted",
    };
    vi.mocked(sessionClient.stopChatTurn).mockResolvedValue(interruptedTurn);

    await useSessionStore.getState().stopChat("turn-1");

    expect(sessionClient.stopChatTurn).toHaveBeenCalledWith("abc", "turn-1");
    expect(useSessionStore.getState().chat.turns).toEqual([interruptedTurn]);
  });

  test("endChat clears the chat backend from the returned session", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();
    vi.mocked(sessionClient.startChat).mockResolvedValue({
      id: "turn-1",
      backend: "claude",
      user_message: "hello",
      narration: [],
      agent_message: "done",
      status: "completed",
      error: null,
    });
    await useSessionStore.getState().startChat("claude", "hello");

    vi.mocked(sessionClient.endChat).mockResolvedValue(
      fakeSession({
        id: "abc",
        version: 0,
        collab: {
          reviews: {},
          gates: {},
          chat: {
            backend: null,
            backend_thread_id: null,
            active_persona: null,
            turns: [],
          },
        },
      }),
    );

    await useSessionStore.getState().endChat();

    expect(sessionClient.endChat).toHaveBeenCalledWith("abc");
    expect(useSessionStore.getState().chat.backend).toBeNull();
    expect(useSessionStore.getState().chat.turns).toEqual([]);
  });

  test("a chat_narration_added SSE event refreshes the chat state from the server", async () => {
    vi.mocked(sessionClient.createSession).mockResolvedValue(
      fakeSession({ id: "abc", version: 0 }),
    );
    await useSessionStore.getState().createAndJoin();

    const turn: sessionClient.ChatTurn = {
      id: "turn-1",
      backend: "claude",
      user_message: "hello",
      narration: ["running curl"],
      agent_message: null,
      status: "running",
      error: null,
    };
    vi.mocked(sessionClient.getSession).mockResolvedValue(
      fakeSession({
        id: "abc",
        version: 0,
        collab: {
          reviews: {},
          gates: {},
          chat: {
            backend: "claude",
            backend_thread_id: null,
            active_persona: null,
            turns: [turn],
          },
        },
      }),
    );

    await capturedOnEvent?.({
      type: "chat_narration_added",
      session_id: "abc",
      turn_id: "turn-1",
    });

    expect(useSessionStore.getState().chat.turns).toEqual([turn]);
  });
});
