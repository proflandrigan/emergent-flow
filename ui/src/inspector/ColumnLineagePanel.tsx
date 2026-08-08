// Inspector Lineage tab's column-level view (Epic 18, Story 5): POSTs the current graph plus
// the selected node + column to the local server's `/lineage/column` route and renders the
// column's derivation chain as readable steps ("revenue → log1p → revenue_log") rather than a
// bare node list. Column lineage is a pure on-demand function of the graph (Epic 18), so it is
// never stored and re-traces on every selection.

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import { useGraphStore } from "../store/graphStore";

interface ColumnLineageNodeDTO {
  node_id: string;
  node_type: string;
  label: string | null;
  column: string;
  role: string;
  source_column?: string | null;
  detail?: string | null;
}

interface ColumnLineageEdgeDTO {
  source_node_id: string;
  source_column: string;
  target_node_id: string;
  target_column: string;
  role: string;
}

interface ColumnLineageDTO {
  target_node_id: string;
  target_column: string;
  nodes: ColumnLineageNodeDTO[];
  edges: ColumnLineageEdgeDTO[];
}

const mutedStyle: CSSProperties = { color: "var(--text-secondary)" };

function isColumnLineageNodeDTO(value: unknown): value is ColumnLineageNodeDTO {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const v = value as Record<string, unknown>;
  return (
    typeof v.node_id === "string" &&
    typeof v.node_type === "string" &&
    (v.label === null || typeof v.label === "string") &&
    typeof v.column === "string" &&
    typeof v.role === "string" &&
    (v.source_column === undefined ||
      v.source_column === null ||
      typeof v.source_column === "string") &&
    (v.detail === undefined || v.detail === null || typeof v.detail === "string")
  );
}

function isColumnLineageDTO(value: unknown): value is ColumnLineageDTO {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const v = value as Record<string, unknown>;
  return (
    typeof v.target_node_id === "string" &&
    typeof v.target_column === "string" &&
    Array.isArray(v.nodes) &&
    v.nodes.every(isColumnLineageNodeDTO) &&
    Array.isArray(v.edges)
  );
}

interface ColumnLineagePanelProps {
  nodeId: string | null;
  column: string | null;
  debounceMs?: number;
}

export function ColumnLineagePanel({
  nodeId,
  column,
  debounceMs = 400,
}: ColumnLineagePanelProps): JSX.Element {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const [lineage, setLineage] = useState<ColumnLineageDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (nodeId === null || column === null) {
      setLineage(null);
      setError(null);
      return;
    }

    const graph = useGraphStore.getState().toIR();
    if (Object.keys(graph.nodes ?? {}).length === 0) {
      setLineage(null);
      setError(null);
      return;
    }

    let cancelled = false;
    const handle = setTimeout(() => {
      void (async () => {
        try {
          const res = await fetch("/lineage/column", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ graph, node_id: nodeId, column }),
          });
          const body = await res.json();
          if (cancelled) {
            return;
          }
          if (!res.ok || body.error) {
            setError(body.error ?? `Server error ${res.status}`);
            setLineage(null);
          } else if (isColumnLineageDTO(body.lineage)) {
            setLineage(body.lineage);
            setError(null);
          } else {
            setError("Malformed column-lineage response from server.");
            setLineage(null);
          }
        } catch (err) {
          if (!cancelled) {
            const msg = err instanceof Error ? err.message : String(err);
            setError("Could not reach server: " + msg);
            setLineage(null);
          }
        }
      })();
    }, debounceMs);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [nodes, edges, nodeId, column, debounceMs]);

  if (nodeId === null) {
    return (
      <p data-testid="column-lineage-empty-no-selection" style={mutedStyle}>
        Select a node to trace a column's lineage.
      </p>
    );
  }

  if (column === null) {
    return (
      <p data-testid="column-lineage-empty-no-column" style={mutedStyle}>
        Click a column in the results table to trace where it came from.
      </p>
    );
  }

  if (Object.keys(nodes).length === 0) {
    return (
      <p data-testid="column-lineage-empty" style={mutedStyle}>
        Add nodes to trace column lineage.
      </p>
    );
  }

  if (error) {
    return (
      <div
        data-testid="column-lineage-error"
        style={{ color: "var(--danger)", whiteSpace: "pre-wrap" }}
      >
        {error}
      </div>
    );
  }

  if (lineage === null) {
    return (
      <p data-testid="column-lineage-loading" style={mutedStyle}>
        Tracing column lineage…
      </p>
    );
  }

  const current = lineage;

  const displayName = (n: ColumnLineageNodeDTO): string =>
    n.label !== null && n.label !== "" ? n.label : n.node_type;

  // Render the chain as readable steps: source column → labelled role → derived column.
  return (
    <div data-testid="column-lineage">
      <div data-testid="column-lineage-header" style={mutedStyle}>
        <span style={{ fontWeight: 600 }}>{current.target_column}</span> at{" "}
        {displayName(
          current.nodes[current.nodes.length - 1] ?? {
            node_id: current.target_node_id,
            node_type: "node",
            label: null,
            column: current.target_column,
            role: "unknown",
          },
        )}
      </div>
      <div data-testid="column-lineage-steps" style={{ marginTop: "0.5rem" }}>
        {current.nodes.map((n, i) => (
          <div key={`${n.node_id}-${n.column}-${i}`} data-testid="column-lineage-step">
            <span>{displayName(n)}</span>
            <span style={mutedStyle}> · {n.column}</span>
            {n.source_column && n.source_column !== n.column ? (
              <>
                <span style={mutedStyle}> ⇠ {n.source_column}</span>
              </>
            ) : null}
            <span style={mutedStyle}>[{n.role}]</span>
            {n.detail ? (
              <span style={{ ...mutedStyle, marginLeft: "0.25rem" }}>({n.detail})</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

export default ColumnLineagePanel;
