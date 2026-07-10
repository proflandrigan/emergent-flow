import { useState, type JSX } from "react";

import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import type { Decision, Gate } from "./sessionClient";
import { useSessionStore } from "./sessionStore";

function DecisionRow({ decision }: { decision: Decision }): JSX.Element {
  return (
    <div
      data-testid="gate-decision"
      style={{ fontSize: "var(--text-xs)", marginBottom: "0.15rem" }}
    >
      <span style={{ fontWeight: 600 }}>{decision.author}: </span>
      {decision.text}
    </div>
  );
}

function GateCard({ gate }: { gate: Gate }): JSX.Element {
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  const handleClose = () => {
    setShowCloseConfirm(true);
  };

  const handleConfirmClose = () => {
    void useSessionStore.getState().closeGate(gate.id);
  };

  const handleCancelClose = () => {
    setShowCloseConfirm(false);
  };

  const handleSkip = () => {
    void useSessionStore.getState().skipGate(gate.id);
  };

  const [decisionText, setDecisionText] = useState("");

  const handleAddDecision = () => {
    const text = decisionText.trim();
    if (!text) return;
    void useSessionStore
      .getState()
      .addGateDecision(gate.id, { author: "human", text });
    setDecisionText("");
  };

  return (
    <div
      data-testid="gate-card"
      style={{
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "0.5rem",
        marginBottom: "0.5rem",
      }}
    >
      <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>
        {gate.phase} — {gate.kind}
      </div>
      <div
        style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}
      >
        {gate.description}
      </div>
      <div
        data-testid="gate-status"
        style={{ fontSize: "var(--text-xs)", marginTop: "0.25rem" }}
      >
        {gate.status}
      </div>
      {gate.decisions.map((d) => (
        <DecisionRow key={d.id} decision={d} />
      ))}
      {gate.status === "open" ? (
        <>
          <div
            style={{
              display: "flex",
              gap: "var(--space-2)",
              marginTop: "0.5rem",
            }}
          >
            {showCloseConfirm ? (
              <>
                <Button
                  variant="primary"
                  data-testid="gate-close-confirm"
                  onClick={handleConfirmClose}
                >
                  Confirm close
                </Button>
                <Button
                  variant="ghost"
                  data-testid="gate-close-cancel"
                  onClick={handleCancelClose}
                >
                  Cancel
                </Button>
              </>
            ) : (
              <Button
                variant="secondary"
                data-testid="gate-close"
                onClick={handleClose}
              >
                Close
              </Button>
            )}
            <Button
              variant="ghost"
              data-testid="gate-skip"
              onClick={handleSkip}
            >
              Skip
            </Button>
          </div>
          <div
            style={{
              display: "flex",
              gap: "var(--space-2)",
              marginTop: "0.5rem",
            }}
          >
            <Input
              data-testid="gate-decision-input"
              value={decisionText}
              onChange={(e) => setDecisionText(e.target.value)}
              placeholder="Add a decision..."
            />
            <Button
              variant="secondary"
              data-testid="gate-decision-submit"
              onClick={handleAddDecision}
            >
              Add decision
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}

export function GatePanel(): JSX.Element | null {
  const sessionId = useSessionStore((s) => s.sessionId);
  const gates = useSessionStore((s) => s.gates);

  if (sessionId === null) {
    return null;
  }

  const list = Object.values(gates).sort((a, b) => a.id.localeCompare(b.id));
  const openCount = list.filter((g) => g.status === "open").length;

  return (
    <div data-testid="gate-panel">
      {openCount > 0 ? (
        <div
          data-testid="gate-open-banner"
          style={{
            background: "var(--warning-soft)",
            color: "var(--warning)",
            padding: "var(--space-2)",
            borderRadius: "var(--radius-md)",
            marginBottom: "var(--space-2)",
            fontSize: "var(--text-sm)",
          }}
        >
          {openCount} gate(s) open
        </div>
      ) : null}
      <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Gates</div>
      {list.length === 0 ? (
        <div
          data-testid="gate-panel-empty"
          style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}
        >
          No gates yet
        </div>
      ) : (
        list.map((g) => <GateCard key={g.id} gate={g} />)
      )}
    </div>
  );
}
