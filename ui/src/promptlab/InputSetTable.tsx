import type { JSX } from "react";

import "./InputSetTable.css";

export type InputRow = Record<string, string>;

export interface InputSetTableProps {
  variables: string[];
  rows: InputRow[];
  onChange: (rows: InputRow[]) => void;
}

function emptyRow(variables: string[]): InputRow {
  return Object.fromEntries(variables.map((v) => [v, ""]));
}

export function InputSetTable({
  variables,
  rows,
  onChange,
}: InputSetTableProps): JSX.Element {
  if (variables.length === 0) {
    return (
      <div className="ef-promptlab-inputset" data-testid="input-set-table">
        <p className="ef-promptlab-inputset__empty-note">
          No variables in your prompt — this will run once with no bindings
          (single run mode).
        </p>
      </div>
    );
  }

  function updateCell(rowIndex: number, variable: string, value: string): void {
    const next = rows.map((row, i) =>
      i === rowIndex ? { ...row, [variable]: value } : row,
    );
    onChange(next);
  }

  function addRow(): void {
    onChange([...rows, emptyRow(variables)]);
  }

  function removeRow(rowIndex: number): void {
    onChange(rows.filter((_, i) => i !== rowIndex));
  }

  return (
    <div className="ef-promptlab-inputset" data-testid="input-set-table">
      <table className="ef-promptlab-inputset__table">
        <thead>
          <tr>
            {variables.map((v) => (
              <th key={v}>{v}</th>
            ))}
            <th aria-label="row actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {variables.map((v) => (
                <td key={v}>
                  <input
                    type="text"
                    value={row[v] ?? ""}
                    onChange={(e) => updateCell(rowIndex, v, e.target.value)}
                    data-testid={`input-set-cell-${rowIndex}-${v}`}
                  />
                </td>
              ))}
              <td>
                <button
                  type="button"
                  onClick={() => removeRow(rowIndex)}
                  aria-label={`Remove row ${rowIndex + 1}`}
                  data-testid={`input-set-remove-${rowIndex}`}
                >
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={addRow}
        className="ef-promptlab-inputset__add-row"
        data-testid="input-set-add-row"
      >
        + Add row
      </button>
    </div>
  );
}
