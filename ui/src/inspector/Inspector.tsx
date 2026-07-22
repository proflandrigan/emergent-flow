// Right-side Inspector dock (Epic 5 Story 4): a tabbed panel with Config, Code, and Results
// tabs. Renders the Config form for the single selected node (or an empty-state prompt), the
// Code tab's live-compiled output, and the Results tab's last execution output for the selected
// node; selection is read from `selectionStore`, never the IR.

import { Maximize2 } from "lucide-react";
import { useEffect, useState } from "react";

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
import { StepsPanel } from "./StepsPanel";

type InspectorTab = "config" | "code" | "results" | "steps";

function formatAgo(ms: number): string {
  const secs = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  return `${Math.round(mins / 60)}h ago`;
}

export function Inspector(): JSX.Element {
  const [tab, setTab] = useState<InspectorTab>("config");
  const [expanded, setExpanded] = useState(false);
  const [highlightVarName, setHighlightVarName] = useState<string | null>(null);
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

  // Close the expanded inspector modal whenever the selected node changes -- otherwise
  // switching to a node with no results unmounts the modal (its content vanishes) but
  // leaves `expanded` true, so re-selecting a node with results snaps the modal
  // back open with no click on the expand button.
  useEffect(() => {
    setExpanded(false);
  }, [nodeId]);

  // Shared between the docked panel and the expanded OverlayModal so the two views can
  // never drift apart (e.g. one gaining the family badge's ConsultAffordance while the
  // other doesn't).
  function renderHeader(): JSX.Element | null {
    if (!node) return null;
    return (
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
    );
  }

  function renderTabs(): JSX.Element {
    return (
      <Segmented
        options={[
          {
            value: "config",
            label: "Config",
            testId: "inspector-tab-config",
          },
          { value: "code", label: "Code", testId: "inspector-tab-code" },
          { value: "steps", label: "Steps", testId: "inspector-tab-steps" },
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
    );
  }

  function renderBody(): JSX.Element {
    if (tab === "config") {
      return node ? (
        <ConfigForm node={node} />
      ) : (
        <p
          data-testid="inspector-empty"
          style={{ color: "var(--text-secondary)" }}
        >
          Select a node to edit its parameters.
        </p>
      );
    }
    if (tab === "code") return <CodePanel highlightVarName={highlightVarName} />;
    if (tab === "steps") {
      return (
        <StepsPanel
          onViewInCode={(varName) => {
            setHighlightVarName(varName);
            setTab("code");
          }}
        />
      );
    }
    return renderResults();
  }

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
        {lastRunAt !== null ? (
          <div
            data-testid="results-last-run"
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
          <div key={portName} style={{ marginBottom: "0.5rem" }}>
            <span style={{ fontWeight: 600 }}>{portName}</span>
            <PayloadView payload={payload} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <>
      <aside
        data-testid="inspector"
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
        }}
      >
        {renderHeader()}
        <div
          style={{
            padding: "var(--space-2) var(--space-3)",
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
          }}
        >
          {renderTabs()}
          <IconButton
            aria-label="Expand inspector"
            data-testid="inspector-expand-btn"
            onClick={() => setExpanded(true)}
          >
            <Maximize2 size={14} />
          </IconButton>
        </div>
        <div
          style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "0.5rem" }}
        >
          {renderBody()}
        </div>
      </aside>
      {expanded ? (
        <OverlayModal width={800} onClose={() => setExpanded(false)}>
          {renderHeader()}
          <div style={{ padding: "var(--space-2) var(--space-3)" }}>
            {renderTabs()}
          </div>
          <div
            style={{
              flex: 1,
              minHeight: 0,
              overflowY: "auto",
              padding: "0.5rem",
            }}
          >
            {renderBody()}
          </div>
        </OverlayModal>
      ) : null}
    </>
  );
}
