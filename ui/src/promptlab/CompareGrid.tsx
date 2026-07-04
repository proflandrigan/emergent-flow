import type { JSX } from "react";
import { useMemo } from "react";

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

function cellKey(rowId: number, variant: string): string {
  return `${rowId}:${variant}`;
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
  // Grid render cost is O(rowIds x variants); building lookup maps once per `rows`/`labels`
  // change (rather than re-scanning the full array for every cell) keeps that from also
  // scaling with `rows.length`/`labels.length` on every render.
  const { rowIds, variants, cellByKey, inputByRowId } = useMemo(() => {
    const rowIdSet = new Set<number>();
    const variantSet = new Set<string>();
    const cellMap = new Map<string, EvalRunRow>();
    const inputMap = new Map<number, Record<string, unknown>>();
    for (const row of rows) {
      rowIdSet.add(row.row_id);
      const variant = variantOf(row);
      variantSet.add(variant);
      cellMap.set(cellKey(row.row_id, variant), row);
      if (!inputMap.has(row.row_id)) {
        inputMap.set(row.row_id, row.input);
      }
    }
    return {
      rowIds: Array.from(rowIdSet).sort((a, b) => a - b),
      variants: Array.from(variantSet),
      cellByKey: cellMap,
      inputByRowId: inputMap,
    };
  }, [rows]);

  const labelByKey = useMemo(() => {
    const map = new Map<string, CompareGridLabel>();
    for (const label of labels) {
      map.set(cellKey(label.row_id, label.variant), label);
    }
    return map;
  }, [labels]);

  function setLabel(rowId: number, variant: string, label: string): void {
    const score = label === "pass" ? 1 : 0;
    const entry: CompareGridLabel = { row_id: rowId, variant, label, score };
    const next = [
      ...labels.filter((l) => !(l.row_id === rowId && l.variant === variant)),
      entry,
    ];
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
          const input = inputByRowId.get(rowId);
          return (
            <tr key={rowId}>
              <td data-testid={`compare-grid-input-${rowId}`}>
                {input ? JSON.stringify(input) : ""}
              </td>
              {variants.map((variant) => {
                const cell = cellByKey.get(cellKey(rowId, variant));
                if (!cell) {
                  return (
                    <td
                      key={variant}
                      data-testid={`compare-grid-cell-${rowId}-${variant}`}
                    />
                  );
                }
                const currentLabel = labelByKey.get(cellKey(rowId, variant));
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
