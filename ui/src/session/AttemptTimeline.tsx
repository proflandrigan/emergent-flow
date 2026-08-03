import type { JSX } from "react";

import { useSessionStore } from "./sessionStore";
import type { Attempt } from "./sessionClient";

function verdictColor(verdict: string): string {
  switch (verdict) {
    case "kept":
      return "var(--success)";
    case "reverted":
      return "var(--danger)";
    default:
      return "var(--text-secondary)";
  }
}

function AttemptCard({ attempt }: { attempt: Attempt }): JSX.Element {
  return (
    <div
      data-testid="attempt-card"
      style={{
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "0.5rem",
        marginBottom: "0.5rem",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>
          {attempt.author}
        </div>
        <div
          data-testid="attempt-verdict"
          style={{
            fontSize: "var(--text-xs)",
            color: verdictColor(attempt.verdict),
            fontWeight: 600,
          }}
        >
          {attempt.verdict}
        </div>
      </div>
      {attempt.hypothesis ? (
        <div
          style={{
            fontSize: "var(--text-xs)",
            color: "var(--text-secondary)",
            marginTop: "0.25rem",
          }}
        >
          {attempt.hypothesis}
        </div>
      ) : null}
      <div
        style={{
          fontSize: "var(--text-xs)",
          color: "var(--text-secondary)",
          marginTop: "0.25rem",
        }}
      >
        <div>Mutation: {attempt.mutation_id}</div>
        {attempt.run_id ? <div>Run: {attempt.run_id}</div> : null}
        {attempt.metric_name && attempt.metric_value !== null ? (
          <div>
            {attempt.metric_name}: {attempt.metric_value}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export interface AttemptTimelineProps {
  className?: string;
}

export function AttemptTimeline({
  className,
}: AttemptTimelineProps): JSX.Element | null {
  const sessionId = useSessionStore((s) => s.sessionId);
  const attempts = useSessionStore((s) => s.attempts);

  if (sessionId === null) {
    return null;
  }

  const list = Object.values(attempts).sort((a, b) => b.timestamp - a.timestamp);

  return (
    <div className={className} data-testid="attempt-timeline">
      <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Attempts</div>
      {list.length === 0 ? (
        <div
          data-testid="attempt-timeline-empty"
          style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}
        >
          No attempts yet
        </div>
      ) : (
        list.map((a) => <AttemptCard key={a.id} attempt={a} />)
      )}
    </div>
  );
}