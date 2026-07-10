// Right-side Inspector dock (Epic 5 Story 4): a tabbed panel with Config, Code, and Results
// tabs. Renders the Config form for the single selected node (or an empty-state prompt), the
// Code tab's live-compiled output, and the Results tab's last execution output for the selected
// node; selection is read from `selectionStore`, never the IR.

import { Maximize2 } from "lucide-react";
import { useState } from "react";

import { useCatalog } from "../catalog/useCatalog";
import { ConsultAffordance } from "../session/ConsultAffordance";
import { familyMeta } from "../theme/family";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { selectedNodeId, useSelectionStore } from "../store/selectionStore";
import { IconButton } from "../ui/IconButton";
import { OverlayModal } from "../ui/OverlayModal";
import { Segmented } from "../ui/Segmented";
import { CodePanel } from "./CodePanel";
import { ConfigForm } from "./ConfigForm";
import { PayloadView } from "./PayloadView";

type InspectorTab = "config" | "code" | "results";

function formatAgo(ms: number): string {
  const secs = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  return `${Math.round(mins / 60)}h ago`;
}

export function Inspector(): JSX.Element {
  const [tab, setTab] = useState<InspectorTab>("config");
  const [resultsExpanded, setResultsExpanded] = useState(false);
  const selNodes = useSelectionStore((s) => s.nodes);
  const nodes = useGraphStore((s) => s.nodes);
  const nodeId = selectedNodeId({ nodes: selNodes });
  const node = nodeId ? nodes[nodeId] : null;
  const catalog = useCatalog();
  const spec = node
    ? catalog.nodes.find((n) => n.type === node.type)
    : undefined;
  const meta = familyMeta(spec?.family ?? "");
  const FamIcon = meta.Icon;

  const results = useExecutionStore((s) => s.results);
  const statuses = useExecutionStore((s) => s.statuses);
  const lastRunAt = useExecutionStore((s) => s.lastRunAt);

  function renderResults(): JSX.Element {
    if (!nodeId) {
      return (
        <p
          data-testid="results-empty-no-selection"
          style={{ color: "var(--text-secondary)" }}
        >
          Select a node to see its results.
        </p>
      );
    }
    const status = statuses[nodeId];
    if (status?.status === "error") {
      return (
        <div
          data-testid="results-error"
          style={{ color: "var(--danger)", whiteSpace: "pre-wrap" }}
        >
          {status.error ?? "Execution failed."}
        </div>
      );
    }
    const nodeResults = results[nodeId];
    if (!nodeResults || Object.keys(nodeResults).length === 0) {
      return (
        <p
          data-testid="results-empty-no-run"
          style={{ color: "var(--text-secondary)" }}
        >
          {lastRunAt !== null
            ? "No inspectable outputs for this node."
            : "No results — run the graph first."}
        </p>
      );
    }
    return (
      <div data-testid="results-list">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          {lastRunAt !== null ? (
            <div
              data-testid="results-last-run"
              style={{
                color: "var(--text-secondary)",
                fontSize: 11,
              }}
            >
              last run: {formatAgo(lastRunAt)}
            </div>
          ) : (
            <div />
          )}
          <IconButton
            aria-label="Expand results"
            data-testid="results-expand-btn"
            onClick={() => setResultsExpanded(true)}
          >
            <Maximize2 size={14} />
          </IconButton>
        </div>
        {Object.entries(nodeResults).map(([portName, payload]) => (
          <div key={portName} style={{ marginBottom: "0.5rem" }}>
            <span style={{ fontWeight: 600 }}>{portName}</span>
            <PayloadView payload={payload} />
          </div>
        ))}
        {resultsExpanded ? (
          <OverlayModal width={720} onClose={() => setResultsExpanded(false)}>
            <h2
              style={{
                margin: "0 0 var(--space-3)",
                fontSize: "var(--text-lg)",
                fontWeight: 600,
              }}
            >
              Results — {node?.label ?? nodeId}
            </h2>
            {lastRunAt !== null ? (
              <div
                style={{
                  color: "var(--text-secondary)",
                  fontSize: 11,
                  marginBottom: "0.5rem",
                }}
              >
                last run: {formatAgo(lastRunAt)}
              </div>
            ) : null}
            {Object.entries(nodeResults).map(([portName, payload]) => (
              <div key={portName} style={{ marginBottom: "0.75rem" }}>
                <span style={{ fontWeight: 600 }}>{portName}</span>
                <PayloadView payload={payload} />
              </div>
            ))}
          </OverlayModal>
        ) : null}
      </div>
    );
  }

  return (
    <aside
      data-testid="inspector"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
      }}
    >
      {node ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "var(--space-2)",
            padding: "var(--space-2) var(--space-3)",
            marginBottom: "var(--space-2)",
            background: meta.soft,
            borderLeft: `3px solid ${meta.color}`,
            fontWeight: 600,
            color: "var(--text-primary)",
            fontSize: "var(--text-sm)",
          }}
        >
          <FamIcon size={16} style={{ color: meta.color, flexShrink: 0 }} />
          <span>{spec?.label ?? node.type}</span>
          {spec?.advisor_persona ? (
            <ConsultAffordance
              nodeId={node.id}
              personaSlug={spec.advisor_persona}
            />
          ) : null}
        </div>
      ) : null}
      <div style={{ padding: "var(--space-2) var(--space-3)" }}>
        <Segmented
          options={[
            {
              value: "config",
              label: "Config",
              testId: "inspector-tab-config",
            },
            { value: "code", label: "Code", testId: "inspector-tab-code" },
            {
              value: "results",
              label: "Results",
              testId: "inspector-tab-results",
            },
          ]}
          value={tab}
          onChange={setTab}
          aria-label="Inspector tabs"
        />
      </div>
      <div
        style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "0.5rem" }}
      >
        {tab === "config" ? (
          node ? (
            <ConfigForm node={node} />
          ) : (
            <p
              data-testid="inspector-empty"
              style={{ color: "var(--text-secondary)" }}
            >
              Select a node to edit its parameters.
            </p>
          )
        ) : tab === "code" ? (
          <CodePanel />
        ) : (
          renderResults()
        )}
      </div>
    </aside>
  );
}
