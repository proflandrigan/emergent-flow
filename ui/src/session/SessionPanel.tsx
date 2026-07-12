// Session panel (Epic 14 Story 4): the human's entry point into session mode. Start a session
// (seeded from the current canvas graph) or join an existing one by id; once connected, shows
// a copyable session id + handoff instructions (there is no in-app "chat" -- the id is relayed
// out of band to whatever coding agent the human is running, per
// agents/emergent-flow-collaborator.md), the optimistic-concurrency "rebase" banner (surfaced by
// sessionStore's pushLocalGraph on a stale_version conflict -- never a silent overwrite), a Leave
// action, and the ProposalPanel. Rendered lazily by App.tsx behind the "Share session" overflow-
// menu item -- nothing in this module runs unless the user opens it.

import { useState, type JSX } from "react";

import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import { GatePanel } from "./GatePanel";
import { ProposalPanel } from "./ProposalPanel";
import { ReviewPanel } from "./ReviewPanel";
import { useSessionStore } from "./sessionStore";

function JoinOrCreate(): JSX.Element {
  const status = useSessionStore((s) => s.status);
  const error = useSessionStore((s) => s.error);
  const createAndJoin = useSessionStore((s) => s.createAndJoin);
  const join = useSessionStore((s) => s.join);
  const [joinId, setJoinId] = useState("");

  const connecting = status === "connecting";

  return (
    <div data-testid="session-panel">
      <div style={{ fontWeight: 600, marginBottom: "var(--space-2)" }}>
        Share session
      </div>
      <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
        There's no in-app chat -- starting a session gives you a session id to
        hand to a coding agent (e.g. paste it into a separate Claude Code
        chat) so it can propose changes to this graph over HTTP. Or join an
        existing session by id.
      </p>
      <Button
        variant="primary"
        disabled={connecting}
        onClick={() => void createAndJoin()}
        data-testid="session-start"
      >
        {connecting ? "Starting\u2026" : "Start session"}
      </Button>
      <div
        style={{
          display: "flex",
          gap: "var(--space-2)",
          marginTop: "var(--space-3)",
          alignItems: "center",
        }}
      >
        <Input
          data-testid="session-join-input"
          value={joinId}
          onChange={(e) => setJoinId(e.target.value)}
          placeholder="Session id"
        />
        <Button
          variant="secondary"
          disabled={connecting || joinId.trim() === ""}
          onClick={() => void join(joinId.trim())}
          data-testid="session-join"
        >
          Join
        </Button>
      </div>
      {status === "error" && error ? (
        <div
          data-testid="session-error"
          style={{
            color: "var(--danger)",
            marginTop: "var(--space-2)",
            fontSize: "var(--text-sm)",
          }}
        >
          {error}
        </div>
      ) : null}
    </div>
  );
}

function ActiveSession({ sessionId }: { sessionId: string }): JSX.Element {
  const rebaseNeeded = useSessionStore((s) => s.rebaseNeeded);
  const rebaseMessage = useSessionStore((s) => s.rebaseMessage);
  const dismissRebase = useSessionStore((s) => s.dismissRebase);
  const leave = useSessionStore((s) => s.leave);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    void navigator.clipboard
      .writeText(sessionId)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => {
        // Clipboard API unavailable (e.g. insecure context) -- the id is still
        // visible in the panel for the user to select and copy by hand.
      });
  };

  return (
    <div data-testid="session-panel">
      <div style={{ fontWeight: 600, marginBottom: "var(--space-2)" }}>
        Session {sessionId}
      </div>
      <div
        data-testid="session-handoff"
        style={{
          background: "var(--surface-2)",
          borderRadius: "var(--radius-md)",
          padding: "var(--space-2)",
          marginBottom: "var(--space-3)",
          fontSize: "var(--text-sm)",
        }}
      >
        <p style={{ margin: "0 0 var(--space-2)", color: "var(--text-secondary)" }}>
          Give this session id to a coding agent (e.g. paste it into a separate
          Claude Code chat) to let it propose changes here. Point it at{" "}
          <code>agents/emergent-flow-collaborator.md</code> for the HTTP
          protocol -- no token is needed if this server is on localhost.
        </p>
        <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
          <code
            data-testid="session-id-value"
            style={{
              flex: 1,
              padding: "var(--space-1) var(--space-2)",
              background: "var(--surface-3)",
              borderRadius: "var(--radius-sm)",
              overflowWrap: "anywhere",
            }}
          >
            {sessionId}
          </code>
          <Button
            variant="secondary"
            onClick={handleCopy}
            data-testid="session-copy-id"
          >
            {copied ? "Copied!" : "Copy"}
          </Button>
        </div>
      </div>
      {rebaseNeeded ? (
        <div
          data-testid="session-rebase-banner"
          style={{
            background: "var(--warning-soft)",
            color: "var(--warning)",
            padding: "var(--space-2)",
            borderRadius: "var(--radius-md)",
            marginBottom: "var(--space-2)",
            fontSize: "var(--text-sm)",
          }}
        >
          <div>
            {rebaseMessage ??
              "Your local changes are out of date with the session."}
          </div>
          <Button
            variant="ghost"
            onClick={dismissRebase}
            data-testid="session-rebase-dismiss"
          >
            Dismiss
          </Button>
        </div>
      ) : null}
      <ProposalPanel />
      <ReviewPanel />
      <GatePanel />
      <Button
        variant="secondary"
        onClick={leave}
        data-testid="session-leave"
        style={{ marginTop: "var(--space-3)" }}
      >
        Leave session
      </Button>
    </div>
  );
}

export function SessionPanel(): JSX.Element {
  const sessionId = useSessionStore((s) => s.sessionId);
  return sessionId === null ? (
    <JoinOrCreate />
  ) : (
    <ActiveSession sessionId={sessionId} />
  );
}
