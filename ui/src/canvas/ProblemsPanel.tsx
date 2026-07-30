// Problems panel: lists validation diagnostics and failed execution nodes.
// Click a row to navigate to the node on the canvas.

import { AlertCircle, AlertTriangle, XCircle, type LucideIcon } from "lucide-react";
import { useState, useMemo, type JSX } from "react";

import { useExecutionStore } from "../store/executionStore";
import { useValidationStore } from "../store/validationStore";
import { severityColor } from "../store/validation";

export interface ProblemsPanelProps {
  onNavigate: (nodeId: string) => void;
}

interface ProblemRow {
  id: string;
  nodeId: string | null;
  message: string;
  severity: "error" | "warning" | "info" | "execution-error";
}

export function ProblemsPanel({ onNavigate }: ProblemsPanelProps): JSX.Element {
  const diagnostics = useValidationStore((s) => s.diagnostics);
  const statuses = useExecutionStore((s) => s.statuses);

  const problems = useMemo(() => {
    const rows: ProblemRow[] = [];

    for (const d of diagnostics) {
      rows.push({
        id: `diag-${d.code}-${d.node_id ?? ""}-${d.edge_id ?? ""}`,
        nodeId: d.node_id ?? null,
        message: d.message,
        severity: d.severity,
      });
    }

    for (const [nodeId, status] of Object.entries(statuses)) {
      if (status.status === "error") {
        rows.push({
          id: `exec-${nodeId}`,
          nodeId,
          message: status.error ?? "Execution failed",
          severity: "execution-error",
        });
      }
    }

    return rows;
  }, [diagnostics, statuses]);

  const [collapsed, setCollapsed] = useState(false);

  const errorCount = problems.filter((p) => p.severity === "error" || p.severity === "execution-error").length;
  const warningCount = problems.filter((p) => p.severity === "warning").length;

  if (problems.length === 0) {
    return <></>;
  }

  return (
    <div
      className="glass"
      style={{
        position: "absolute",
        bottom: "var(--space-4)",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 10,
        width: 480,
        maxHeight: collapsed ? "auto" : 240,
        display: "flex",
        flexDirection: "column",
        fontSize: "var(--text-xs)",
      }}
    >
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          padding: "var(--space-2) var(--space-3)",
          border: "none",
          background: "none",
          cursor: "pointer",
          color: "var(--text-primary)",
          font: "inherit",
          fontSize: "var(--text-xs)",
          fontWeight: 600,
          textAlign: "left",
          borderBottom: collapsed ? "none" : "1px solid var(--border-subtle)",
        }}
        data-testid="problems-panel-toggle"
      >
        <span>{collapsed ? "▸" : "▾"}</span>
        <span>Problems</span>
        {errorCount > 0 && (
          <span style={{ color: "var(--danger)", fontWeight: 600 }}>
            {errorCount} {errorCount === 1 ? "error" : "errors"}
          </span>
        )}
        {warningCount > 0 && (
          <span style={{ color: "var(--warning)", fontWeight: 600 }}>
            {warningCount} {warningCount === 1 ? "warning" : "warnings"}
          </span>
        )}
        {problems.length > 0 && (
          <span style={{ color: "var(--text-tertiary)", marginLeft: "auto" }}>
            {problems.length} total
          </span>
        )}
      </button>
      {!collapsed && (
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
          {problems.map((problem) => {
            const color =
              problem.severity === "execution-error"
                ? "var(--danger)"
                : severityColor(problem.severity);
            const Icon: LucideIcon =
              problem.severity === "error" || problem.severity === "execution-error"
                ? XCircle
                : problem.severity === "warning"
                  ? AlertTriangle
                  : AlertCircle;

            const isClickable = problem.nodeId !== null;

            return (
              <div
                key={problem.id}
                onClick={() => {
                  if (isClickable) onNavigate(problem.nodeId!);
                }}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "var(--space-2)",
                  padding: "var(--space-2) var(--space-3)",
                  borderBottom: "1px solid var(--border-subtle)",
                  cursor: isClickable ? "pointer" : "default",
                }}
                data-testid={`problem-row-${problem.severity}`}
              >
                <Icon size={12} style={{ color, flexShrink: 0, marginTop: 2 }} />
                <span style={{ color: "var(--text-primary)", lineHeight: 1.4 }}>
                  {problem.message}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
