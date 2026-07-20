import { afterEach, describe, expect, test, vi } from "vitest";

import {
  acceptProposal,
  createReview,
  addReviewComment,
  createSession,
  deleteSession,
  endChat,
  getAvailableAgents,
  getSession,
  proposeMutation,
  rejectProposal,
  replaceSessionGraph,
  startChat,
  stopChatTurn,
  subscribeToSessionEvents,
  type ChatTurn,
  type GraphSession,
} from "./sessionClient";

afterEach(() => {
  vi.restoreAllMocks();
});

function fakeSession(overrides: Partial<GraphSession> = {}): GraphSession {
  return {
    id: "sess-1",
    graph: { paradigm: "functional", nodes: {}, edges: {} },
    version: 0,
    proposals: {},
    ...overrides,
  };
}

describe("createSession", () => {
  test("POSTs to /sessions and returns the parsed session", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify(fakeSession()), { status: 200 }),
      );

    const session = await createSession();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, opts] = fetchSpy.mock.calls[0];
    expect(url).toBe("/sessions");
    expect((opts as RequestInit).method).toBe("POST");
    expect(session.id).toBe("sess-1");
  });

  test("includes the graph in the body when provided", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify(fakeSession()), { status: 200 }),
      );

    await createSession({ paradigm: "functional", nodes: {}, edges: {} });

    const [, opts] = fetchSpy.mock.calls[0];
    const body = JSON.parse((opts as RequestInit).body as string);
    expect(body.graph).toBeDefined();
  });
});

describe("getSession", () => {
  test("GETs /sessions/{id}", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fakeSession({ id: "abc" })), {
        status: 200,
      }),
    );

    const session = await getSession("abc");

    expect(fetchSpy).toHaveBeenCalledWith(
      "/sessions/abc",
      expect.objectContaining({ method: "GET" }),
    );
    expect(session.id).toBe("abc");
  });

  test("throws with the server's error message on a non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "no session with id 'abc'." }), {
        status: 404,
      }),
    );

    await expect(getSession("abc")).rejects.toThrow(
      "no session with id 'abc'.",
    );
  });
});

describe("deleteSession", () => {
  test("DELETEs /sessions/{id}", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
      );

    await deleteSession("abc");

    expect(fetchSpy).toHaveBeenCalledWith(
      "/sessions/abc",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});

describe("replaceSessionGraph", () => {
  test("PUTs the graph and expected_version", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fakeSession({ version: 1 })), {
        status: 200,
      }),
    );

    const graph = { paradigm: "functional" as const, nodes: {}, edges: {} };
    const session = await replaceSessionGraph("abc", graph, 0);

    const [url, opts] = fetchSpy.mock.calls[0];
    expect(url).toBe("/sessions/abc/graph");
    expect((opts as RequestInit).method).toBe("PUT");
    const body = JSON.parse((opts as RequestInit).body as string);
    expect(body.expected_version).toBe(0);
    expect(session.version).toBe(1);
  });

  test("throws stale_version on a 409", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "stale_version: ..." }), {
        status: 409,
      }),
    );

    await expect(
      replaceSessionGraph(
        "abc",
        { paradigm: "functional", nodes: {}, edges: {} },
        5,
      ),
    ).rejects.toThrow("stale_version");
  });
});

describe("proposeMutation / acceptProposal / rejectProposal", () => {
  test("proposeMutation POSTs the mutation directly (no envelope) to /sessions/{id}/proposals", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "p1",
          mutation: { base_version: 0 },
          diagnostics: { diagnostics: [], edge_compatibility: {} },
          status: "pending",
        }),
        { status: 200 },
      ),
    );

    const proposal = await proposeMutation("abc", { base_version: 0 });

    const [url, opts] = fetchSpy.mock.calls[0];
    expect(url).toBe("/sessions/abc/proposals");
    const body = JSON.parse((opts as RequestInit).body as string);
    expect(body).toEqual({ base_version: 0 });
    expect(proposal.status).toBe("pending");
  });

  test("acceptProposal POSTs to the accept route", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify(fakeSession()), { status: 200 }),
      );

    await acceptProposal("abc", "p1");

    expect(fetchSpy).toHaveBeenCalledWith(
      "/sessions/abc/proposals/p1/accept",
      expect.objectContaining({ method: "POST" }),
    );
  });

  test("rejectProposal POSTs to the reject route", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify(fakeSession()), { status: 200 }),
      );

    await rejectProposal("abc", "p1");

    expect(fetchSpy).toHaveBeenCalledWith(
      "/sessions/abc/proposals/p1/reject",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("subscribeToSessionEvents", () => {
  test("uses EventSource when available and forwards parsed events", () => {
    const listeners: {
      onmessage?: (ev: MessageEvent<string>) => void;
      close: () => void;
    } = {
      close: vi.fn(),
    };
    class FakeEventSource {
      constructor(public url: string) {
        listeners.onmessage = undefined;
      }
      set onmessage(fn: (ev: MessageEvent<string>) => void) {
        listeners.onmessage = fn;
      }
      close = listeners.close;
    }
    vi.stubGlobal("EventSource", FakeEventSource);

    const received: unknown[] = [];
    const sub = subscribeToSessionEvents("abc", (event) =>
      received.push(event),
    );

    listeners.onmessage?.({
      data: JSON.stringify({
        type: "proposal_added",
        session_id: "abc",
        proposal_id: "p1",
      }),
    } as MessageEvent<string>);

    expect(received).toEqual([
      { type: "proposal_added", session_id: "abc", proposal_id: "p1" },
    ]);

    sub.close();
    expect(listeners.close).toHaveBeenCalledTimes(1);

    vi.unstubAllGlobals();
  });

  test("falls back to polling when EventSource is unavailable", async () => {
    vi.stubGlobal("EventSource", undefined);
    vi.useFakeTimers();

    let call = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      call += 1;
      return new Response(JSON.stringify(fakeSession({ version: call })), {
        status: 200,
      });
    });

    const received: unknown[] = [];
    const sub = subscribeToSessionEvents(
      "abc",
      (event) => received.push(event),
      {
        pollIntervalMs: 100,
      },
    );

    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(100);
    await vi.advanceTimersByTimeAsync(100);

    expect(received.length).toBeGreaterThan(0);
    expect(received[0]).toMatchObject({
      type: "graph_replaced",
      session_id: "abc",
    });

    sub.close();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  test("polling fallback detects a chat update even when version doesn't change", async () => {
    // Regression test: chat turns never bump `session.version` (only the two graph-mutation
    // paths in collab/session.py do), so the polling fallback used to synthesize an event only
    // on a version change -- a chat turn that starts and completes while polling never reached
    // the UI, leaving it stuck on "working..." indefinitely.
    vi.stubGlobal("EventSource", undefined);
    vi.useFakeTimers();

    const runningTurn: ChatTurn = {
      id: "turn-1",
      backend: "claude",
      user_message: "hi",
      narration: [],
      agent_message: null,
      status: "running",
      error: null,
    };
    const completedTurn: ChatTurn = {
      ...runningTurn,
      status: "completed",
      agent_message: "hello!",
    };

    let call = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      call += 1;
      const turn = call === 1 ? runningTurn : completedTurn;
      return new Response(
        JSON.stringify(
          fakeSession({
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
        ),
        { status: 200 },
      );
    });

    const received: unknown[] = [];
    const sub = subscribeToSessionEvents(
      "abc",
      (event) => received.push(event),
      { pollIntervalMs: 100 },
    );

    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(100);
    await vi.advanceTimersByTimeAsync(100);

    expect(received.length).toBeGreaterThan(0);
    expect(received[0]).toMatchObject({ session_id: "abc" });

    sub.close();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
});

describe("createReview", () => {
  test("POSTs the review input to /sessions/{id}/reviews", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "r1",
          author: "ml_engineer",
          findings: [],
          comments: [],
          fix: null,
          status: "open",
        }),
        { status: 200 },
      ),
    );

    const thread = await createReview("abc", { author: "ml_engineer" });

    const [url] = fetchSpy.mock.calls[0];
    expect(url).toBe("/sessions/abc/reviews");
    expect(thread.status).toBe("open");
  });
});

describe("addReviewComment", () => {
  test("POSTs to /sessions/{id}/reviews/{reviewId}/comments", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "r1",
          author: "ml_engineer",
          findings: [],
          comments: [{ id: "c1", author: "human", text: "thanks" }],
          fix: null,
          status: "open",
        }),
        { status: 200 },
      ),
    );

    const thread = await addReviewComment("abc", "r1", {
      author: "human",
      text: "thanks",
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      "/sessions/abc/reviews/r1/comments",
      expect.objectContaining({ method: "POST" }),
    );
    expect(thread.comments).toHaveLength(1);
  });
});

describe("startChat", () => {
  test("POSTs backend/message to /sessions/{id}/chat", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "turn-1",
          backend: "claude",
          user_message: "hi",
          narration: [],
          agent_message: null,
          status: "running",
          error: null,
        }),
        { status: 200 },
      ),
    );

    const turn = await startChat("abc", { backend: "claude", message: "hi" });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, opts] = fetchSpy.mock.calls[0];
    expect(url).toBe("/sessions/abc/chat");
    expect((opts as RequestInit).method).toBe("POST");
    const body = JSON.parse((opts as RequestInit).body as string);
    expect(body).toEqual({ backend: "claude", message: "hi" });
    expect(turn.id).toBe("turn-1");
    expect(turn.status).toBe("running");
  });

  test("throws with the server's error message on a non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "chat_already_active: already running" }), {
        status: 409,
      }),
    );

    await expect(
      startChat("abc", { backend: "claude", message: "hi" }),
    ).rejects.toThrow("chat_already_active");
  });
});

describe("stopChatTurn", () => {
  test("POSTs to /sessions/{id}/chat/{turnId}/stop", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "turn-1",
          backend: "claude",
          user_message: "hi",
          narration: [],
          agent_message: null,
          status: "interrupted",
          error: null,
        }),
        { status: 200 },
      ),
    );

    const turn = await stopChatTurn("abc", "turn-1");

    expect(fetchSpy).toHaveBeenCalledWith(
      "/sessions/abc/chat/turn-1/stop",
      expect.objectContaining({ method: "POST" }),
    );
    expect(turn.status).toBe("interrupted");
  });
});

describe("endChat", () => {
  test("POSTs to /sessions/{id}/chat/end and returns the session", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify(fakeSession()), { status: 200 }),
      );

    const session = await endChat("abc");

    expect(fetchSpy).toHaveBeenCalledWith(
      "/sessions/abc/chat/end",
      expect.objectContaining({ method: "POST" }),
    );
    expect(session.id).toBe("sess-1");
  });
});

describe("getAvailableAgents", () => {
  test("GETs /agents and returns the agent list", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ agents: ["claude", "opencode"] }), {
        status: 200,
      }),
    );

    const agents = await getAvailableAgents();

    expect(fetchSpy).toHaveBeenCalledWith(
      "/agents",
      expect.objectContaining({ method: "GET" }),
    );
    expect(agents).toEqual(["claude", "opencode"]);
  });
});
