/* AUTO-GENERATED from session_event.schema.json by `npm run gen:types`. Do not edit. */

export type CommentId = string | null;
export type ProposalId = string | null;
export type ReviewId = string | null;
export type SessionId = string;
export type Type =
  | "graph_replaced"
  | "proposal_added"
  | "proposal_accepted"
  | "proposal_rejected"
  | "review_added"
  | "review_comment_added";
export type Version = number | null;

/**
 * The shape of every event `SessionStore` publishes on a session's SSE stream.
 */
export interface SessionEvent {
  comment_id?: CommentId;
  proposal_id?: ProposalId;
  review_id?: ReviewId;
  session_id: SessionId;
  type: Type;
  version?: Version;
}
