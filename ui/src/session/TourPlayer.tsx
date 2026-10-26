// Tour player (issue #171): a caption panel BESIDE the graph (not a modal) for the step being
// played. Purely presentational -- all state changes go through the callbacks.

import type { JSX } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ResolvedTourStep } from "../canvas/tourResolve";
import { Button } from "../ui/Button";
import type { Tour } from "./sessionClient";

export interface TourPlayerProps {
  tour: Tour;
  index: number;
  resolved: ResolvedTourStep | null;
  /** Display name for a node id (label, else id). */
  nodeName: (id: string) => string;
  onPrev: () => void;
  onNext: () => void;
  onExit: () => void;
  announcement?: string | null;
}

const srOnly = {
  position: "absolute",
  width: 1,
  height: 1,
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
} as const;

export function TourPlayer({
  tour,
  index,
  resolved,
  nodeName,
  onPrev,
  onNext,
  onExit,
  announcement,
}: TourPlayerProps): JSX.Element {
  const step = tour.steps[index];
  const count = tour.steps.length;
  const route = step?.route ?? null;
  const unknowns = step?.unknowns ?? [];

  return (
    <aside
      role="region"
      aria-label="Guided tour"
      data-testid="tour-player"
      style={{
        position: "absolute",
        top: 56,
        right: 12,
        bottom: 12,
        width: 340,
        maxWidth: "calc(100% - 24px)",
        overflowY: "auto",
        zIndex: 15,
        background: "var(--surface-1)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-3)",
        fontSize: "var(--text-sm)",
      }}
    >
      <h2 style={{ fontSize: "var(--text-sm)", margin: 0 }}>{tour.title}</h2>
      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
        by {tour.author}
      </div>
      <div
        data-testid="tour-conclusion"
        style={{
          margin: "var(--space-2) 0",
          padding: "var(--space-2)",
          borderRadius: "var(--radius-sm)",
          background: "var(--surface-2)",
          fontWeight: 600,
        }}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{tour.conclusion}</ReactMarkdown>
      </div>
      <div data-testid="tour-step-counter" style={{ fontSize: "var(--text-xs)" }}>
        Step {index + 1}/{count}
      </div>
      {(resolved?.removedIds ?? []).map((id) => (
        <span
          key={id}
          data-testid="tour-removed-badge"
          style={{
            display: "inline-block",
            fontSize: "var(--text-xs)",
            padding: "0 var(--space-2)",
            marginRight: "var(--space-2)",
            borderRadius: "var(--radius-sm)",
            background: "var(--surface-2)",
          }}
        >
          Node removed: {id}
        </span>
      ))}
      {resolved?.routeStatus === "no-path" && route ? (
        <div data-testid="tour-no-path" style={{ fontSize: "var(--text-xs)" }}>
          No directed path from {nodeName(route[0])} to {nodeName(route[1])}
        </div>
      ) : null}
      <div data-testid="tour-note">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{step?.note ?? ""}</ReactMarkdown>
      </div>
      {unknowns.length > 0 ? (
        <div
          data-testid="tour-open-questions"
          style={{
            borderLeft: "3px solid var(--warning, #d97706)",
            paddingLeft: "var(--space-2)",
            margin: "var(--space-2) 0",
            fontSize: "var(--text-xs)",
          }}
        >
          <strong>Open questions</strong>
          <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
            {unknowns.map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-2)" }}>
        <Button
          data-testid="tour-prev"
          aria-label="Previous step"
          disabled={index <= 0}
          onClick={onPrev}
        >
          Prev
        </Button>
        <Button
          data-testid="tour-next"
          aria-label="Next step"
          disabled={index >= count - 1}
          onClick={onNext}
        >
          Next
        </Button>
        <Button
          variant="ghost"
          data-testid="tour-exit"
          aria-label="Exit tour"
          onClick={onExit}
        >
          Exit (Esc)
        </Button>
      </div>
      <div aria-live="polite" className="sr-only" data-testid="tour-announcement" style={srOnly}>
        {announcement}
      </div>
    </aside>
  );
}
