import type { JSX } from "react";

import "./RunHistory.css";
import type { EvalVariantParams } from "./buildEvalGraph";
import type { CompareGridLabel } from "./CompareGrid";
import type { EvalRunRow } from "./runEval";

export interface RunHistoryEntry {
  id: string;
  timestamp: number;
  system: string;
  user: string;
  variants: EvalVariantParams[];
  dataset: Record<string, string>[];
  rows: EvalRunRow[];
  labels: CompareGridLabel[];
}

export interface RunHistoryProps {
  entries: RunHistoryEntry[];
  onSelect: (entry: RunHistoryEntry) => void;
}

function formatSummary(entry: RunHistoryEntry): string {
  const variantCount = entry.variants.length;
  const rowCount = entry.dataset.length;
  const variantWord = variantCount === 1 ? "variant" : "variants";
  const rowWord = rowCount === 1 ? "row" : "rows";
  return `${variantCount} ${variantWord} × ${rowCount} ${rowWord}`;
}

function formatTimestamp(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString();
}

export function RunHistory({
  entries,
  onSelect,
}: RunHistoryProps): JSX.Element {
  if (entries.length === 0) {
    return (
      <div className="ef-promptlab-history" data-testid="run-history">
        <p className="ef-promptlab-history__empty-note">No runs yet</p>
      </div>
    );
  }

  return (
    <ul className="ef-promptlab-history" data-testid="run-history">
      {entries.map((entry) => (
        <li key={entry.id} className="ef-promptlab-history__entry">
          <button
            type="button"
            className="ef-promptlab-history__button"
            onClick={() => onSelect(entry)}
            data-testid={`run-history-entry-${entry.id}`}
          >
            <span className="ef-promptlab-history__timestamp">
              {formatTimestamp(entry.timestamp)}
            </span>
            <span className="ef-promptlab-history__summary">
              {formatSummary(entry)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
