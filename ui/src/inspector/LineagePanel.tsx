// Inspector's Lineage tab: on demand, POSTs the current graph plus the selected node id to the
// local server's `/lineage` route and renders the returned source -> transform -> artifact
// chain behind that node. Lineage is NOT a node OUT-port payload -- it is computed fresh on
// every request from the graph shape and is never stored on the IR or in the store (Epic 16,
// Story 17/23), so selecting a different node (or editing the graph) always re-traces.

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import { useGraphStore } from "../store/graphStore";

interface LineageNodeDTO {
  node_id: string;
  node_type: string;
  label: string | null;
}

interface LineageEdgeDTO {
  source_node_id: string;
  source_port: string;
  target_node_id: string;
  target_port: string;
}

interface LineageDTO {
  target_node_id: string;
  nodes: LineageNodeDTO[];
  edges: LineageEdgeDTO[];
}

const mutedStyle: CSSProperties = { color: "var(--text-secondary)" };

function isLineageNodeDTO(value: unknown): value is LineageNodeDTO {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  if (!("node_id" in value)) {
    return false;
  }
  if (!("node_type" in value)) {
    return false;
  }
  if (!("label" in value)) {
    return false;
  }
  return (
    typeof value.node_id === "string" &&
    typeof value.node_type === "string" &&
    (value.label === null || typeof value.label === "string")
  );
}

function isLineageEdgeDTO(value: unknown): value is LineageEdgeDTO {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  if (!("source_node_id" in value)) {
    return false;
  }
  if (!("source_port" in value)) {
    return false;
  }
  if (!("target_node_id" in value)) {
    return false;
  }
  if (!("target_port" in value)) {
    return false;
  }
  return (
    typeof value.source_node_id === "string" &&
    typeof value.source_port === "string" &&
    typeof value.target_node_id === "string" &&
    typeof value.target_port === "string"
  );
}

function isLineageDTO(value: unknown): value is LineageDTO {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  if (!("target_node_id" in value)) {
    return false;
  }
  if (!("nodes" in value)) {
    return false;
  }
  if (!("edges" in value)) {
    return false;
  }
  return (
    typeof value.target_node_id === "string" &&
    Array.isArray(value.nodes) &&
    value.nodes.every(isLineageNodeDTO) &&
    Array.isArray(value.edges) &&
    value.edges.every(isLineageEdgeDTO)
  );
}

interface LineagePanelProps {
  nodeId: string | null;
  debounceMs?: number;
}

export function LineagePanel({
  nodeId,
  debounceMs = 400,
}: LineagePanelProps): JSX.Element {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const [lineage, setLineage] = useState<LineageDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (nodeId === null) {
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
          const res = await fetch("/lineage", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ graph, node_id: nodeId }),
          });
          const body = await res.json();
          if (cancelled) {
            return;
          }
          if (!res.ok || body.error) {
            setError(body.error ?? `Server error ${res.status}`);
            setLineage(null);
          } else if (isLineageDTO(body.lineage)) {
            setLineage(body.lineage);
            setError(null);
          } else {
            setError("Malformed lineage response from server.");
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
  }, [nodes, edges, nodeId, debounceMs]);

  if (nodeId === null) {
    return (
      <p data-testid="lineage-empty-no-selection" style={mutedStyle}>
        Select a node to trace its lineage.
      </p>
    );
  }

  if (Object.keys(nodes).length === 0) {
    return (
      <p data-testid="lineage-empty" style={mutedStyle}>
        Add nodes to trace lineage.
      </p>
    );
  }

  if (error) {
    return (
      <div
        data-testid="lineage-error"
        style={{ color: "var(--danger)", whiteSpace: "pre-wrap" }}
      >
        {error}
      </div>
    );
  }

  if (lineage === null) {
    // Covers both "the debounced fetch is in flight" and "the very first render, before the
    // effect has fired" -- the message is the same either way, and returning early is what
    // keeps the chain render below free of a null check.
    return (
      <p data-testid="lineage-loading" style={mutedStyle}>
        Tracing lineage…
      </p>
    );
  }

  const currentLineage = lineage;

  const hopFor = (fromId: string, toId: string): LineageEdgeDTO | undefined =>
    currentLineage.edges.find(
      (edge) => edge.source_node_id === fromId && edge.target_node_id === toId,
    );

  return (
    <div>
      <div data-testid="lineage-summary" style={mutedStyle}>
        {currentLineage.nodes.length} nodes · {currentLineage.edges.length} edges
      </div>
      <ol data-testid="lineage-chain">
        {currentLineage.nodes.map((node, i) => {
          const isTarget = node.node_id === currentLineage.target_node_id;
          const displayName =
            node.label !== null && node.label !== "" ? node.label : node.node_type;
          const prev = i > 0 ? currentLineage.nodes[i - 1] : null;
          const hop = prev ? hopFor(prev.node_id, node.node_id) : undefined;
          return (
            <li
              key={node.node_id}
              data-testid={isTarget ? "lineage-target" : "lineage-node"}
              style={isTarget ? { fontWeight: 600 } : undefined}
            >
              {hop ? (
                <div data-testid="lineage-hop" style={mutedStyle}>
                  {hop.source_port} → {hop.target_port}
                </div>
              ) : null}
              <div>
                {displayName}
                {isTarget ? " (target)" : null}
              </div>
              <div style={mutedStyle}>
                {node.node_type} · {node.node_id}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
