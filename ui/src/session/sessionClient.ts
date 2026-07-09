// Session HTTP client (Epic 14 Story 4) -- typed fetch wrappers over the graph-session routes
// on emergentflow/server/app.py (POST/GET/DELETE /sessions, PUT .../graph, propose/accept/reject,
// and the /events SSE stream). Pure I/O boundary: no React, no Zustand -- ui/src/session/sessionStore.ts
// (a later task) is the only caller. Uses the same relative-path + `{"error": ...}`-on-failure
// convention as ui/src/promptlab/httpJson.ts's postJson.

import { postJson } from "../promptlab/httpJson";
import type { Graph } from "../generated/ir";
import type { GraphMutation } from "../generated/mutation";
import type { SessionEvent } from "../generated/session_event";
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

export interface CreateReviewInput {
  author: string;
  findings?: Diagnostic[];
  fix?: GraphMutation | null;
}

export interface GraphSession {
  id: string;
  graph: Graph;
  version: number;
  proposals: Record<string, StoredProposal>;
  collab?: { reviews: Record<string, ReviewThread> };
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

export interface SessionEventSubscription {
  close: () => void;
}

// Subscribes to a session's live event stream. Prefers the browser's native EventSource
// (matches the server's plain `data: <json>\n\n` SSE frames with no custom event name, so
// `onmessage` receives every frame directly). Falls back to polling GET /sessions/{id} when
// EventSource is unavailable (e.g. some test/SSR environments): on every version bump it
// synthesizes a `graph_replaced` event so callers behave the same regardless of transport.
export function subscribeToSessionEvents(
  sessionId: string,
  onEvent: (event: SessionEvent) => void,
  options?: { pollIntervalMs?: number },
): SessionEventSubscription {
  if (typeof EventSource !== "undefined") {
    const source = new EventSource(`/sessions/${sessionId}/events`);
    source.onmessage = (ev: MessageEvent<string>) => {
      try {
        onEvent(JSON.parse(ev.data) as SessionEvent);
      } catch {
        // Malformed frame -- ignore rather than crash the subscriber.
      }
    };
    return {
      close: () => source.close(),
    };
  }

  let lastVersion: number | null = null;
  let stopped = false;
  const intervalMs = options?.pollIntervalMs ?? 2000;

  const poll = async (): Promise<void> => {
    if (stopped) return;
    try {
      const session = await getSession(sessionId);
      if (lastVersion !== null && session.version !== lastVersion) {
        onEvent({
          type: "graph_replaced",
          session_id: sessionId,
          version: session.version,
        });
      }
      lastVersion = session.version;
    } catch {
      // Network hiccup -- try again next tick rather than tearing down the subscription.
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
