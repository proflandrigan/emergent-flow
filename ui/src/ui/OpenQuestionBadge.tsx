// Shared "open question" marker (issue #173): the ? badge used by open-question notes on the
// canvas and by a tour step's unknowns, so both read with the same meaning.
import type { JSX } from "react";
import "./OpenQuestionBadge.css";

export interface OpenQuestionBadgeProps {
  /** Visible label next to the ? mark. */
  label?: string;
}

export function OpenQuestionBadge({ label = "Open question" }: OpenQuestionBadgeProps): JSX.Element {
  return (
    <span className="ef-open-question-badge" data-testid="open-question-badge">
      <span className="ef-open-question-badge__mark" aria-hidden="true">?</span>
      <span className="ef-open-question-badge__label">{label}</span>
    </span>
  );
}

export default OpenQuestionBadge;
