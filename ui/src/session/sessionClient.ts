// Session HTTP client (Epic 14 Story 4) -- typed fetch wrappers over the graph-session routes
// on emergentflow/server/app.py (POST/GET/DELETE /sessions, PUT .../graph, propose/accept/reject,
// and the /events SSE stream). Pure I/O boundary: no React, no Zustand -- ui/src/session/sessionStore.ts
// (a later task) is the only caller. Uses the same relative-path + `{"error": ...}`-on-failure
// convention as ui/src/promptlab/httpJson.ts's postJson.

import { postJson } from "../promptlab/httpJson";
import type { Graph } from "../generated/ir";
import type { GraphMutation } from "../generated/mutation";
import type { SessionEvent } from "../generated/session_event";
import { validateSessionEvent } from "../store/validateMutation";
import type { Diagnostic, Diagnostics } from "../store/validation";

export type ProposalStatus = "pending" | "accepted" | "rejected";

export interface StoredProposal {
  id: string;
  mutation: GraphMutation;
  diagnostics: Diagnostics;
  status: ProposalStatus;
}

export interface ReviewComment {
  id: string;
  author: string;
  text: string;
}

export type ReviewStatus = "open" | "resolved";

export interface ReviewThread {
  id: string;
  author: string;
  findings: Diagnostic[];
  comments: ReviewComment[];
  fix: GraphMutation | null;
  status: ReviewStatus;
}

export type GateKind = "phase" | "confirm" | "handoff" | "execute" | "final";
export type GateStatus = "open" | "closed" | "skipped";

export interface Decision {
  id: string;
  author: string;
  text: string;
}

export interface Gate {
  id: string;
  phase: string;
  kind: GateKind;
  description: string;
  status: GateStatus;
  decisions: Decision[];
}

export type AttemptVerdict = "kept" | "reverted" | "pending";

export interface Attempt {
  id: string;
  mutation_id: string;
  run_id: string | null;
  metric_name: string | null;
  metric_value: number | null;
  verdict: AttemptVerdict;
  hypothesis: string;
  author: string;
  timestamp: number;
}

export interface CreateGateInput {
  phase: string;
  kind: GateKind;
  description: string;
}

export interface CreateReviewInput {
  author: string;
  findings?: Diagnostic[];
  fix?: GraphMutation | null;
}

export type ChatTurnStatus = "running" | "completed" | "failed" | "interrupted";

export interface ChatTurn {
  id: string;
  backend: string;
  user_message: string;
  narration: string[];
  agent_message: string | null;
  status: ChatTurnStatus;
  error: string | null;
}

export interface ChatState {
  backend: string | null;
  backend_thread_id: string | null;
  turns: ChatTurn[];
  active_persona: string | null;
}

export interface GraphSession {
  id: string;
  graph: Graph;
  version: number;
  proposals: Record<string, StoredProposal>;
  collab?: {
    reviews: Record<string, ReviewThread>;
    gates: Record<string, Gate>;
    chat: ChatState;
    attempts?: Record<string, Attempt>;
  };
}

// Shared non-POST request helper mirroring postJson's error-handling contract (parses
// `{"error": ...}` from a non-2xx body, else falls back to the HTTP status).
async function requestJson(path: string, init: RequestInit): Promise<Response> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.error ?? `Server error ${res.status}`);
  }
  return res;
}

export async function createSession(graph?: Graph): Promise<GraphSession> {
  const res = await postJson("/sessions", graph !== undefined ? { graph } : {});
  return (await res.json()) as GraphSession;
}

export async function getSession(sessionId: string): Promise<GraphSession> {
  const res = await requestJson(`/sessions/${sessionId}`, { method: "GET" });
  return (await res.json()) as GraphSession;
}

export async function deleteSession(sessionId: string): Promise<void> {
  await requestJson(`/sessions/${sessionId}`, { method: "DELETE" });
}

export async function replaceSessionGraph(
  sessionId: string,
  graph: Graph,
  expectedVersion: number,
): Promise<GraphSession> {
  const res = await requestJson(`/sessions/${sessionId}/graph`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ graph, expected_version: expectedVersion }),
  });
  return (await res.json()) as GraphSession;
}

export async function proposeMutation(
  sessionId: string,
  mutation: GraphMutation,
): Promise<StoredProposal> {
  const res = await postJson(`/sessions/${sessionId}/proposals`, mutation);
  return (await res.json()) as StoredProposal;
}

export async function compileSession(sessionId: string): Promise<{ code: string }> {
  const res = await postJson(`/sessions/${sessionId}/compile`, {});
  return (await res.json()) as { code: string };
}

export interface ExecuteSessionScope {
  run_to?: string[];
  run_from?: string[];
  run_only?: string[];
}

export interface ExecuteSessionResult {
  payloads: Record<string, Record<string, unknown>>;
  statuses: Record<string, { status: string; error?: string; reason?: string }>;
  elapsed_ms: Record<string, number>;
}

export async function executeSession(
  sessionId: string,
  scope?: ExecuteSessionScope,
): Promise<ExecuteSessionResult> {
  const res = await postJson(`/sessions/${sessionId}/execute`, scope ?? {});
  return (await res.json()) as ExecuteSessionResult;
}

export interface ConsultInput {
  persona: string;
  node_ids: string[];
  ask: string;
  provider?: string;
  model?: string;
}

export async function consultSession(
  sessionId: string,
  input: ConsultInput,
): Promise<StoredProposal> {
  const res = await postJson(`/sessions/${sessionId}/consult`, input);
  return (await res.json()) as StoredProposal;
}

export async function acceptProposal(
  sessionId: string,
  proposalId: string,
): Promise<GraphSession> {
  const res = await postJson(
    `/sessions/${sessionId}/proposals/${proposalId}/accept`,
    {},
  );
  return (await res.json()) as GraphSession;
}

export async function rejectProposal(
  sessionId: string,
  proposalId: string,
): Promise<GraphSession> {
  const res = await postJson(
    `/sessions/${sessionId}/proposals/${proposalId}/reject`,
    {},
  );
  return (await res.json()) as GraphSession;
}

export async function createReview(
  sessionId: string,
  input: CreateReviewInput,
): Promise<ReviewThread> {
  const res = await postJson(`/sessions/${sessionId}/reviews`, input);
  return (await res.json()) as ReviewThread;
}

export async function addReviewComment(
  sessionId: string,
  reviewId: string,
  comment: { author: string; text: string },
): Promise<ReviewThread> {
  const res = await postJson(
    `/sessions/${sessionId}/reviews/${reviewId}/comments`,
    comment,
  );
  return (await res.json()) as ReviewThread;
}

export async function createGate(
  sessionId: string,
  input: CreateGateInput,
): Promise<Gate> {
  const res = await postJson(`/sessions/${sessionId}/gates`, input);
  return (await res.json()) as Gate;
}

export async function closeGateRequest(
  sessionId: string,
  gateId: string,
): Promise<Gate> {
  const res = await postJson(
    `/sessions/${sessionId}/gates/${gateId}/close`,
    {},
  );
  return (await res.json()) as Gate;
}

export async function skipGateRequest(
  sessionId: string,
  gateId: string,
): Promise<Gate> {
  const res = await postJson(`/sessions/${sessionId}/gates/${gateId}/skip`, {});
  return (await res.json()) as Gate;
}

export async function postGateDecision(
  sessionId: string,
  gateId: string,
  decision: { author: string; text: string },
): Promise<Gate> {
  const res = await postJson(
    `/sessions/${sessionId}/gates/${gateId}/decisions`,
    decision,
  );
  return (await res.json()) as Gate;
}

export interface StartChatInput {
  backend: string;
  message: string;
}

export async function startChat(
  sessionId: string,
  input: StartChatInput,
): Promise<ChatTurn> {
  const res = await postJson(`/sessions/${sessionId}/chat`, input);
  return (await res.json()) as ChatTurn;
}

export async function stopChatTurn(
  sessionId: string,
  turnId: string,
): Promise<ChatTurn> {
  const res = await postJson(`/sessions/${sessionId}/chat/${turnId}/stop`, {});
  return (await res.json()) as ChatTurn;
}

export async function endChat(sessionId: string): Promise<GraphSession> {
  const res = await postJson(`/sessions/${sessionId}/chat/end`, {});
  return (await res.json()) as GraphSession;
}

export async function getAvailableAgents(): Promise<string[]> {
  const res = await requestJson("/agents", { method: "GET" });
  const body = (await res.json()) as { agents: string[] };
  return body.agents;
}

export interface SessionEventSubscription {
  close: () => void;
}

// Subscribes to a session's live event stream. Prefers the browser's native EventSource
// (matches the server's plain `data: <json>\n\n` SSE frames with no custom event name, so
// `onmessage` receives every frame directly). Falls back to polling GET /sessions/{id} when
// EventSource is unavailable (e.g. some test/SSR environments): on every version bump it
// synthesizes a `graph_replaced` event, and on any change to the chat state (which never
// bumps `version` -- see the poll loop below) a `chat_narration_added` event, so callers
// behave the same regardless of transport.
export function subscribeToSessionEvents(
  sessionId: string,
  onEvent: (event: SessionEvent) => void,
  options?: { pollIntervalMs?: number },
): SessionEventSubscription {
  if (typeof EventSource !== "undefined") {
    const source = new EventSource(`/sessions/${sessionId}/events`);
    source.onmessage = (ev: MessageEvent<string>) => {
      try {
        const parsed: unknown = JSON.parse(ev.data);
        if (!validateSessionEvent(parsed).valid) {
          return;
        }
        onEvent(parsed as SessionEvent);
      } catch {
        // Malformed frame -- ignore rather than crash the subscriber.
      }
    };
    return {
      close: () => source.close(),
    };
  }

  let lastVersion: number | null = null;
  // Chat turns (start/narrate/complete/fail) never bump `session.version` -- only the two
  // graph-mutation paths in collab/session.py do -- so version alone can't detect a chat
  // update. Track a snapshot of the chat state too, and synthesize an event on either
  // changing, or a chat turn started/streamed/finished while polling would silently never
  // reach the UI (it would sit on "working..." until an unrelated version bump happened to
  // trigger a refetch).
  let lastChatSnapshot: string | null = null;
  let stopped = false;
  const intervalMs = options?.pollIntervalMs ?? 2000;

  const poll = async (): Promise<void> => {
    if (stopped) return;
    // Skip the network round-trip while the tab is backgrounded; still reschedules so
    // polling resumes automatically once the tab regains visibility.
    if (typeof document === "undefined" || !document.hidden) {
      try {
        const session = await getSession(sessionId);
        const chatSnapshot = JSON.stringify(session.collab?.chat ?? null);
        if (lastVersion !== null && session.version !== lastVersion) {
          onEvent({
            type: "graph_replaced",
            session_id: sessionId,
            version: session.version,
          });
        } else if (lastChatSnapshot !== null && chatSnapshot !== lastChatSnapshot) {
          onEvent({
            type: "chat_narration_added",
            session_id: sessionId,
            version: session.version,
          });
        }
        lastVersion = session.version;
        lastChatSnapshot = chatSnapshot;
      } catch {
        // Network hiccup -- try again next tick rather than tearing down the subscription.
      }
    }
    if (!stopped) setTimeout(() => void poll(), intervalMs);
  };
  void poll();

  return {
    close: () => {
      stopped = true;
    },
  };
}
