import { useEffect, useState } from "react";

import type { ConnectionProfileSummary } from "../catalog/useConnectionProfiles";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";

interface TestEntry {
  status: "idle" | "loading" | "ok" | "error";
  message?: string;
}

type ViewState =
  | { mode: "list" }
  | { mode: "create" }
  | { mode: "edit"; name: string };

interface WarehouseConnectionFormProps {
  initial: ConnectionProfileSummary | null;
  onCancel: () => void;
  onSaved: () => void;
}

function WarehouseConnectionForm({
  initial,
  onCancel,
  onSaved,
}: WarehouseConnectionFormProps): JSX.Element {
  const [name, setName] = useState(initial?.name ?? "");
  const [dialect, setDialect] = useState(initial?.dialect ?? "");
  const [authMethod, setAuthMethod] = useState(initial?.auth_method ?? "none");
  const [coordinatesText, setCoordinatesText] = useState(
    JSON.stringify(initial?.coordinates ?? {}, null, 2),
  );
  const [credentialRefsText, setCredentialRefsText] = useState(
    JSON.stringify(initial?.credential_refs ?? {}, null, 2),
  );
  const [limitsText, setLimitsText] = useState(JSON.stringify(initial?.limits ?? {}, null, 2));
  const [writeEnabled, setWriteEnabled] = useState(initial?.write_enabled ?? false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function parseJsonObject(text: string, label: string): Record<string, unknown> | null {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text.trim() === "" ? "{}" : text);
    } catch {
      setError(`${label} must be valid JSON.`);
      return null;
    }
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      setError(`${label} must be a JSON object.`);
      return null;
    }
    return parsed as Record<string, unknown>;
  }

  async function handleSubmit() {
    setError(null);
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    if (!dialect.trim()) {
      setError("Dialect is required.");
      return;
    }
    const coordinates = parseJsonObject(coordinatesText, "Coordinates");
    if (coordinates === null) return;
    const isImplicitAuth = authMethod === "adc" || authMethod === "implicit" || authMethod === "none";
    const credentialRefs = isImplicitAuth ? {} : parseJsonObject(credentialRefsText, "Credential refs");
    if (!isImplicitAuth && credentialRefs === null) return;
    const limits = parseJsonObject(limitsText, "Limits");
    if (limits === null) return;

    setSaving(true);
    const body = {
      name,
      kind: "warehouse",
      dialect,
      auth_method: authMethod,
      coordinates,
      credential_refs: credentialRefs,
      limits,
      write_enabled: writeEnabled,
    };
    try {
      const res = await fetch(
        initial ? `/connections/${encodeURIComponent(initial.name)}` : "/connections",
        {
          method: initial ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      const responseBody = await res.json();
      if (!res.ok) {
        setError(responseBody.error ?? "Save failed");
        setSaving(false);
        return;
      }
      onSaved();
    } catch {
      setError("Save failed");
      setSaving(false);
    }
  }

  return (
    <div
      data-testid="warehouse-connection-form"
      style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}
    >
      <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
        Name
        <Input
          data-testid="warehouse-form-name"
          value={name}
          disabled={initial !== null}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
        Dialect
        <Input
          data-testid="warehouse-form-dialect"
          placeholder="e.g. postgres, duckdb, bigquery, redshift"
          value={dialect}
          onChange={(e) => setDialect(e.target.value)}
        />
      </label>
      <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
        Auth method
        <select
          data-testid="warehouse-form-auth-method"
          value={authMethod}
          onChange={(e) => setAuthMethod(e.target.value)}
          style={{ width: "100%", padding: "6px 8px", fontSize: "0.875rem" }}
        >
          <option value="none">none — No authentication</option>
          <option value="password_env">password_env — Password from env var</option>
          <option value="service_account_file">
            service_account_file — Service account JSON file
          </option>
          <option value="adc">
            adc — Application Default Credentials (Google Cloud)
          </option>
          <option value="implicit">implicit — Implicit / environment auth (libpq)</option>
        </select>
      </label>
      <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
        Coordinates (JSON)
        <textarea
          data-testid="warehouse-form-coordinates"
          rows={3}
          style={{ width: "100%", fontFamily: "monospace", fontSize: "0.8rem" }}
          value={coordinatesText}
          onChange={(e) => setCoordinatesText(e.target.value)}
        />
      </label>
      {authMethod !== "adc" && authMethod !== "implicit" && authMethod !== "none" && (
        <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
          Credential refs (JSON — env-var NAMES only, never a literal secret)
          <textarea
            data-testid="warehouse-form-credential-refs"
            rows={3}
            style={{ width: "100%", fontFamily: "monospace", fontSize: "0.8rem" }}
            value={credentialRefsText}
            onChange={(e) => setCredentialRefsText(e.target.value)}
          />
        </label>
      )}
      <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
        Limits (JSON)
        <textarea
          data-testid="warehouse-form-limits"
          rows={2}
          style={{ width: "100%", fontFamily: "monospace", fontSize: "0.8rem" }}
          value={limitsText}
          onChange={(e) => setLimitsText(e.target.value)}
        />
      </label>
      <label
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          fontSize: "var(--text-sm)",
        }}
      >
        <input
          type="checkbox"
          data-testid="warehouse-form-write-enabled"
          checked={writeEnabled}
          onChange={(e) => setWriteEnabled(e.target.checked)}
        />
        Write enabled
      </label>
      {error && (
        <div
          data-testid="warehouse-form-error"
          style={{ color: "var(--danger)", fontSize: "var(--text-sm)" }}
        >
          {error}
        </div>
      )}
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <Button
          variant="primary"
          data-testid="warehouse-form-save"
          disabled={saving}
          onClick={handleSubmit}
        >
          {initial ? "Save" : "Create"}
        </Button>
        <Button variant="ghost" data-testid="warehouse-form-cancel" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export function WarehouseConnectionsSection(): JSX.Element {
  const [profiles, setProfiles] = useState<ConnectionProfileSummary[]>([]);
  const [reloadToken, setReloadToken] = useState(0);
  const [testStates, setTestStates] = useState<Record<string, TestEntry>>({});
  const [view, setView] = useState<ViewState>({ mode: "list" });

  useEffect(() => {
    let cancelled = false;
    fetch("/connections")
      .then((res) => res.json() as Promise<{ connections: Array<Record<string, unknown>> }>)
      .then((data) => {
        if (!cancelled && data && Array.isArray(data.connections)) {
          setProfiles(
            data.connections.filter(
              (p) => p.kind === "warehouse" || p.kind === undefined,
            ) as unknown as ConnectionProfileSummary[],
          );
        }
      })
      .catch(() => {
        /* keep whatever was last loaded */
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  function refresh() {
    setView({ mode: "list" });
    setReloadToken((t) => t + 1);
  }

  async function handleTest(name: string) {
    setTestStates((prev) => ({ ...prev, [name]: { status: "loading" } }));
    try {
      const res = await fetch(`/connections/${encodeURIComponent(name)}/test`, {
        method: "POST",
      });
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

  async function handleDelete(name: string) {
    await fetch(`/connections/${encodeURIComponent(name)}`, { method: "DELETE" });
    setReloadToken((t) => t + 1);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <h3
          style={{
            fontSize: "var(--text-md)",
            fontWeight: 600,
            margin: 0,
            color: "var(--text-primary)",
          }}
        >
          Warehouses
        </h3>
        {view.mode === "list" && (
          <Button
            variant="secondary"
            data-testid="connection-new-button"
            onClick={() => setView({ mode: "create" })}
          >
            New warehouse connection
          </Button>
        )}
      </div>

      {view.mode === "create" && (
        <WarehouseConnectionForm
          initial={null}
          onCancel={() => setView({ mode: "list" })}
          onSaved={refresh}
        />
      )}
      {view.mode === "edit" && (
        <WarehouseConnectionForm
          initial={profiles.find((p) => p.name === view.name) ?? null}
          onCancel={() => setView({ mode: "list" })}
          onSaved={refresh}
        />
      )}

      {view.mode === "list" && profiles.length === 0 && (
        <div
          data-testid="connections-empty"
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--text-secondary)",
            lineHeight: 1.5,
          }}
        >
          No connection profiles are configured yet. Click "New warehouse connection" above to
          add one, or hand-edit{" "}
          <code>~/.config/emergentflow/connections.toml</code>{" "}
          (or the path from the <code>EMERGENTFLOW_CONNECTIONS</code>{" "}
          environment variable).
        </div>
      )}

      {view.mode === "list" && profiles.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
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
                      style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}
                    >
                      Testing&hellip;
                    </span>
                  )}
                  {ts?.status === "ok" && (
                    <span
                      data-testid={`connection-status-${p.name}`}
                      style={{ fontSize: "var(--text-xs)", color: "var(--success)" }}
                    >
                      {ts.message}
                    </span>
                  )}
                  {ts?.status === "error" && (
                    <span
                      data-testid={`connection-status-${p.name}`}
                      style={{ fontSize: "var(--text-xs)", color: "var(--danger)" }}
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
                  <Button
                    variant="ghost"
                    data-testid={`connection-edit-${p.name}`}
                    onClick={() => setView({ mode: "edit", name: p.name })}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="ghost"
                    data-testid={`connection-delete-${p.name}`}
                    onClick={() => handleDelete(p.name)}
                  >
                    Delete
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
