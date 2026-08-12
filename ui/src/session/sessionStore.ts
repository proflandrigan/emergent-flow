// Session connection store (Epic 14 Story 4) -- Zustand store owning graph-session connection
// state (id, version, pending proposals, connection status, optimistic-concurrency conflicts).
// This store WRAPS ui/src/store/graphStore.ts: it never holds its own copy of node/edge state,
// it drives useGraphStore's toIR()/loadIR() to move the canvas's graph in and out of sync with
// the server-side GraphSession. Session mode is strictly opt-in -- nothing in this module runs
// unless a caller invokes createAndJoin/join.

import { create } from "zustand";

import { useGraphStore } from "../store/graphStore";
import type { Graph } from "../generated/ir";
import type { GraphMutation } from "../generated/mutation";
import type { SessionEvent } from "../generated/session_event";
import {
  acceptProposal,
  addReviewComment,
  applyDirectMutation,
  closeGateRequest,
  compileSession,
  consultSession,
  createGate,
  createReview,
  createSession,
  endChat as endChatRequest,
  executeSession,
  getSession,
  listCheckpoints,
  postGateDecision,
  proposeMutation,
  rejectProposal,
  replaceSessionGraph,
  revertCheckpoint,
  skipGateRequest,
  startChat as startChatRequest,
  stopChatTurn as stopChatTurnRequest,
  subscribeToSessionEvents,
  type Attempt,
  type ChatState,
  type ChatTurn,
  type Checkpoint,
  type ConsultInput,
  type CreateGateInput,
  type CreateReviewInput,
  type ExecuteSessionResult,
  type ExecuteSessionScope,
  type Gate,
  type GraphSession,
  type ReviewThread,
  type SessionEventSubscription,
  type StoredProposal,
} from "./sessionClient";

export type SessionConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "error";

export interface SessionStoreState {
  sessionId: string | null;
  version: number | null;
  proposals: Record<string, StoredProposal>;
  reviews: Record<string, ReviewThread>;
  gates: Record<string, Gate>;
  chat: ChatState;
  attempts: Record<string, Attempt>;
  checkpoints: Record<string, Checkpoint>;
  status: SessionConnectionStatus;
  error: string | null;
  // Set when a PUT .../graph call is rejected for a stale expected_version (someone else's
  // change landed first). The canvas surfaces this as a "rebase" banner (a later task) rather
  // than silently overwriting the server's graph or discarding the local edit.
  rebaseNeeded: boolean;
  rebaseMessage: string | null;

  createAndJoin: (graph?: Graph) => Promise<void>;
  join: (sessionId: string) => Promise<void>;
  leave: () => void;
  pushLocalGraph: () => Promise<void>;
  propose: (mutation: GraphMutation) => Promise<StoredProposal>;
  consult: (input: ConsultInput) => Promise<StoredProposal>;
  accept: (proposalId: string) => Promise<void>;
  reject: (proposalId: string) => Promise<void>;
  dismissRebase: () => void;
  postReview: (input: CreateReviewInput) => Promise<ReviewThread>;
  postReviewComment: (
    reviewId: string,
    comment: { author: string; text: string },
  ) => Promise<void>;
  applyFix: (reviewId: string) => Promise<void>;
  openGate: (input: CreateGateInput) => Promise<Gate>;
  closeGate: (gateId: string) => Promise<void>;
  skipGate: (gateId: string) => Promise<void>;
  addGateDecision: (
    gateId: string,
    decision: { author: string; text: string },
  ) => Promise<void>;
  startChat: (backend: string, message: string) => Promise<ChatTurn>;
  stopChat: (turnId: string) => Promise<void>;
  endChat: () => Promise<void>;
  applyDirectMutation: (
    mutation: GraphMutation,
    author?: string,
    reason?: string,
  ) => Promise<void>;
  revertCheckpoint: (checkpointId: string) => Promise<void>;
  listCheckpoints: () => Promise<void>;
  compileSession: () => Promise<{ code: string }>;
  executeSession: (scope?: ExecuteSessionScope) => Promise<ExecuteSessionResult>;
}

// Holds the live SSE/poll subscription outside Zustand state (it is not serializable/comparable
// state -- an external resource tied to the store's lifecycle, closed on leave()/re-join()).
let activeSubscription: SessionEventSubscription | null = null;

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

// Refreshes the proposal list + version from the server (cheap correctness over cleverness --
// one GET), and ONLY reloads the canvas's graph for the event types that actually change
// the accepted graph server-side (graph_replaced, proposal_accepted, graph_changed,
// graph_reverted). proposal_added/proposal_rejected update the proposal list without touching
// the canvas, so an in-progress local edit is never stomped by someone else's proposal arriving.
// The six chat_* event types (chat_turn_started, chat_narration_added, chat_turn_completed,
// chat_turn_failed, chat_turn_interrupted, chat_ended) need no special case here -- they flow
// through this same full refetch, which is how live narration/replies actually reach the UI as
// a spawned chat backend streams output in the background.
async function refreshFromServer(
  sessionId: string,
  event: SessionEvent,
): Promise<void> {
  try {
    const session = await getSession(sessionId);
    const chat =
      event.type === "graph_changed" || event.type === "graph_reverted"
        ? appendAgentTurn(session.collab?.chat ?? idleChatState, event)
        : session.collab?.chat ?? idleChatState;
    useSessionStore.setState({
      version: session.version,
      proposals: session.proposals,
      reviews: session.collab?.reviews ?? {},
      gates: session.collab?.gates ?? {},
      chat,
      attempts: session.collab?.attempts ?? {},
      checkpoints: session.collab?.checkpoints ?? {},
    });
    if (
      event.type === "graph_replaced" ||
      event.type === "proposal_accepted" ||
      event.type === "graph_changed" ||
      event.type === "graph_reverted"
    ) {
      useGraphStore.getState().loadIR(session.graph);
    }
  } catch (err) {
    useSessionStore.setState({ error: errorMessage(err) });
  }
}

// Surfaces a live agent edit (graph_changed / graph_reverted) as an attributed message in the
// session chat panel. The turn is synthetic -- the server does not emit a chat turn for a direct
// mutation -- so it is appended to the freshly-fetched session's chat state, never to local state.
function appendAgentTurn(chat: ChatState, event: SessionEvent): ChatState {
  const turn: ChatTurn = {
    id: `agent-${event.checkpoint_id ?? Date.now()}`,
    backend: "agent",
    user_message: "",
    narration: [],
    agent_message:
      event.description || `${event.author ?? "agent"} applied a graph change.`,
    status: "completed",
    error: null,
  };
  return { ...chat, turns: [...chat.turns, turn] };
}

// Single-flight + trailing coalescing: a burst of SSE/poll events arriving faster than the
// server round-trip (e.g. an agent posting several proposals/review comments back to back)
// would otherwise fire one full-session GET per event, racing each other for which response's
// setState lands last. Instead, an event that arrives while a refresh is already in flight is
// queued (only the LATEST one, since each refresh re-fetches the full session state) and
// triggers exactly one trailing refresh once the in-flight one completes.
let inFlightRefresh: Promise<void> | null = null;
let queuedEvent: SessionEvent | null = null;

async function handleSessionEvent(event: SessionEvent): Promise<void> {
  const state = useSessionStore.getState();
  if (state.sessionId === null || event.session_id !== state.sessionId) {
    return;
  }
  if (inFlightRefresh) {
    queuedEvent = event;
    await inFlightRefresh;
    return;
  }
  const sessionId = state.sessionId;
  inFlightRefresh = refreshFromServer(sessionId, event);
  await inFlightRefresh;
  inFlightRefresh = null;
  const next = queuedEvent;
  queuedEvent = null;
  if (next) {
    await handleSessionEvent(next);
  }
}

function subscribe(sessionId: string): void {
  activeSubscription?.close();
  activeSubscription = subscribeToSessionEvents(
    sessionId,
    (event) => void handleSessionEvent(event),
  );
}

// The connection-state fields (as opposed to the action methods) of SessionStoreState --
// shared by the store's initial state, resetConnectionState(), and applySession() so a new
// field only needs to be listed once instead of independently in all three.
type ConnectionState = Omit<
  SessionStoreState,
  | "createAndJoin"
  | "join"
  | "leave"
  | "pushLocalGraph"
  | "propose"
  | "consult"
  | "accept"
  | "reject"
  | "dismissRebase"
  | "postReview"
  | "postReviewComment"
  | "applyFix"
  | "openGate"
  | "closeGate"
  | "skipGate"
  | "addGateDecision"
  | "startChat"
  | "stopChat"
  | "endChat"
  | "applyDirectMutation"
  | "revertCheckpoint"
  | "listCheckpoints"
  | "compileSession"
  | "executeSession"
>;

const idleChatState: ChatState = {
  backend: null,
  backend_thread_id: null,
  turns: [],
  active_persona: null,
};

const idleConnectionState: ConnectionState = {
  sessionId: null,
  version: null,
  proposals: {},
  reviews: {},
  gates: {},
  chat: idleChatState,
  attempts: {},
  checkpoints: {},
  status: "idle",
  error: null,
  rebaseNeeded: false,
  rebaseMessage: null,
};

function resetConnectionState(): ConnectionState {
  activeSubscription?.close();
  activeSubscription = null;
  return idleConnectionState;
}

function applySession(session: GraphSession): ConnectionState {
  return {
    ...idleConnectionState,
    sessionId: session.id,
    version: session.version,
    proposals: session.proposals,
    reviews: session.collab?.reviews ?? {},
    gates: session.collab?.gates ?? {},
    chat: session.collab?.chat ?? idleChatState,
    attempts: session.collab?.attempts ?? {},
    checkpoints: session.collab?.checkpoints ?? {},
    status: "connected",
  };
}

export const useSessionStore = create<SessionStoreState>((set, get) => ({
  ...idleConnectionState,

  async createAndJoin(graph) {
    set({ status: "connecting", error: null });
    try {
      const initialGraph = graph ?? useGraphStore.getState().toIR();
      const session = await createSession(initialGraph);
      useGraphStore.getState().loadIR(session.graph);
      subscribe(session.id);
      set(applySession(session));
    } catch (err) {
      set({ status: "error", error: errorMessage(err) });
    }
  },

  async join(sessionId) {
    set({ status: "connecting", error: null });
    try {
      const session = await getSession(sessionId);
      useGraphStore.getState().loadIR(session.graph);
      subscribe(session.id);
      set(applySession(session));
    } catch (err) {
      set({ status: "error", error: errorMessage(err) });
    }
  },

  leave() {
    set(resetConnectionState());
  },

  async pushLocalGraph() {
    const state = get();
    if (state.sessionId === null || state.version === null) {
      return;
    }
    try {
      const graph = useGraphStore.getState().toIR();
      const session = await replaceSessionGraph(
        state.sessionId,
        graph,
        state.version,
      );
      set({
        version: session.version,
        proposals: session.proposals,
        rebaseNeeded: false,
        rebaseMessage: null,
      });
    } catch (err) {
      const message = errorMessage(err);
      if (message.startsWith("stale_version")) {
        set({ rebaseNeeded: true, rebaseMessage: message });
      } else {
        set({ error: message });
      }
    }
  },

  async propose(mutation) {
    const state = get();
    if (state.sessionId === null) {
      throw new Error("cannot propose a mutation: no active session");
    }
    try {
      const proposal = await proposeMutation(state.sessionId, mutation);
      set((s) => ({ proposals: { ...s.proposals, [proposal.id]: proposal } }));
      return proposal;
    } catch (err) {
      const message = errorMessage(err);
      if (message.startsWith("stale_version")) {
        set({ rebaseNeeded: true, rebaseMessage: message });
      } else {
        set({ error: message });
      }
      throw err;
    }
  },

  async consult(input) {
    const state = get();
    if (state.sessionId === null) {
      throw new Error("cannot consult: no active session");
    }
    try {
      const proposal = await consultSession(state.sessionId, input);
      set((s) => ({ proposals: { ...s.proposals, [proposal.id]: proposal } }));
      return proposal;
    } catch (err) {
      const message = errorMessage(err);
      set({ error: message });
      throw err;
    }
  },

  async accept(proposalId) {
    const state = get();
    if (state.sessionId === null) {
      return;
    }
    try {
      const session = await acceptProposal(state.sessionId, proposalId);
      useGraphStore.getState().loadIR(session.graph);
      set({ version: session.version, proposals: session.proposals });
    } catch (err) {
      const message = errorMessage(err);
      if (message.startsWith("stale_version")) {
        set({ rebaseNeeded: true, rebaseMessage: message });
      } else {
        set({ error: message });
      }
    }
  },

  async reject(proposalId) {
    const state = get();
    if (state.sessionId === null) {
      return;
    }
    try {
      const session = await rejectProposal(state.sessionId, proposalId);
      set({ version: session.version, proposals: session.proposals });
    } catch (err) {
      set({ error: errorMessage(err) });
    }
  },

  dismissRebase() {
    set({ rebaseNeeded: false, rebaseMessage: null });
  },

  async postReview(input) {
    const state = get();
    if (state.sessionId === null) {
      throw new Error("cannot post a review: no active session");
    }
    const thread = await createReview(state.sessionId, input);
    set((s) => ({ reviews: { ...s.reviews, [thread.id]: thread } }));
    return thread;
  },

  async postReviewComment(reviewId, comment) {
    const state = get();
    if (state.sessionId === null) {
      return;
    }
    const thread = await addReviewComment(state.sessionId, reviewId, comment);
    set((s) => ({ reviews: { ...s.reviews, [reviewId]: thread } }));
  },

  // "Apply fix" is an ORDINARY proposal accept (Story 4 machinery) -- zero new apply code,
  // just chaining the two existing actions below.
  async applyFix(reviewId) {
    const thread = get().reviews[reviewId];
    if (!thread || !thread.fix) {
      return;
    }
    try {
      const proposal = await get().propose(thread.fix);
      await get().accept(proposal.id);
    } catch {
      // propose() already recorded the failure in `error`/`rebaseNeeded` state;
      // swallow here so a rejected fix doesn't surface as an unhandled rejection.
    }
  },

  async openGate(input) {
    const state = get();
    if (state.sessionId === null) {
      throw new Error("cannot open a gate: no active session");
    }
    const gate = await createGate(state.sessionId, input);
    set((s) => ({ gates: { ...s.gates, [gate.id]: gate } }));
    return gate;
  },

  async closeGate(gateId) {
    const state = get();
    if (state.sessionId === null) return;
    try {
      const gate = await closeGateRequest(state.sessionId, gateId);
      set((s) => ({ gates: { ...s.gates, [gateId]: gate } }));
    } catch (err) {
      set({ error: errorMessage(err) });
    }
  },

  async skipGate(gateId) {
    const state = get();
    if (state.sessionId === null) return;
    try {
      const gate = await skipGateRequest(state.sessionId, gateId);
      set((s) => ({ gates: { ...s.gates, [gateId]: gate } }));
    } catch (err) {
      set({ error: errorMessage(err) });
    }
  },

  async addGateDecision(gateId, decision) {
    const state = get();
    if (state.sessionId === null) return;
    const gate = await postGateDecision(state.sessionId, gateId, decision);
    set((s) => ({ gates: { ...s.gates, [gateId]: gate } }));
  },

  async startChat(backend, message) {
    const state = get();
    if (state.sessionId === null) {
      throw new Error("cannot start chat: no active session");
    }
    try {
      const turn = await startChatRequest(state.sessionId, { backend, message });
      set((s) => ({
        chat: {
          ...s.chat,
          backend: s.chat.backend ?? backend,
          turns: [...s.chat.turns, turn],
        },
      }));
      return turn;
    } catch (err) {
      set({ error: errorMessage(err) });
      throw err;
    }
  },

  async stopChat(turnId) {
    const state = get();
    if (state.sessionId === null) return;
    try {
      const turn = await stopChatTurnRequest(state.sessionId, turnId);
      set((s) => ({
        chat: {
          ...s.chat,
          turns: s.chat.turns.map((t) => (t.id === turn.id ? turn : t)),
        },
      }));
    } catch (err) {
      set({ error: errorMessage(err) });
    }
  },

  async endChat() {
    const state = get();
    if (state.sessionId === null) return;
    try {
      const session = await endChatRequest(state.sessionId);
      set({
        version: session.version,
        proposals: session.proposals,
        reviews: session.collab?.reviews ?? {},
        gates: session.collab?.gates ?? {},
        chat: session.collab?.chat ?? idleChatState,
      });
    } catch (err) {
      set({ error: errorMessage(err) });
    }
  },

  async applyDirectMutation(mutation, author, reason) {
    const state = get();
    if (state.sessionId === null) {
      throw new Error("cannot apply a mutation: no active session");
    }
    try {
      const session = await applyDirectMutation(
        state.sessionId,
        mutation,
        author,
        reason,
      );
      useGraphStore.getState().loadIR(session.graph);
      set(applySession(session));
    } catch (err) {
      const message = errorMessage(err);
      if (message.startsWith("stale_version")) {
        set({ rebaseNeeded: true, rebaseMessage: message });
      } else {
        set({ error: message });
      }
    }
  },

  async revertCheckpoint(checkpointId) {
    const state = get();
    if (state.sessionId === null) {
      throw new Error("cannot revert a checkpoint: no active session");
    }
    try {
      const session = await revertCheckpoint(state.sessionId, checkpointId);
      useGraphStore.getState().loadIR(session.graph);
      set(applySession(session));
    } catch (err) {
      set({ error: errorMessage(err) });
    }
  },

  async listCheckpoints() {
    const state = get();
    if (state.sessionId === null) {
      throw new Error("cannot list checkpoints: no active session");
    }
    try {
      const { checkpoints } = await listCheckpoints(state.sessionId);
      set({
        checkpoints: Object.fromEntries(
          checkpoints.map((c) => [c.id, c]),
        ),
      });
    } catch (err) {
      set({ error: errorMessage(err) });
    }
  },

  async compileSession() {
    const state = get();
    if (state.sessionId === null) {
      throw new Error("cannot compile: no active session");
    }
    try {
      return await compileSession(state.sessionId);
    } catch (err) {
      set({ error: errorMessage(err) });
      throw err;
    }
  },

  async executeSession(scope) {
    const state = get();
    if (state.sessionId === null) {
      throw new Error("cannot execute: no active session");
    }
    try {
      return await executeSession(state.sessionId, scope);
    } catch (err) {
      set({ error: errorMessage(err) });
      throw err;
    }
  },
}));
