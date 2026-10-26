// Tour step resolver: turns one guided-tour step (a focus set with optional reach, or a route)
// into the highlight the canvas should render, plus which authored ids have since been removed
// from the graph and which rendered nodes the viewport should fit.
// Pure functions only -- no store/React dependency here so this stays trivially unit-testable.
// Builds on the reach/route helpers in ./trace.

import type { TourStep } from "../generated/tour";
import { computeReach, computeRoute, type TraceEdge, type TraceResult } from "./trace";

export interface TourGraphView {
  /** Ids of the nodes actually rendered (collapsed-group members excluded). */
  nodeIds: string[];
  /** Rendered edges (already re-anchored to collapsed groups). */
  edges: TraceEdge[];
  /** True when the id is a node of the graph being toured (rendered or hidden in a collapsed group). */
  hasNode: (id: string) => boolean;
  /** Map an id to the node that represents it on screen (its collapsed group, else itself). */
  visibleId: (id: string) => string;
  /**
   * The top-level graph before re-anchoring to collapsed groups. Route steps decide found/no-path
   * on this so a collapsed group can't fake a path through a sibling member; the result is then
   * projected onto the rendered graph. Omitted => the rendered graph is used as-is.
   */
  graph?: { nodeIds: string[]; edges: TraceEdge[] };
}

export type TourRouteStatus = "found" | "no-path" | "endpoint-removed";

export interface ResolvedTourStep {
  kind: "focus" | "reach" | "route";
  /** Every id the step names, as authored (focus list or [from, to]). */
  authoredIds: string[];
  /** Authored ids no longer in the graph (render a "Node removed" badge for each). */
  removedIds: string[];
  /** The highlight to render; `active` false only when nothing survives. */
  highlight: TraceResult;
  /** Route steps only; null otherwise. */
  routeStatus: TourRouteStatus | null;
  /** Rendered node ids to fit the viewport to (de-duplicated, mapped through visibleId); [] => don't fit. */
  fitIds: string[];
}

function emptyHighlight(): TraceResult {
  return { active: false, highlightedNodeIds: new Set(), highlightedEdgeIds: new Set() };
}

/** De-duplicate a list of ids, preserving first-seen order. */
function unique(ids: string[]): string[] {
  return Array.from(new Set(ids));
}

/**
 * Highlight EXACTLY `ids` (no expansion), plus every edge whose source and target are both in
 * `ids` and differ (self-loops are not highlighted). Inactive when `ids` is empty.
 */
function exactHighlight(ids: string[], edges: TraceEdge[]): TraceResult {
  if (ids.length === 0) {
    return emptyHighlight();
  }
  const highlightedNodeIds = new Set(ids);
  const highlightedEdgeIds = new Set<string>();
  for (const edge of edges) {
    if (
      edge.source !== edge.target &&
      highlightedNodeIds.has(edge.source) &&
      highlightedNodeIds.has(edge.target)
    ) {
      highlightedEdgeIds.add(edge.id);
    }
  }
  return { active: true, highlightedNodeIds, highlightedEdgeIds };
}

/**
 * Resolve a tour step against the rendered graph.
 *
 * - focus only: exactly the focus nodes (mapped through `visibleId`) plus edges between them.
 * - focus + reach: the closure from the focus roots in the requested direction.
 * - route `[from, to]`: directed paths from `from` to `to` only (never retried reversed). Two
 *   present endpoints with no path give `no-path`; a missing endpoint gives `endpoint-removed`.
 *
 * Authored ids deleted from the graph are listed in `removedIds`; surviving ones are still
 * highlighted. Never throws: a step with neither focus nor route resolves to an empty, inactive
 * `focus` result.
 */
export function resolveTourStep(step: TourStep, view: TourGraphView): ResolvedTourStep {
  const rendered = new Set(view.nodeIds);

  /** Visible ids of the surviving (present and rendered) authored ids, de-duplicated. */
  const survivingVisible = (ids: string[]): string[] => {
    const visible: string[] = [];
    for (const id of ids) {
      if (view.hasNode(id)) {
        const shown = view.visibleId(id);
        if (rendered.has(shown)) {
          visible.push(shown);
        }
      }
    }
    return unique(visible);
  };

  if (step.route) {
    const [from, to] = step.route;
    const authoredIds = [from, to];
    const removedIds = unique(authoredIds.filter((id) => !view.hasNode(id)));
    const endpoints = survivingVisible(authoredIds);

    if (removedIds.length > 0) {
      return {
        kind: "route",
        authoredIds,
        removedIds,
        highlight: exactHighlight(endpoints, view.edges),
        routeStatus: "endpoint-removed",
        fitIds: endpoints,
      };
    }

    const graph = view.graph ?? { nodeIds: view.nodeIds, edges: view.edges };
    const route = view.graph
      ? computeRoute(from, to, graph.nodeIds, graph.edges)
      : computeRoute(view.visibleId(from), view.visibleId(to), view.nodeIds, view.edges);
    if (route.found) {
      // Project the path onto the rendered graph: hidden members show as their collapsed group,
      // and edges dropped by re-anchoring (internal to one collapsed group) are not highlighted.
      const renderedEdgeIds = new Set(view.edges.map((e) => e.id));
      return {
        kind: "route",
        authoredIds,
        removedIds,
        highlight: {
          active: route.active,
          highlightedNodeIds: new Set(survivingVisible([...route.highlightedNodeIds])),
          highlightedEdgeIds: new Set(
            [...route.highlightedEdgeIds].filter((id) => renderedEdgeIds.has(id)),
          ),
        },
        routeStatus: "found",
        fitIds: endpoints,
      };
    }
    // No directed path: show just the two endpoints (no edges) so the reader still sees them.
    return {
      kind: "route",
      authoredIds,
      removedIds,
      highlight: {
        active: endpoints.length > 0,
        highlightedNodeIds: new Set(endpoints),
        highlightedEdgeIds: new Set(),
      },
      routeStatus: "no-path",
      fitIds: endpoints,
    };
  }

  const authoredIds = step.focus ?? [];
  const removedIds = unique(authoredIds.filter((id) => !view.hasNode(id)));
  const roots = survivingVisible(authoredIds);
  const reach = step.reach ?? null;

  if (reach) {
    const direction =
      reach === "up" ? "upstream" : reach === "down" ? "downstream" : ("both" as const);
    return {
      kind: "reach",
      authoredIds,
      removedIds,
      highlight: computeReach(roots, view.nodeIds, view.edges, direction),
      routeStatus: null,
      fitIds: roots,
    };
  }

  return {
    kind: "focus",
    authoredIds,
    removedIds,
    highlight: exactHighlight(roots, view.edges),
    routeStatus: null,
    fitIds: roots,
  };
}

/** A view over a plain graph with no collapsed groups (every node rendered, visibleId = identity). */
export function plainTourGraphView(nodeIds: string[], edges: TraceEdge[]): TourGraphView {
  const known = new Set(nodeIds);
  return {
    nodeIds,
    edges,
    hasNode: (id) => known.has(id),
    visibleId: (id) => id,
  };
}
