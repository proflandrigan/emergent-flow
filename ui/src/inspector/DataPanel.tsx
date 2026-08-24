// Data inspector tab: sortable, filterable table explorer with column types
// and describe stats for table-type results of the selected node.

import { useMemo, useState } from "react";

import type { Payload } from "../store/execution";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { selectedNodeId, useSelectionStore } from "../store/selectionStore";

type SortDir = "asc" | "desc" | null;

interface TableExplorerProps {
  portName: string;
  payload: Extract<Payload, { kind: "table" }>;
}

const cellStyle: React.CSSProperties = {
  border: "1px solid var(--border-subtle)",
  padding: "0.15rem 0.4rem",
  fontSize: 11,
};

const headerCellStyle: React.CSSProperties = {
  ...cellStyle,
  cursor: "pointer",
  userSelect: "none",
  fontWeight: 600,
  background: "var(--surface-2)",
};

const filterInputStyle: React.CSSProperties = {
  width: "100%",
  padding: "0.25rem 0.5rem",
  fontSize: 11,
  border: "1px solid var(--border-subtle)",
  borderRadius: "var(--radius-sm)",
  background: "var(--surface-1)",
  color: "var(--text-primary)",
  boxSizing: "border-box",
};

function TableExplorer({ portName, payload }: TableExplorerProps): JSX.Element {
  const { columns, dtypes, head, shape, describe } = payload;
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);
  const [filter, setFilter] = useState("");

  const handleSort = (col: string): void => {
    if (sortCol === col) {
      if (sortDir === "asc") { setSortDir("desc"); }
      else if (sortDir === "desc") { setSortCol(null); setSortDir(null); }
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
  };

  const filtered = useMemo(() => {
    let rows = [...head];
    const f = filter.trim().toLowerCase();
    if (f) {
      rows = rows.filter((row) =>
        columns.some((col) => String(row[col] ?? "").toLowerCase().includes(f))
      );
    }
    if (sortCol !== null && sortDir !== null) {
      rows.sort((a, b) => {
        const av = a[sortCol] ?? "";
        const bv = b[sortCol] ?? "";
        if (typeof av === "number" && typeof bv === "number") {
          return sortDir === "asc" ? av - bv : bv - av;
        }
        const sa = String(av);
        const sb = String(bv);
        return sortDir === "asc" ? sa.localeCompare(sb) : sb.localeCompare(sa);
      });
    }
    return rows;
  }, [head, filter, sortCol, sortDir]);

  return (
    <div style={{ marginBottom: "1rem" }}>
      <div style={{ fontWeight: 600, marginBottom: "0.25rem", fontSize: 12 }}>
        {portName} — {shape[0]} rows × {shape[1]} cols
      </div>
      <input
        type="text"
        placeholder="Filter rows..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={filterInputStyle}
        data-testid="data-filter-input"
      />

      {/* Type row */}
      <div style={{ fontSize: 10, color: "var(--text-secondary)", padding: "0.15rem 0.4rem", fontFamily: "var(--font-mono)" }}>
        {columns.map((col, i) => (
          <span key={col} style={{ marginRight: "0.75rem" }} data-testid={`data-type-${col}`}>
            {col}: {dtypes[i] ?? "unknown"}
          </span>
        ))}
      </div>

      {/* Data table */}
      <div style={{ maxHeight: 250, overflow: "auto", marginBottom: "0.5rem" }}>
        <table
          data-testid="data-table"
          style={{ fontSize: 11, borderCollapse: "collapse", width: "100%" }}
        >
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  style={headerCellStyle}
                  onClick={() => handleSort(col)}
                  data-testid={`data-col-header-${col}`}
                >
                  {col}
                  {sortCol === col ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((row, i) => (
              <tr key={i} data-testid="data-row">
                {columns.map((col) => (
                  <td key={col} style={cellStyle}>
                    {String(row[col] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={columns.length} style={{ ...cellStyle, color: "var(--text-secondary)", textAlign: "center" }}>
                  No matching rows
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {/* Describe stats */}
      {describe && Object.keys(describe).length > 0 ? (
        <details data-testid="data-describe">
          <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 600, marginBottom: "0.25rem" }}>
            Column statistics (describe)
          </summary>
          {Object.entries(describe).map(([colName, stats]) => (
            <div
              key={colName}
              data-testid={`data-describe-col-${colName}`}
              style={{ marginLeft: "0.75rem", fontSize: 11, marginBottom: "0.25rem" }}
            >
              <div style={{ fontWeight: 600, fontFamily: "var(--font-mono)" }}>{colName}</div>
              {Object.entries(stats).map(([stat, val]) => (
                <div key={stat} style={{ display: "inline-block", marginRight: "0.75rem", color: "var(--text-secondary)" }}>
                  <span style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>{stat}</span>
                  :{" "}
                  <span>{val === null ? "—" : typeof val === "number" ? val.toFixed(4) : String(val)}</span>
                </div>
              ))}
            </div>
          ))}
          <div style={{ marginTop: "0.25rem", fontSize: 10, color: "var(--text-secondary)" }}>
            Computed over all {shape[0]} rows, not just the displayed sample.
          </div>
        </details>
      ) : null}
    </div>
  );
}

export function DataPanel(): JSX.Element {
  const selNodes = useSelectionStore((s) => s.nodes);
  const nodes = useGraphStore((s) => s.nodes);
  const nodeId = selectedNodeId({ nodes: selNodes });
  const results = useExecutionStore((s) => s.results);

  if (!nodeId) {
    return (
      <p data-testid="data-empty-no-selection" style={{ color: "var(--text-secondary)" }}>
        Select a node to explore its data.
      </p>
    );
  }

  const nodeResults = results[nodeId];
  if (!nodeResults || Object.keys(nodeResults).length === 0) {
    return (
      <p data-testid="data-empty-no-results" style={{ color: "var(--text-secondary)" }}>
        No results — run the graph first.
      </p>
    );
  }

  const tableEntries = Object.entries(nodeResults).filter(
    ([, p]) => p.kind === "table"
  ) as [string, Extract<Payload, { kind: "table" }>][];

  if (tableEntries.length === 0) {
    return (
      <p data-testid="data-empty-no-tables" style={{ color: "var(--text-secondary)" }}>
        This node has no tabular results.
      </p>
    );
  }

  return (
    <div data-testid="data-panel">
      {tableEntries.map(([portName, payload]) => (
        <TableExplorer key={portName} portName={portName} payload={payload} />
      ))}
    </div>
  );
}

export default DataPanel;