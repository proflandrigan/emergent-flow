import { useState } from "react";

import { useConnectionProfiles } from "../catalog/useConnectionProfiles";
import { Button } from "../ui/Button";

interface TestEntry {
  status: "idle" | "loading" | "ok" | "error";
  message?: string;
}

export function ConnectionManagerPanel(): JSX.Element {
  const profiles = useConnectionProfiles();
  const [testStates, setTestStates] = useState<Record<string, TestEntry>>({});

  async function handleTest(name: string) {
    setTestStates((prev) => ({ ...prev, [name]: { status: "loading" } }));
    try {
      const res = await fetch(
        `/connections/${encodeURIComponent(name)}/test`,
        { method: "POST" },
      );
      const body = await res.json();
      if (!res.ok) {
        setTestStates((prev) => ({
          ...prev,
          [name]: { status: "error", message: body.error ?? "Test failed" },
        }));
        return;
      }
      setTestStates((prev) => ({
        ...prev,
        [name]: {
          status: body.ok ? "ok" : "error",
          message: body.message ?? "Test completed",
        },
      }));
    } catch {
      setTestStates((prev) => ({
        ...prev,
        [name]: { status: "error", message: "Test failed" },
      }));
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
      }}
    >
      <h2
        style={{
          fontSize: "var(--text-lg)",
          fontWeight: 600,
          margin: 0,
          color: "var(--text-primary)",
        }}
      >
        Connections
      </h2>

      {profiles.length === 0 ? (
        <div
          data-testid="connections-empty"
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--text-secondary)",
            lineHeight: 1.5,
          }}
        >
          No connection profiles are configured yet. Add one by editing{" "}
          <code>~/.config/emergentflow/connections.toml</code>{" "}
          (or the path from the <code>EMERGENTFLOW_CONNECTIONS</code>{" "}
          environment variable).
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-2)",
          }}
        >
          {profiles.map((p) => {
            const ts = testStates[p.name];
            return (
              <div
                key={p.name}
                data-testid={`connection-row-${p.name}`}
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
                    style={{
                      fontWeight: 600,
                      color: "var(--text-primary)",
                      fontSize: "var(--text-sm)",
                    }}
                  >
                    {p.name}
                  </span>
                  <span
                    style={{
                      fontSize: "var(--text-xs)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {p.dialect} &middot; {p.auth_method}
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--space-2)",
                  }}
                >
                  {ts?.status === "loading" && (
                    <span
                      data-testid={`connection-status-${p.name}`}
                      style={{
                        fontSize: "var(--text-xs)",
                        color: "var(--text-secondary)",
                      }}
                    >
                      Testing&hellip;
                    </span>
                  )}
                  {ts?.status === "ok" && (
                    <span
                      data-testid={`connection-status-${p.name}`}
                      style={{
                        fontSize: "var(--text-xs)",
                        color: "var(--success)",
                      }}
                    >
                      {ts.message}
                    </span>
                  )}
                  {ts?.status === "error" && (
                    <span
                      data-testid={`connection-status-${p.name}`}
                      style={{
                        fontSize: "var(--text-xs)",
                        color: "var(--danger)",
                      }}
                    >
                      {ts.message}
                    </span>
                  )}
                  <Button
                    variant="ghost"
                    data-testid={`connection-test-${p.name}`}
                    disabled={ts?.status === "loading"}
                    onClick={() => handleTest(p.name)}
                  >
                    Test
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
