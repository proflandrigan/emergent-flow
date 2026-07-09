/* AUTO-GENERATED from session_event.schema.json by `npm run gen:types`. Do not edit. */

export type ProposalId = string | null;
export type SessionId = string;
export type Type = "graph_replaced" | "proposal_added" | "proposal_accepted" | "proposal_rejected";
export type Version = number | null;

/**
 * The shape of every event `SessionStore` publishes on a session's SSE stream.
 */
export interface SessionEvent {
  proposal_id?: ProposalId;
  session_id: SessionId;
  type: Type;
  version?: Version;
}
