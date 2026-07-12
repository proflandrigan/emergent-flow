import { useEffect, useState } from "react";

import { Button } from "../ui/Button";

interface SessionSummary {
  id: string;
  version: number;
  nodeCount: number;
  proposalCount: number;
}

type LoadState =
  | { status: "loading" }
  | { status: "ok"; sessions: SessionSummary[] }
  | { status: "auth-required" }
  | { status: "error"; message: string };

function toSessionSummary(raw: Record<string, unknown>): SessionSummary {
  const graph = (raw.graph ?? {}) as Record<string, unknown>;
  const nodes = (graph.nodes ?? {}) as Record<string, unknown>;
  const proposals = (raw.proposals ?? {}) as Record<string, unknown>;
  return {
    id: String(raw.id ?? ""),
    version: typeof raw.version === "number" ? raw.version : 0,
    nodeCount: Object.keys(nodes).length,
    proposalCount: Object.keys(proposals).length,
  };
}

export function CodingAgentsSection(): JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    fetch("/sessions")
      .then(async (res) => {
        if (cancelled) return;
        if (res.status === 401) {
          setState({ status: "auth-required" });
          return;
        }
        if (!res.ok) {
          setState({ status: "error", message: "Failed to load sessions" });
          return;
        }
        const data = (await res.json()) as { sessions?: Array<Record<string, unknown>> };
        const sessions = (data.sessions ?? []).map(toSessionSummary);
        setState({ status: "ok", sessions });
      })
      .catch(() => {
        if (!cancelled) {
          setState({ status: "error", message: "Failed to load sessions" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  async function handleEndSession(id: string) {
    await fetch(`/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
    setReloadToken((t) => t + 1);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <h3
        style={{
          fontSize: "var(--text-md)",
          fontWeight: 600,
          margin: 0,
          color: "var(--text-primary)",
        }}
      >
        Coding Agents
      </h3>

      <div
        data-testid="coding-agents-help"
        style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", lineHeight: 1.5 }}
      >
        An external coding agent (e.g. Claude Code) connects to this server's session API to
        co-author the graph with you. On the default localhost bind, no credential is needed. If
        this server is bound to a non-local host, set the <code>EMERGENTFLOW_SESSION_TOKEN</code>{" "}
        environment variable before starting it (<code>emergentflow serve</code>), and give that
        same value to the agent as its bearer token.
      </div>

      {state.status === "loading" && (
        <div
          data-testid="coding-agents-loading"
          style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}
        >
          Loading sessions&hellip;
        </div>
      )}

      {state.status === "auth-required" && (
        <div
          data-testid="coding-agents-auth-required"
          style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", lineHeight: 1.5 }}
        >
          Session auth is required on this server and no token was supplied, so active sessions
          can't be listed from this browser. Set <code>EMERGENTFLOW_SESSION_TOKEN</code> for the
          agent to use directly instead.
        </div>
      )}

      {state.status === "error" && (
        <div data-testid="coding-agents-error" style={{ fontSize: "var(--text-sm)", color: "var(--danger)" }}>
          {state.message}
        </div>
      )}

      {state.status === "ok" && state.sessions.length === 0 && (
        <div
          data-testid="coding-agents-empty"
          style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", lineHeight: 1.5 }}
        >
          No active collaboration sessions. An agent starts one via POST /sessions.
        </div>
      )}

      {state.status === "ok" && state.sessions.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {state.sessions.map((s) => (
            <div
              key={s.id}
              data-testid={`session-row-${s.id}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-3)",
                padding: "var(--space-2) var(--space-3)",
                borderRadius: "var(--radius-sm)",
                background: "var(--surface-2)",
              }}
            >
              <div
                style={{
                  flex: 1,
                  display: "flex",
                  flexDirection: "column",
                  gap: "var(--space-1)",
                }}
              >
                <span
                  style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "var(--text-sm)" }}
                >
                  {s.id}
                </span>
                <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                  {s.nodeCount} node{s.nodeCount === 1 ? "" : "s"} &middot; v{s.version}
                  {s.proposalCount > 0
                    ? ` · ${s.proposalCount} pending proposal${s.proposalCount === 1 ? "" : "s"}`
                    : ""}
                </span>
              </div>
              <Button
                variant="ghost"
                data-testid={`session-end-${s.id}`}
                onClick={() => handleEndSession(s.id)}
              >
                End session
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
