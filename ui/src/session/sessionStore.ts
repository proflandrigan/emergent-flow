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
  createReview,
  createSession,
  getSession,
  proposeMutation,
  rejectProposal,
  replaceSessionGraph,
  subscribeToSessionEvents,
  type CreateReviewInput,
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
  accept: (proposalId: string) => Promise<void>;
  reject: (proposalId: string) => Promise<void>;
  dismissRebase: () => void;
  postReview: (input: CreateReviewInput) => Promise<ReviewThread>;
  postReviewComment: (
    reviewId: string,
    comment: { author: string; text: string },
  ) => Promise<void>;
  applyFix: (reviewId: string) => Promise<void>;
}

// Holds the live SSE/poll subscription outside Zustand state (it is not serializable/comparable
// state -- an external resource tied to the store's lifecycle, closed on leave()/re-join()).
let activeSubscription: SessionEventSubscription | null = null;

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

// Applies an incoming SSE/poll event: always refreshes the proposal list + version from the
// server (cheap correctness over cleverness -- one extra GET per event), and ONLY reloads the
// canvas's graph for the two event types that actually change the accepted graph server-side
// (graph_replaced, proposal_accepted). proposal_added/proposal_rejected update the proposal
// list without touching the canvas, so an in-progress local edit is never stomped by someone
// else's proposal arriving.
async function handleSessionEvent(event: SessionEvent): Promise<void> {
  const state = useSessionStore.getState();
  if (state.sessionId === null || event.session_id !== state.sessionId) {
    return;
  }
  try {
    const session = await getSession(state.sessionId);
    useSessionStore.setState({
      version: session.version,
      proposals: session.proposals,
      reviews: session.collab?.reviews ?? {},
    });
    if (event.type === "graph_replaced" || event.type === "proposal_accepted") {
      useGraphStore.getState().loadIR(session.graph);
    }
  } catch (err) {
    useSessionStore.setState({ error: errorMessage(err) });
  }
}

function subscribe(sessionId: string): void {
  activeSubscription?.close();
  activeSubscription = subscribeToSessionEvents(
    sessionId,
    (event) => void handleSessionEvent(event),
  );
}

function resetConnectionState() {
  activeSubscription?.close();
  activeSubscription = null;
  return {
    sessionId: null,
    version: null,
    proposals: {},
    reviews: {},
    status: "idle" as SessionConnectionStatus,
    error: null,
    rebaseNeeded: false,
    rebaseMessage: null,
  };
}

function applySession(session: GraphSession) {
  return {
    sessionId: session.id,
    version: session.version,
    proposals: session.proposals,
    reviews: session.collab?.reviews ?? {},
    status: "connected" as SessionConnectionStatus,
    error: null,
    rebaseNeeded: false,
    rebaseMessage: null,
  };
}

export const useSessionStore = create<SessionStoreState>((set, get) => ({
  sessionId: null,
  version: null,
  proposals: {},
  reviews: {},
  status: "idle",
  error: null,
  rebaseNeeded: false,
  rebaseMessage: null,

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
    const proposal = await proposeMutation(state.sessionId, mutation);
    set((s) => ({ proposals: { ...s.proposals, [proposal.id]: proposal } }));
    return proposal;
  },

  async accept(proposalId) {
    const state = get();
    if (state.sessionId === null) {
      return;
    }
    const session = await acceptProposal(state.sessionId, proposalId);
    useGraphStore.getState().loadIR(session.graph);
    set({ version: session.version, proposals: session.proposals });
  },

  async reject(proposalId) {
    const state = get();
    if (state.sessionId === null) {
      return;
    }
    const session = await rejectProposal(state.sessionId, proposalId);
    set({ version: session.version, proposals: session.proposals });
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
    const proposal = await get().propose(thread.fix);
    await get().accept(proposal.id);
  },
}));
