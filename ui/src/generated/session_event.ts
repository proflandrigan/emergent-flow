/* AUTO-GENERATED from session_event.schema.json by `npm run gen:types`. Do not edit. */

export type CommentId = string | null;
export type DecisionId = string | null;
export type GateId = string | null;
export type ProposalId = string | null;
export type ReviewId = string | null;
export type SessionId = string;
export type TurnId = string | null;
export type Type =
  | "graph_replaced"
  | "proposal_added"
  | "proposal_accepted"
  | "proposal_rejected"
  | "review_added"
  | "review_comment_added"
  | "gate_opened"
  | "gate_closed"
  | "gate_skipped"
  | "decision_added"
  | "chat_turn_started"
  | "chat_narration_added"
  | "chat_turn_completed"
  | "chat_turn_failed"
  | "chat_turn_interrupted"
  | "chat_ended";
export type Version = number | null;

/**
 * The shape of every event `SessionStore` publishes on a session's SSE stream.
 */
export interface SessionEvent {
  comment_id?: CommentId;
  decision_id?: DecisionId;
  gate_id?: GateId;
  proposal_id?: ProposalId;
  review_id?: ReviewId;
  session_id: SessionId;
  turn_id?: TurnId;
  type: Type;
  version?: Version;
}
