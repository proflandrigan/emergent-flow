// Reach / route trace helpers: given visible node ids and edges, compute the
// transitive closure of nodes reachable downstream and/or upstream of a set of
// roots (reach), or every node/edge lying on a directed path between two nodes
// (route), or every node of selected families (lens), plus the edges connecting the highlighted
// nodes.
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
  /** Node ids in the trace: the selected roots PLUS every node reachable from them. */
  highlightedNodeIds: Set<string>;
  /** Edge ids whose BOTH endpoints are in highlightedNodeIds. */
  highlightedEdgeIds: Set<string>;
}

export type TraceDirection = "downstream" | "upstream" | "both";

/**
 * Build an adjacency map over the visible edges. Edges referencing ids not in `nodeIdSet` are
 * ignored. Forward (`reverse` false): source -> targets. Reverse: target -> sources.
 */
function buildAdjacency(
  nodeIdSet: Set<string>,
  edges: TraceEdge[],
  reverse: boolean,
): Map<string, string[]> {
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    if (!nodeIdSet.has(edge.source) || !nodeIdSet.has(edge.target)) {
      continue;
    }
    const from = reverse ? edge.target : edge.source;
    const to = reverse ? edge.source : edge.target;
    const neighbours = adjacency.get(from);
    if (neighbours) {
      neighbours.push(to);
    } else {
      adjacency.set(from, [to]);
    }
  }
  return adjacency;
}

/**
 * Transitive closure from `seeds` over `adjacency`, INCLUDING the seeds themselves. Seeds not in
 * `nodeIdSet` are skipped. Worklist-based and cycle-safe.
 */
function closure(
  seeds: string[],
  nodeIdSet: Set<string>,
  adjacency: Map<string, string[]>,
): Set<string> {
  const seen = new Set<string>();
  const worklist: string[] = [];
  for (const id of seeds) {
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
    const neighbours = adjacency.get(current);
    if (neighbours) {
      for (const next of neighbours) {
        if (!seen.has(next)) {
          seen.add(next);
          worklist.push(next);
        }
      }
    }
  }
  return seen;
}

/**
 * Compute the reach of the given root node ids in the given direction.
 *
 * `rootIds`: ids of the root nodes. Must be the *visible* node set (collapsed-group members
 *   already removed, edges re-anchored) -- this helper does not resolve groups.
 * `nodeIds`: every visible node id in the graph.
 * `edges`: every visible edge, with `source`/`target` already resolved to visible node ids.
 * `direction`: `downstream` follows source -> target, `upstream` follows target -> source, and
 *   `both` is the union of the separately computed downstream and upstream closures (NOT an
 *   undirected walk, which would wrongly pull in siblings).
 *
 * Roots are included in the result; roots not in `nodeIds` are skipped but still make the result
 * `active`.
 *
 * Edge membership: for `downstream`/`upstream`, an edge is highlighted iff BOTH endpoints are
 * highlighted. For `both`, an edge is highlighted iff both endpoints are in the downstream closure
 * OR both are in the upstream closure.
 *
 * When `rootIds` is empty, return `{ active: false, highlightedNodeIds: new Set(),
 * highlightedEdgeIds: new Set() }`.
 */
export function computeReach(
  rootIds: string[],
  nodeIds: string[],
  edges: TraceEdge[],
  direction: TraceDirection,
): TraceResult {
  const highlightedNodeIds = new Set<string>();
  const highlightedEdgeIds = new Set<string>();

  if (rootIds.length === 0) {
    return { active: false, highlightedNodeIds, highlightedEdgeIds };
  }

  const nodeIdSet = new Set(nodeIds);
  const closures: Set<string>[] = [];
  if (direction === "downstream" || direction === "both") {
    closures.push(closure(rootIds, nodeIdSet, buildAdjacency(nodeIdSet, edges, false)));
  }
  if (direction === "upstream" || direction === "both") {
    closures.push(closure(rootIds, nodeIdSet, buildAdjacency(nodeIdSet, edges, true)));
  }

  for (const set of closures) {
    for (const id of set) {
      highlightedNodeIds.add(id);
    }
  }

  for (const edge of edges) {
    for (const set of closures) {
      if (set.has(edge.source) && set.has(edge.target)) {
        highlightedEdgeIds.add(edge.id);
        break;
      }
    }
  }

  return { active: true, highlightedNodeIds, highlightedEdgeIds };
}

/**
 * Compute the downstream trace for the currently selected node ids. Thin wrapper over
 * {@link computeReach} with direction `downstream`: the transitive closure over directed edges
 * (source -> target) from each selected id, plus every edge whose both endpoints are in it.
 * Empty `selectedNodeIds` yields an inactive, empty result.
 */
export function computeTrace(
  selectedNodeIds: string[],
  nodeIds: string[],
  edges: TraceEdge[],
): TraceResult {
  return computeReach(selectedNodeIds, nodeIds, edges, "downstream");
}

export interface RouteResult extends TraceResult {
  /** False when `toId` is not reachable from `fromId` (or either id is not a visible node). */
  found: boolean;
}

/**
 * Compute the route from `fromId` to `toId`: every node and edge lying on ANY directed path
 * between them (the intersection of the downstream closure of `fromId` and the upstream closure
 * of `toId`), NOT just the shortest path. Derived purely from the edge graph, never inferred from
 * node geometry/positions.
 *
 * `active` is always true (a route was requested); callers use `found` to show a "no path" state.
 * If either id is not in `nodeIds`, or `toId` is unreachable from `fromId`, `found` is false and
 * the sets are empty. If `fromId === toId`, the route is that single node with no edges
 * (self-loops are not highlighted).
 *
 * Edge membership: an edge is highlighted iff BOTH endpoints are on-route nodes.
 */
export function computeRoute(
  fromId: string,
  toId: string,
  nodeIds: string[],
  edges: TraceEdge[],
): RouteResult {
  const highlightedNodeIds = new Set<string>();
  const highlightedEdgeIds = new Set<string>();
  const notFound: RouteResult = {
    active: true,
    found: false,
    highlightedNodeIds,
    highlightedEdgeIds,
  };

  const nodeIdSet = new Set(nodeIds);
  if (!nodeIdSet.has(fromId) || !nodeIdSet.has(toId)) {
    return notFound;
  }

  if (fromId === toId) {
    highlightedNodeIds.add(fromId);
    return { active: true, found: true, highlightedNodeIds, highlightedEdgeIds };
  }

  const down = closure([fromId], nodeIdSet, buildAdjacency(nodeIdSet, edges, false));
  if (!down.has(toId)) {
    return notFound;
  }
  const up = closure([toId], nodeIdSet, buildAdjacency(nodeIdSet, edges, true));

  for (const id of down) {
    if (up.has(id)) {
      highlightedNodeIds.add(id);
    }
  }

  for (const edge of edges) {
    if (highlightedNodeIds.has(edge.source) && highlightedNodeIds.has(edge.target)) {
      highlightedEdgeIds.add(edge.id);
    }
  }

  return { active: true, found: true, highlightedNodeIds, highlightedEdgeIds };
}

export interface LensNode {
  id: string;
  /** Catalog family of the node (e.g. "ml", "clean"); null for non-catalog nodes (notes, groups). */
  family: string | null;
}

/**
 * Family lens: highlight every visible node whose `family` is in `families`, plus every edge whose
 * BOTH endpoints are highlighted. Purely a highlight -- never moves or hides nodes.
 * `active` is false when `families` is empty (lens off).
 */
export function computeLens(
  families: Set<string>,
  nodes: LensNode[],
  edges: TraceEdge[],
): TraceResult {
  const highlightedNodeIds = new Set<string>();
  const highlightedEdgeIds = new Set<string>();

  if (families.size === 0) {
    return { active: false, highlightedNodeIds, highlightedEdgeIds };
  }

  for (const node of nodes) {
    if (node.family !== null && families.has(node.family)) {
      highlightedNodeIds.add(node.id);
    }
  }

  for (const edge of edges) {
    if (highlightedNodeIds.has(edge.source) && highlightedNodeIds.has(edge.target)) {
      highlightedEdgeIds.add(edge.id);
    }
  }

  return { active: true, highlightedNodeIds, highlightedEdgeIds };
}
