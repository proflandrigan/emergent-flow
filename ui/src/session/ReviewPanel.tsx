// Review panel (Epic 14 Story 6): renders review threads posted against the session's graph.
// Findings reuse the SAME Diagnostic type ef.validate output uses, but here they are always
// rendered as review comments (a colored dot + message + anchor label), never as pass/fail
// chips -- ProposalPanel's DiagnosticsVerdict stays the "this proposal type-checks" moment;
// this is the OTHER direction, an agent critiquing an existing graph. A finding with an
// attached `fix` offers "Apply fix", which is an ORDINARY proposal accept (sessionStore.propose
// + sessionStore.accept, both already implemented) -- zero new apply code here.

import { useState, type JSX } from "react";

import type { Diagnostic, Severity } from "../store/validation";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import type { ReviewComment, ReviewThread } from "./sessionClient";
import { useSessionStore } from "./sessionStore";

function severityColor(severity: Severity | string): string {
  switch (severity) {
    case "error":
      return "var(--danger)";
    case "warning":
      return "var(--warning)";
    case "info":
      return "var(--info)";
    default:
      return "var(--text-secondary)";
  }
}

function FindingRow({ finding }: { finding: Diagnostic }): JSX.Element {
  const anchor = finding.node_id
    ? `node ${finding.node_id}`
    : finding.edge_id
      ? `edge ${finding.edge_id}`
      : null;
  return (
    <div
      data-testid="review-finding"
      style={{
        display: "flex",
        gap: "var(--space-2)",
        alignItems: "flex-start",
        padding: "0.35rem 0.5rem",
        borderRadius: "var(--radius-sm)",
        background: "var(--surface-2)",
        marginBottom: "0.25rem",
        fontSize: "var(--text-xs)",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: severityColor(finding.severity),
          marginTop: 4,
          flexShrink: 0,
        }}
      />
      <div>
        <div>{finding.message}</div>
        {anchor ? (
          <div style={{ color: "var(--text-secondary)" }}>{anchor}</div>
        ) : null}
      </div>
    </div>
  );
}

function CommentRow({ comment }: { comment: ReviewComment }): JSX.Element {
  return (
    <div
      data-testid="review-comment"
      style={{ fontSize: "var(--text-xs)", marginBottom: "0.15rem" }}
    >
      <span style={{ fontWeight: 600 }}>{comment.author}: </span>
      {comment.text}
    </div>
  );
}

function ReviewThreadCard({ thread }: { thread: ReviewThread }): JSX.Element {
  const applyFix = useSessionStore((s) => s.applyFix);
  const postReviewComment = useSessionStore((s) => s.postReviewComment);
  const [replyText, setReplyText] = useState("");

  const handleApplyFix = () => void applyFix(thread.id);
  const handleReply = () => {
    const text = replyText.trim();
    if (!text) return;
    void postReviewComment(thread.id, { author: "human", text });
    setReplyText("");
  };

  return (
    <div
      data-testid="review-thread"
      style={{
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "0.5rem",
        marginBottom: "0.5rem",
      }}
    >
      <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>
        {thread.author}
      </div>
      {thread.findings.map((f, i) => (
        <FindingRow key={i} finding={f} />
      ))}
      {thread.comments.map((c) => (
        <CommentRow key={c.id} comment={c} />
      ))}
      {thread.fix ? (
        <Button
          variant="primary"
          onClick={handleApplyFix}
          data-testid="review-apply-fix"
        >
          Apply fix
        </Button>
      ) : null}
      <div
        style={{ display: "flex", gap: "var(--space-2)", marginTop: "0.5rem" }}
      >
        <Input
          data-testid="review-reply-input"
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          placeholder="Reply..."
        />
        <Button
          variant="secondary"
          onClick={handleReply}
          data-testid="review-reply-submit"
        >
          Reply
        </Button>
      </div>
    </div>
  );
}

export interface ReviewPanelProps {
  className?: string;
}

// Renders nothing when there is no active session -- session UI stays strictly opt-in.
export function ReviewPanel({
  className,
}: ReviewPanelProps): JSX.Element | null {
  const sessionId = useSessionStore((s) => s.sessionId);
  const reviews = useSessionStore((s) => s.reviews);

  if (sessionId === null) {
    return null;
  }

  const list = Object.values(reviews).sort((a, b) => a.id.localeCompare(b.id));

  return (
    <div className={className} data-testid="review-panel">
      <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Reviews</div>
      {list.length === 0 ? (
        <div
          data-testid="review-panel-empty"
          style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}
        >
          No reviews yet
        </div>
      ) : (
        list.map((t) => <ReviewThreadCard key={t.id} thread={t} />)
      )}
    </div>
  );
}
