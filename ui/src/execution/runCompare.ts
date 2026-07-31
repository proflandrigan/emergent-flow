export interface RunMetricDiff {
  nodeId: string;
  portName: string;
  runAValue: string | number | boolean | null;
  runBValue: string | number | boolean | null;
}

export function computeRunGraphDiff(
  graphA: Record<string, unknown>,
  graphB: Record<string, unknown>,
): {
  added: { id: string; [key: string]: unknown }[];
  removed: { id: string; [key: string]: unknown }[];
  modified: { id: string; [key: string]: unknown }[];
  addedEdges: { id: string; [key: string]: unknown }[];
  removedEdges: { id: string; [key: string]: unknown }[];
} {
  const nodesA = (graphA.nodes as Record<string, unknown>) ?? {};
  const nodesB = (graphB.nodes as Record<string, unknown>) ?? {};
  const edgesA = (graphA.edges as Record<string, unknown>) ?? {};
  const edgesB = (graphB.edges as Record<string, unknown>) ?? {};

  const added: { id: string; [key: string]: unknown }[] = [];
  const removed: { id: string; [key: string]: unknown }[] = [];
  const modified: { id: string; [key: string]: unknown }[] = [];
  const addedEdges: { id: string; [key: string]: unknown }[] = [];
  const removedEdges: { id: string; [key: string]: unknown }[] = [];

  const nodeIdsA = new Set(Object.keys(nodesA));
  const nodeIdsB = new Set(Object.keys(nodesB));

  for (const id of nodeIdsB) {
    if (!nodeIdsA.has(id)) {
      added.push({ id: id, ...(nodesB[id] as Record<string, unknown>) });
    }
  }

  for (const id of nodeIdsA) {
    if (!nodeIdsB.has(id)) {
      removed.push({ id: id, ...(nodesA[id] as Record<string, unknown>) });
    } else {
      const nodeA = JSON.stringify(nodesA[id]);
      const nodeB = JSON.stringify(nodesB[id]);
      if (nodeA !== nodeB) {
        modified.push({ id: id, ...(nodesB[id] as Record<string, unknown>) });
      }
    }
  }

  const edgeIdsA = new Set(Object.keys(edgesA));
  const edgeIdsB = new Set(Object.keys(edgesB));

  for (const id of edgeIdsB) {
    if (!edgeIdsA.has(id)) {
      addedEdges.push({ id: id, ...(edgesB[id] as Record<string, unknown>) });
    }
  }
  for (const id of edgeIdsA) {
    if (!edgeIdsB.has(id)) {
      removedEdges.push({ id: id, ...(edgesA[id] as Record<string, unknown>) });
    }
  }

  return { added, removed, modified, addedEdges, removedEdges };
}

export function computeRunMetricDiff(
  detailA: { statuses: Record<string, { status: string; elapsed_ms?: number }> },
  detailB: { statuses: Record<string, { status: string; elapsed_ms?: number }> },
): RunMetricDiff[] {
  const diffs: RunMetricDiff[] = [];
  const allNodeIds = new Set([...Object.keys(detailA.statuses), ...Object.keys(detailB.statuses)]);
  for (const nodeId of allNodeIds) {
    const statusA = detailA.statuses[nodeId];
    const statusB = detailB.statuses[nodeId];
    if (statusA?.elapsed_ms !== statusB?.elapsed_ms) {
      diffs.push({
        nodeId,
        portName: "elapsed_ms",
        runAValue: statusA?.elapsed_ms ?? null,
        runBValue: statusB?.elapsed_ms ?? null,
      });
    }
  }
  return diffs;
}