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
