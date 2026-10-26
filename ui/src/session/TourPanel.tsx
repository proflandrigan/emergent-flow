// Tour panel (issue #171): lists guided tours authored by agents via the MCP `set_tour` tool.
// Tours are session-only -- they live on the server session beside the graph, not in saved flows.
// Each row leads with the conclusion (markdown), then offers Play and Copy link.

import type { JSX } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { copyViewLink } from "../store/viewLinkStore";
import { useTourStore } from "../store/tourStore";
import { Button } from "../ui/Button";
import { useSessionStore } from "./sessionStore";

export function TourPanel({ onPlay }: { onPlay?: () => void }): JSX.Element {
  const tours = useSessionStore((s) => s.tours);
  const playingId = useTourStore((s) => s.playing?.tour.id ?? null);
  const list = Object.values(tours).sort((a, b) => a.id.localeCompare(b.id));

  if (list.length === 0) {
    return (
      <div
        data-testid="tour-empty"
        style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}
      >
        No tours yet. Ask the agent to walk you through a change — it creates tours with `set_tour`.
      </div>
    );
  }

  return (
    <div>
      {list.map((tour) => (
        <div
          key={tour.id}
          data-testid="tour-row"
          aria-current={playingId === tour.id ? "true" : undefined}
          style={{
            padding: "var(--space-2)",
            borderRadius: "var(--radius-sm)",
            background: "var(--surface-2)",
            marginBottom: "var(--space-2)",
            fontSize: "var(--text-xs)",
          }}
        >
          <div style={{ fontWeight: 600 }}>{tour.title}</div>
          <div style={{ color: "var(--text-secondary)" }}>
            by {tour.author} · {tour.steps.length} {tour.steps.length === 1 ? "step" : "steps"}
          </div>
          <div>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{tour.conclusion}</ReactMarkdown>
          </div>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <Button
              data-testid="tour-play"
              aria-label={`Play tour ${tour.title}`}
              onClick={() => {
                useTourStore.getState().start(tour, 0);
                onPlay?.();
              }}
            >
              Play
            </Button>
            <Button
              variant="ghost"
              data-testid="tour-copy-link"
              aria-label={`Copy link to tour ${tour.title}`}
              onClick={() => {
                void copyViewLink({ tour: tour.id, step: 0 });
              }}
            >
              Copy link
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
