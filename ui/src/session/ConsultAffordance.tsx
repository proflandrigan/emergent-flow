import { useState } from "react";

import { Button } from "../ui/Button";
import { usePersonas } from "./usePersonas";
import { useSessionStore } from "./sessionStore";

export interface ConsultAffordanceProps {
  nodeId: string;
  personaSlug: string;
}

export function ConsultAffordance({
  nodeId,
  personaSlug,
}: ConsultAffordanceProps): JSX.Element | null {
  const sessionId = useSessionStore((s) => s.sessionId);
  const personas = usePersonas();
  const [open, setOpen] = useState(false);
  const [ask, setAsk] = useState("");
  const [inFlight, setInFlight] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (sessionId === null) {
    return null;
  }

  const persona = personas.find((p) => p.slug === personaSlug);
  const label = persona?.label ?? personaSlug;

  if (!open) {
    return (
      <Button
        variant="secondary"
        data-testid="consult-affordance-open"
        onClick={() => setOpen(true)}
      >
        Ask {label}
      </Button>
    );
  }

  const handleSubmit = async () => {
    if (!ask.trim() || inFlight) return;
    setInFlight(true);
    setError(null);
    try {
      await useSessionStore
        .getState()
        .consult({ persona: personaSlug, node_ids: [nodeId], ask: ask.trim() });
      setOpen(false);
      setAsk("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setInFlight(false);
    }
  };

  const handleCancel = () => {
    setOpen(false);
    setAsk("");
    setError(null);
  };

  return (
    <div
      data-testid="consult-affordance-form"
      style={{
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "0.5rem",
      }}
    >
      <textarea
        data-testid="consult-ask-input"
        placeholder={`What should ${label} do?`}
        value={ask}
        onChange={(e) => setAsk(e.target.value)}
        rows={3}
        style={{
          width: "100%",
          resize: "vertical",
          boxSizing: "border-box",
          fontSize: "var(--text-sm)",
          padding: "0.25rem",
        }}
      />
      {inFlight ? <span data-testid="consult-loading">Consulting…</span> : null}
      {error ? (
        <div
          data-testid="consult-error"
          style={{ color: "var(--danger)", fontSize: "var(--text-xs)" }}
        >
          {error}
        </div>
      ) : null}
      <div
        style={{ display: "flex", gap: "var(--space-2)", marginTop: "0.5rem" }}
      >
        <Button
          variant="primary"
          data-testid="consult-submit"
          disabled={!ask.trim() || inFlight}
          onClick={handleSubmit}
        >
          Ask
        </Button>
        <Button
          variant="ghost"
          data-testid="consult-cancel"
          onClick={handleCancel}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
