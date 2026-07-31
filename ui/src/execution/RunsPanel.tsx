import { useEffect, useState, type JSX } from "react";

import { useRunsStore } from "./runsStore";
import { useGraphStore } from "../store/graphStore";
import { useFlowStore } from "../io/flowStore";
import { getRunGraph } from "./runsClient";
import { computeRunGraphDiff } from "./runCompare";
import type { Graph } from "../generated/ir";
import "./RunsPanel.css";

export interface RunsPanelProps {
  onClose: () => void;
}

export function RunsPanel({ onClose }: RunsPanelProps): JSX.Element {
  const runs = useRunsStore((s) => s.runs);
  const selectedRunId = useRunsStore((s) => s.selectedRunId);
  const selectedRunDetail = useRunsStore((s) => s.selectedRunDetail);
  const compareRunId = useRunsStore((s) => s.compareRunId);
  const compareRunDetail = useRunsStore((s) => s.compareRunDetail);
  const loading = useRunsStore((s) => s.loading);
  const error = useRunsStore((s) => s.error);
  const fetchRuns = useRunsStore((s) => s.fetchRuns);
  const selectRun = useRunsStore((s) => s.selectRun);
  const selectCompareRun = useRunsStore((s) => s.selectCompareRun);
  const deleteRun = useRunsStore((s) => s.deleteRun);

  const [restoreConfirm, setRestoreConfirm] = useState<string | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [graphDiff, setGraphDiff] = useState<ReturnType<typeof computeRunGraphDiff> | null>(null);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  useEffect(() => {
    if (!selectedRunDetail || !compareRunDetail) {
      setGraphDiff(null);
      return;
    }
    const detailA = selectedRunDetail;
    const detailB = compareRunDetail;
    async function loadAndDiff() {
      try {
        const [graphA, graphB] = await Promise.all([
          getRunGraph(detailA.run_id),
          getRunGraph(detailB.run_id),
        ]);
        setGraphDiff(computeRunGraphDiff(graphA, graphB));
      } catch {
        // ignore
      }
    }
    loadAndDiff();
  }, [selectedRunDetail, compareRunDetail]);

  async function doRestore(runId: string): Promise<void> {
    setRestoreConfirm(null);
    setRestoreError(null);
    try {
      const graph = await getRunGraph(runId);
      useGraphStore.getState().loadIR(graph as Graph);
      useFlowStore.getState().setDirty(false);
      onClose();
    } catch (err) {
      setRestoreError(err instanceof Error ? err.message : String(err));
    }
  }

  function handleRestoreClick(runId: string): void {
    const isDirty = useFlowStore.getState().isDirty;
    if (isDirty) {
      setRestoreConfirm(runId);
    } else {
      doRestore(runId);
    }
  }

  async function handleDelete(runId: string): Promise<void> {
    await deleteRun(runId);
  }

  function formatTimestamp(ts: number): string {
    return new Date(ts * 1000).toLocaleString();
  }

  function formatDuration(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  return (
    <div className="ef-runs-panel" data-testid="runs-panel">
      <div className="ef-runs-panel__header">
        <h2>Run History</h2>
        <button type="button" onClick={onClose} className="ef-runs-panel__close" data-testid="runs-panel-close">Close</button>
      </div>

      {error && <p className="ef-runs-panel__error" data-testid="runs-panel-error">{error}</p>}
      {restoreError && <p className="ef-runs-panel__error" data-testid="restore-error">{restoreError}</p>}

      {loading && runs.length === 0 && <p className="ef-runs-panel__loading" data-testid="runs-panel-loading">Loading...</p>}

      {!loading && runs.length === 0 && !error && (
        <p className="ef-runs-panel__empty" data-testid="runs-panel-empty">No runs yet</p>
      )}

      {restoreConfirm !== null && (
        <div className="ef-runs-panel__confirm" data-testid="restore-confirm">
          <p>You have unsaved changes. Restoring will replace the current graph. Continue?</p>
          <button type="button" onClick={() => doRestore(restoreConfirm)}>Yes, restore</button>
          <button type="button" onClick={() => setRestoreConfirm(null)}>Cancel</button>
        </div>
      )}

      <div className="ef-runs-panel__list" data-testid="runs-panel-list">
        {runs.map((run) => (
          <div
            key={run.run_id}
            className={`ef-runs-panel__entry ${selectedRunId === run.run_id ? "ef-runs-panel__entry--selected" : ""}`}
            data-testid={`run-entry-${run.run_id}`}
          >
            <div className="ef-runs-panel__entry-main" onClick={() => selectRun(run.run_id)}>
              <span className="ef-runs-panel__timestamp">{formatTimestamp(run.timestamp)}</span>
              <span className="ef-runs-panel__summary">
                {run.node_count} nodes &middot; {formatDuration(run.duration_ms)}
              </span>
              {run.tag && <span className="ef-runs-panel__tag">{run.tag}</span>}
              {run.graph_name && <span className="ef-runs-panel__graph-name">{run.graph_name}</span>}
            </div>
            <div className="ef-runs-panel__entry-actions">
              <label className="ef-runs-panel__compare-label">
                <input
                  type="checkbox"
                  checked={compareRunId === run.run_id}
                  onChange={() => selectCompareRun(compareRunId === run.run_id ? null : run.run_id)}
                  data-testid={`compare-checkbox-${run.run_id}`}
                />
                Compare
              </label>
              <button type="button" onClick={() => handleRestoreClick(run.run_id)} className="ef-runs-panel__restore-btn" data-testid={`restore-btn-${run.run_id}`}>Restore</button>
              <button type="button" onClick={() => handleDelete(run.run_id)} className="ef-runs-panel__delete-btn" data-testid={`delete-btn-${run.run_id}`}>Delete</button>
            </div>
          </div>
        ))}
      </div>

      {selectedRunDetail && (
        <div className="ef-runs-panel__detail" data-testid="runs-panel-detail">
          <h3>Run Details</h3>
          <p>Run ID: {selectedRunDetail.run_id}</p>
          <p>Started: {formatTimestamp(selectedRunDetail.started_at)}</p>
          <p>Duration: {formatDuration(selectedRunDetail.duration_ms)}</p>
          <p>Nodes: {selectedRunDetail.node_count}</p>
          <p>SDK Version: {selectedRunDetail.sdk_version}</p>
          <h4>Node Statuses</h4>
          <ul>
            {Object.entries(selectedRunDetail.statuses).map(([nodeId, status]) => (
              <li key={nodeId}>
                {nodeId}: {status.status}{status.elapsed_ms !== undefined ? ` (${status.elapsed_ms}ms)` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      {compareRunId && compareRunDetail && selectedRunDetail && (
        <div className="ef-runs-panel__compare" data-testid="runs-panel-compare">
          <h3>Comparison: Run A vs Run B</h3>
          <table className="ef-runs-panel__compare-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Run A ({selectedRunDetail.run_id.slice(0, 8)})</th>
                <th>Run B ({compareRunDetail.run_id.slice(0, 8)})</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Duration</td>
                <td>{formatDuration(selectedRunDetail.duration_ms)}</td>
                <td>{formatDuration(compareRunDetail.duration_ms)}</td>
              </tr>
              <tr>
                <td>Node count</td>
                <td>{selectedRunDetail.node_count}</td>
                <td>{compareRunDetail.node_count}</td>
              </tr>
              <tr>
                <td>Graph hash</td>
                <td>{selectedRunDetail.graph_hash.slice(0, 12)}</td>
                <td>{compareRunDetail.graph_hash.slice(0, 12)}</td>
              </tr>
            </tbody>
          </table>
          {graphDiff && (
            <div className="ef-runs-panel__graph-diff" data-testid="runs-panel-graph-diff">
              <h4>Graph Changes</h4>
              {graphDiff.added.length > 0 && (
                <p>Added nodes: {graphDiff.added.map((n) => n.id).join(", ")}</p>
              )}
              {graphDiff.removed.length > 0 && (
                <p>Removed nodes: {graphDiff.removed.map((n) => n.id).join(", ")}</p>
              )}
              {graphDiff.modified.length > 0 && (
                <p>Modified nodes: {graphDiff.modified.map((n) => n.id).join(", ")}</p>
              )}
              {graphDiff.addedEdges.length > 0 && (
                <p>Added edges: {graphDiff.addedEdges.length}</p>
              )}
              {graphDiff.removedEdges.length > 0 && (
                <p>Removed edges: {graphDiff.removedEdges.length}</p>
              )}
              {graphDiff.added.length === 0 && graphDiff.removed.length === 0 && graphDiff.modified.length === 0 && (
                <p>No structural changes between runs</p>
              )}
            </div>
          )}
          <p>Graph diffs: {selectedRunDetail.graph_hash === compareRunDetail.graph_hash ? "Identical graphs" : "Different graphs"}</p>
        </div>
      )}
    </div>
  );
}