import type { JSX } from "react";

import { snapshot, useGraphStore } from "../store/graphStore";
import type { Diagnostic, Diagnostics } from "../store/validation";
import { severityColor } from "../store/validation";
import { Button } from "../ui/Button";
import { computeGhostDiff } from "./ghostDiff";
import type { StoredProposal } from "./sessionClient";
import { useSessionStore } from "./sessionStore";

function DiagnosticsVerdict({
  diagnostics,
}: {
  diagnostics: Diagnostics;
}): JSX.Element {
  if (diagnostics.diagnostics.length === 0) {
    return (
      <div
        data-testid="proposal-verdict-clean"
        style={{
          color: "var(--success)",
          fontSize: "var(--text-xs)",
          marginTop: "0.25rem",
        }}
      >
        This proposal type-checks
      </div>
    );
  }
  return (
    <ul
      data-testid="proposal-diagnostics"
      style={{
        listStyle: "none",
        padding: 0,
        margin: "0.25rem 0 0",
        fontSize: "var(--text-xs)",
      }}
    >
      {diagnostics.diagnostics.map((d: Diagnostic, i: number) => (
        <li key={i} style={{ color: severityColor(d.severity) }}>
          {d.severity}: {d.message}
        </li>
      ))}
    </ul>
  );
}

function ProposalCard({ proposal }: { proposal: StoredProposal }): JSX.Element {
  const accept = useSessionStore((s) => s.accept);
  const reject = useSessionStore((s) => s.reject);

  const handleAccept = () => void accept(proposal.id);
  const handleReject = () => void reject(proposal.id);

  const handleEditIntoOwn = () => {
    const model = snapshot(useGraphStore.getState());
    const diff = computeGhostDiff(model, proposal.mutation);
    useGraphStore.getState().loadModel({
      ...model,
      nodes: {
        ...model.nodes,
        ...Object.fromEntries(diff.addedNodes.map((n) => [n.id, n])),
      },
      edges: {
        ...model.edges,
        ...Object.fromEntries(diff.addedEdges.map((e) => [e.id, e])),
      },
    });
    void reject(proposal.id);
  };

  return (
    <div
      data-testid="proposal-card"
      style={{
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "0.5rem",
        marginBottom: "0.5rem",
      }}
    >
      <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>
        {proposal.mutation.author ?? "human"}
      </div>
      {proposal.mutation.description ? (
        <div
          style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}
        >
          {proposal.mutation.description}
        </div>
      ) : null}
      <DiagnosticsVerdict diagnostics={proposal.diagnostics} />
      {proposal.status === "pending" ? (
        <div
          style={{
            display: "flex",
            gap: "var(--space-2)",
            marginTop: "0.5rem",
          }}
        >
          <Button
            variant="primary"
            onClick={handleAccept}
            data-testid="proposal-accept"
          >
            Accept
          </Button>
          <Button
            variant="secondary"
            onClick={handleReject}
            data-testid="proposal-reject"
          >
            Reject
          </Button>
          <Button
            variant="ghost"
            onClick={handleEditIntoOwn}
            data-testid="proposal-edit-into-own"
          >
            Edit into own
          </Button>
        </div>
      ) : (
        <div
          data-testid="proposal-status"
          style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}
        >
          {proposal.status}
        </div>
      )}
    </div>
  );
}

export interface ProposalPanelProps {
  className?: string;
}

export function ProposalPanel({
  className,
}: ProposalPanelProps): JSX.Element | null {
  const sessionId = useSessionStore((s) => s.sessionId);
  const proposals = useSessionStore((s) => s.proposals);

  if (sessionId === null) {
    return null;
  }

  const list = Object.values(proposals).sort((a, b) =>
    a.id.localeCompare(b.id),
  );

  return (
    <div className={className} data-testid="proposal-panel">
      <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Proposals</div>
      {list.length === 0 ? (
        <div
          data-testid="proposal-panel-empty"
          style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}
        >
          No proposals yet
        </div>
      ) : (
        list.map((p) => <ProposalCard key={p.id} proposal={p} />)
      )}
    </div>
  );
}
