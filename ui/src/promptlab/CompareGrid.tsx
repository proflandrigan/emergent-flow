import type { JSX } from "react";

import "./CompareGrid.css";
import { LabelControls } from "./LabelControls";
import type { EvalRunRow } from "./runEval";

export interface CompareGridLabel {
  row_id: number;
  variant: string; // "provider:model"
  label: string; // "pass" | "fail"
  score?: number;
}

export interface CompareGridProps {
  rows: EvalRunRow[];
  labels: CompareGridLabel[];
  onLabelsChange: (labels: CompareGridLabel[]) => void;
}

function variantOf(row: EvalRunRow): string {
  return `${row.provider}:${row.model}`;
}

function formatOutput(output: unknown): string {
  return typeof output === "string" ? output : JSON.stringify(output);
}

function formatBadge(row: EvalRunRow): string {
  const cost = row.cost_usd.toFixed(4);
  const tokens = row.input_tokens + row.output_tokens;
  const latency = row.latency_ms.toFixed(0);
  return `$${cost} · ${tokens} tok · ${latency}ms`;
}

export function CompareGrid({
  rows,
  labels,
  onLabelsChange,
}: CompareGridProps): JSX.Element {
  const rowIds = Array.from(new Set(rows.map((r) => r.row_id))).sort(
    (a, b) => a - b,
  );
  const variants = Array.from(new Set(rows.map(variantOf)));

  function labelFor(
    rowId: number,
    variant: string,
  ): CompareGridLabel | undefined {
    return labels.find((l) => l.row_id === rowId && l.variant === variant);
  }

  function setLabel(rowId: number, variant: string, label: string): void {
    const score = label === "pass" ? 1 : 0;
    const existingIndex = labels.findIndex(
      (l) => l.row_id === rowId && l.variant === variant,
    );
    const entry: CompareGridLabel = { row_id: rowId, variant, label, score };
    const next =
      existingIndex === -1
        ? [...labels, entry]
        : labels.map((l, i) => (i === existingIndex ? entry : l));
    onLabelsChange(next);
  }

  return (
    <table className="ef-promptlab-comparegrid" data-testid="compare-grid">
      <thead>
        <tr>
          <th>Input</th>
          {variants.map((v) => (
            <th key={v}>{v}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rowIds.map((rowId) => {
          const firstRow = rows.find((r) => r.row_id === rowId);
          return (
            <tr key={rowId}>
              <td data-testid={`compare-grid-input-${rowId}`}>
                {firstRow ? JSON.stringify(firstRow.input) : ""}
              </td>
              {variants.map((variant) => {
                const cell = rows.find(
                  (r) => r.row_id === rowId && variantOf(r) === variant,
                );
                if (!cell) {
                  return (
                    <td
                      key={variant}
                      data-testid={`compare-grid-cell-${rowId}-${variant}`}
                    />
                  );
                }
                const currentLabel = labelFor(rowId, variant);
                return (
                  <td
                    key={variant}
                    data-testid={`compare-grid-cell-${rowId}-${variant}`}
                  >
                    <div className="ef-promptlab-comparegrid__output">
                      {formatOutput(cell.output)}
                    </div>
                    <div className="ef-promptlab-comparegrid__badge">
                      {formatBadge(cell)}
                    </div>
                    <LabelControls
                      label={currentLabel?.label}
                      onLabel={(label) => setLabel(rowId, variant, label)}
                    />
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
