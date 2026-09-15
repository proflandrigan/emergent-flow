// Downstream trace helper: given the currently selected (visible) node ids,
// compute the transitive closure of nodes reachable downstream over the
// visible edge graph, plus every edge whose both endpoints are in that set.
// Pure functions only -- no store/React dependency here so this stays
// trivially unit-testable and reusable from the canvas selection highlight.

export interface TraceEdge {
  id: string;
  source: string;
  target: string;
}

export interface TraceResult {
  /** True when at least one node is selected; callers use this to toggle "dim the rest". */
  active: boolean;
  /** Node ids in the trace: the selected roots PLUS every node reachable downstream of them. */
  highlightedNodeIds: Set<string>;
  /** Edge ids whose BOTH endpoints are in highlightedNodeIds. */
  highlightedEdgeIds: Set<string>;
}

/**
 * Compute the downstream trace for the currently selected node ids.
 *
 * `selectedNodeIds`: ids of the currently-selected (root) nodes. Must be the *visible* node set
 *   (collapsed-group members already removed, edges re-anchored) -- this helper does not resolve
 *   groups.
 * `nodeIds`: every visible node id in the graph.
 * `edges`: every visible edge, with `source`/`target` already resolved to visible node ids.
 *
 * Reachability: transitive closure over directed edges (source -> target), starting from each
 * selected id, INCLUDING the selected ids themselves. Deterministic: worklist/DFS, the returned
 * Sets' contents are deterministic regardless of iteration order.
 *
 * Edge membership: an edge id is highlighted iff BOTH its source and its target node ids are in
 * `highlightedNodeIds`.
 *
 * When `selectedNodeIds` is empty, return `{ active: false, highlightedNodeIds: new Set(),
 * highlightedEdgeIds: new Set() }`.
 */
export function computeTrace(
  selectedNodeIds: string[],
  nodeIds: string[],
  edges: TraceEdge[],
): TraceResult {
  const highlightedNodeIds = new Set<string>();
  const highlightedEdgeIds = new Set<string>();

  if (selectedNodeIds.length === 0) {
    return { active: false, highlightedNodeIds, highlightedEdgeIds };
  }

  const nodeIdSet = new Set(nodeIds);

  // Forward adjacency: source -> target ids, ignoring edges that reference
  // ids not in the visible node set.
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    if (!nodeIdSet.has(edge.source) || !nodeIdSet.has(edge.target)) {
      continue;
    }
    const targets = adjacency.get(edge.source);
    if (targets) {
      targets.push(edge.target);
    } else {
      adjacency.set(edge.source, [edge.target]);
    }
  }

  // Seed the worklist with the valid selected ids; a selected id that is not
  // in `nodeIds` (e.g. just deleted) is skipped for the closure but still
  // contributes to `active`.
  const seen = new Set<string>();
  const worklist: string[] = [];
  for (const id of selectedNodeIds) {
    if (nodeIdSet.has(id) && !seen.has(id)) {
      seen.add(id);
      worklist.push(id);
    }
  }

  while (worklist.length > 0) {
    const current = worklist.pop();
    if (current === undefined) {
      break;
    }
    highlightedNodeIds.add(current);
    const targets = adjacency.get(current);
    if (targets) {
      for (const target of targets) {
        if (!seen.has(target)) {
          seen.add(target);
          worklist.push(target);
        }
      }
    }
  }

  for (const edge of edges) {
    if (highlightedNodeIds.has(edge.source) && highlightedNodeIds.has(edge.target)) {
      highlightedEdgeIds.add(edge.id);
    }
  }

  return { active: true, highlightedNodeIds, highlightedEdgeIds };
}
