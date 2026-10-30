// Full-frame browser for the Data tab (issue #178): filters, sorts and pages the node's whole
// stored DataFrame via `/browse/frame` instead of the 50-row preview. Pinned to the revision the
// run produced -- if the stored output was replaced or evicted it says so rather than silently
// showing different data. Browsing is read-only and never mutates the graph.

import { useState } from "react";
import type { CSSProperties } from "react";

import { useFrameBrowse } from "./useFrameBrowse";
import type { BrowseFilter, BrowseSort } from "./useFrameBrowse";

const PAGE_SIZE = 100;
const OPERATORS = ["==", "!=", "<", "<=", ">", ">=", "isin"];

interface FilterRow {
  id: number;
  column: string;
  operator: string;
  value: string;
}

interface FrameBrowserProps {
  nodeId: string;
  portName: string;
  revision: string;
  columns: string[];
  dtypes: string[];
}

const cellStyle: CSSProperties = {
  border: "1px solid var(--border-subtle)",
  padding: "0.15rem 0.4rem",
  fontSize: 11,
};

const inputStyle: CSSProperties = {
  padding: "0.2rem 0.4rem",
  fontSize: 11,
  border: "1px solid var(--border-subtle)",
  borderRadius: "var(--radius-sm)",
  background: "var(--surface-1)",
  color: "var(--text-primary)",
};

const mutedStyle: CSSProperties = { color: "var(--text-secondary)", fontSize: 11 };

// A filter row only constrains the query once it has a value; `isin` takes a comma list.
function toFilter(row: FilterRow): BrowseFilter | null {
  const raw = row.value.trim();
  if (raw === "") {
    return null;
  }
  const value = row.operator === "isin" ? raw.split(",").map((v) => v.trim()) : raw;
  return { column: row.column, operator: row.operator, value };
}

export function FrameBrowser({
  nodeId,
  portName,
  revision,
  columns,
  dtypes,
}: FrameBrowserProps): JSX.Element {
  const [filterRows, setFilterRows] = useState<FilterRow[]>([]);
  const [sort, setSort] = useState<BrowseSort[]>([]);
  const [offset, setOffset] = useState(0);
  const [nextId, setNextId] = useState(1);

  const filters = filterRows.map(toFilter).filter((f): f is BrowseFilter => f !== null);
  const state = useFrameBrowse({
    nodeId,
    port: portName,
    revision,
    filters,
    sort,
    offset,
    limit: PAGE_SIZE,
  });

  const updateFilters = (next: FilterRow[]): void => {
    setFilterRows(next);
    setOffset(0);
  };

  const handleSort = (col: string): void => {
    const cur = sort[0];
    if (!cur || cur.column !== col) {
      setSort([{ column: col, ascending: true }]);
    } else if (cur.ascending) {
      setSort([{ column: col, ascending: false }]);
    } else {
      setSort([]);
    }
    setOffset(0);
  };

  const window = state.phase === "ok" ? state.data : state.phase === "loading" ? state.prev : null;

  const renderStatus = (): JSX.Element | null => {
    if (state.phase === "expired" || state.phase === "revision_mismatch") {
      return (
        <p data-testid="browse-replaced" style={{ ...mutedStyle, color: "var(--text-warning, #b45309)" }}>
          Output replaced or evicted — re-run
        </p>
      );
    }
    if (state.phase === "not_tabular") {
      return <p data-testid="browse-not-tabular" style={mutedStyle}>This output is not a table.</p>;
    }
    if (state.phase === "error") {
      return <p data-testid="browse-error" style={{ color: "var(--text-error, #b91c1c)", fontSize: 11 }}>{state.message}</p>;
    }
    return null;
  };

  const blocked =
    state.phase === "expired" ||
    state.phase === "revision_mismatch" ||
    state.phase === "not_tabular";
  const shownCols = window ? window.columns : columns;

  let range: JSX.Element | null = null;
  if (window && !blocked) {
    const first = window.filtered_rows === 0 ? 0 : window.offset + 1;
    const last = window.offset + window.rows.length;
    range = (
      <span data-testid="browse-range" style={mutedStyle}>
        Showing {first}–{last} of {window.filtered_rows.toLocaleString()}
        {window.filtered_rows !== window.total_rows
          ? ` (of ${window.total_rows.toLocaleString()})`
          : ""}
      </span>
    );
  }

  return (
    <div data-testid="frame-browser">
      <div style={{ ...mutedStyle, marginBottom: "0.25rem" }}>
        Browsing the full stored table (not the preview).
      </div>

      {filterRows.map((row) => (
        <div key={row.id} style={{ display: "flex", gap: "0.25rem", marginBottom: "0.25rem" }} data-testid="browse-filter-row">
          <select
            value={row.column}
            aria-label="Filter column"
            style={inputStyle}
            onChange={(e) =>
              updateFilters(filterRows.map((r) => (r.id === row.id ? { ...r, column: e.target.value } : r)))
            }
          >
            {columns.map((c, i) => (
              <option key={`${i}-${c}`} value={c}>
                {c} ({dtypes[i] ?? "?"})
              </option>
            ))}
          </select>
          <select
            value={row.operator}
            aria-label="Filter operator"
            style={inputStyle}
            onChange={(e) =>
              updateFilters(filterRows.map((r) => (r.id === row.id ? { ...r, operator: e.target.value } : r)))
            }
          >
            {OPERATORS.map((op) => (
              <option key={op} value={op}>{op}</option>
            ))}
          </select>
          <input
            type="text"
            value={row.value}
            aria-label="Filter value"
            placeholder={row.operator === "isin" ? "a, b, c" : "value"}
            style={{ ...inputStyle, flex: 1 }}
            onChange={(e) =>
              updateFilters(filterRows.map((r) => (r.id === row.id ? { ...r, value: e.target.value } : r)))
            }
          />
          <button type="button" aria-label="Remove filter" onClick={() => updateFilters(filterRows.filter((r) => r.id !== row.id))}>
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        data-testid="browse-add-filter"
        disabled={columns.length === 0}
        onClick={() => {
          updateFilters([...filterRows, { id: nextId, column: columns[0] ?? "", operator: "==", value: "" }]);
          setNextId(nextId + 1);
        }}
      >
        + Add filter
      </button>

      {renderStatus()}

      {!blocked ? (
        <>
          <div style={{ margin: "0.25rem 0" }}>
            {range}
            {state.phase === "loading" ? <span style={mutedStyle}> Loading…</span> : null}
          </div>
          <div style={{ maxHeight: 250, overflow: "auto", marginBottom: "0.5rem" }}>
            <table data-testid="browse-table" style={{ fontSize: 11, borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr>
                  {shownCols.map((col, i) => (
                    <th
                      key={`${i}-${col}`}
                      style={{ ...cellStyle, cursor: "pointer", userSelect: "none", fontWeight: 600, background: "var(--surface-2)" }}
                      onClick={() => handleSort(col)}
                      data-testid={`browse-col-header-${col}`}
                    >
                      {col}
                      {sort[0]?.column === col ? (sort[0].ascending ? " ▲" : " ▼") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(window?.rows ?? []).map((row, i) => (
                  <tr key={String(row._row ?? i)} data-testid="browse-row">
                    {shownCols.map((col, j) => (
                      <td key={`${j}-${col}`} style={cellStyle}>{String(row[col] ?? "")}</td>
                    ))}
                  </tr>
                ))}
                {window && window.rows.length === 0 ? (
                  <tr>
                    <td colSpan={Math.max(shownCols.length, 1)} style={{ ...cellStyle, textAlign: "center", color: "var(--text-secondary)" }}>
                      No matching rows
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <button type="button" data-testid="browse-prev" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Prev
            </button>
            <button
              type="button"
              data-testid="browse-next"
              disabled={!window || offset + PAGE_SIZE >= window.filtered_rows}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}

export default FrameBrowser;
