import { useMemo } from "react";

import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import type { Payload } from "../store/execution";

/**
 * Given a node ID, walk edges backward to find upstream nodes that have
 * executed and produced table results. Return a deduplicated, sorted list
 * of column names from those upstream table payloads.
 */
export function useUpstreamColumns(nodeId: string): string[] {
  const edges = useGraphStore((s) => s.edges);
  const results = useExecutionStore((s) => s.results);

  return useMemo(() => {
    // Find all upstream node IDs by following edges whose target is one of
    // the current node's IN ports.
    const upstreamNodeIds = new Set<string>();
    for (const edge of Object.values(edges)) {
      if (edge.target.node_id === nodeId) {
        upstreamNodeIds.add(edge.source.node_id);
      }
    }

    // Collect columns from upstream execution results
    const columns = new Set<string>();
    for (const upId of upstreamNodeIds) {
      const nodeResults = results[upId];
      if (!nodeResults) continue;
      for (const payload of Object.values(nodeResults) as Payload[]) {
        if (payload.kind === "table") {
          for (const col of payload.columns) {
            columns.add(col);
          }
        }
      }
    }

    return [...columns].sort();
  }, [nodeId, edges, results]);
}

/**
 * Like `useUpstreamColumns`, but scoped to exactly one of this node's IN
 * ports by name (e.g. "left" vs "right" on a `clean.merge` node) instead of
 * flattening columns from every connected upstream port together. Returns
 * an empty list if the node has no such IN port or nothing is connected to
 * it yet.
 */
export function useUpstreamColumnsForPort(nodeId: string, portName: string): string[] {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const results = useExecutionStore((s) => s.results);

  return useMemo(() => {
    const node = nodes[nodeId];
    const port = node?.ports.find((p) => p.name === portName && p.direction === "in");
    if (!port) {
      return [];
    }

    const upstreamNodeIds = new Set<string>();
    for (const edge of Object.values(edges)) {
      if (edge.target.node_id === nodeId && edge.target.port_id === port.id) {
        upstreamNodeIds.add(edge.source.node_id);
      }
    }

    const columns = new Set<string>();
    for (const upId of upstreamNodeIds) {
      const nodeResults = results[upId];
      if (!nodeResults) continue;
      for (const payload of Object.values(nodeResults) as Payload[]) {
        if (payload.kind === "table") {
          for (const col of payload.columns) {
            columns.add(col);
          }
        }
      }
    }

    return [...columns].sort();
  }, [nodeId, portName, nodes, edges, results]);
}
