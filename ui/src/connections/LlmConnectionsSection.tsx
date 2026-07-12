import { useEffect, useState } from "react";

import type { LlmConnectionProfileSummary } from "../catalog/useConnectionProfiles";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";

type ViewState =
  | { mode: "list" }
  | { mode: "create" }
  | { mode: "edit"; name: string };

interface LlmConnectionFormProps {
  initial: LlmConnectionProfileSummary | null;
  onCancel: () => void;
  onSaved: () => void;
}

function LlmConnectionForm({ initial, onCancel, onSaved }: LlmConnectionFormProps): JSX.Element {
  const [name, setName] = useState(initial?.name ?? "");
  const [provider, setProvider] = useState(initial?.provider ?? "");
  const [apiKeyEnv, setApiKeyEnv] = useState(initial?.api_key_env ?? "");
  const [baseUrlEnv, setBaseUrlEnv] = useState(initial?.base_url_env ?? "");
  const [defaultModel, setDefaultModel] = useState(initial?.default_model ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit() {
    setError(null);
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    if (!provider.trim()) {
      setError("Provider is required.");
      return;
    }
    if (!apiKeyEnv.trim()) {
      setError("API key env var is required.");
      return;
    }
    setSaving(true);
    const body = {
      name,
      kind: "llm",
      provider,
      api_key_env: apiKeyEnv,
      base_url_env: baseUrlEnv.trim() || null,
      default_model: defaultModel.trim() || null,
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
      data-testid="llm-connection-form"
      style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}
    >
      <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
        Name
        <Input
          data-testid="llm-form-name"
          value={name}
          disabled={initial !== null}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
        Provider
        <Input
          data-testid="llm-form-provider"
          placeholder="e.g. anthropic, openai, gemini"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        />
      </label>
      <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
        API key env var (env-var NAME only, never a literal secret)
        <Input
          data-testid="llm-form-api-key-env"
          placeholder="e.g. ANTHROPIC_API_KEY"
          value={apiKeyEnv}
          onChange={(e) => setApiKeyEnv(e.target.value)}
        />
      </label>
      <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
        Base URL env var (optional)
        <Input
          data-testid="llm-form-base-url-env"
          value={baseUrlEnv}
          onChange={(e) => setBaseUrlEnv(e.target.value)}
        />
      </label>
      <label style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
        Default model (optional)
        <Input
          data-testid="llm-form-default-model"
          value={defaultModel}
          onChange={(e) => setDefaultModel(e.target.value)}
        />
      </label>
      {error && (
        <div
          data-testid="llm-form-error"
          style={{ color: "var(--danger)", fontSize: "var(--text-sm)" }}
        >
          {error}
        </div>
      )}
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <Button
          variant="primary"
          data-testid="llm-form-save"
          disabled={saving}
          onClick={handleSubmit}
        >
          {initial ? "Save" : "Create"}
        </Button>
        <Button variant="ghost" data-testid="llm-form-cancel" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export function LlmConnectionsSection(): JSX.Element {
  const [profiles, setProfiles] = useState<LlmConnectionProfileSummary[]>([]);
  const [reloadToken, setReloadToken] = useState(0);
  const [view, setView] = useState<ViewState>({ mode: "list" });

  useEffect(() => {
    let cancelled = false;
    fetch("/connections")
      .then((res) => res.json() as Promise<{ connections: Array<Record<string, unknown>> }>)
      .then((data) => {
        if (!cancelled && data && Array.isArray(data.connections)) {
          setProfiles(
            data.connections.filter(
              (p) => p.kind === "llm",
            ) as unknown as LlmConnectionProfileSummary[],
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
          LLM Credentials
        </h3>
        {view.mode === "list" && (
          <Button
            variant="secondary"
            data-testid="llm-connection-new-button"
            onClick={() => setView({ mode: "create" })}
          >
            New LLM connection
          </Button>
        )}
      </div>

      {view.mode === "create" && (
        <LlmConnectionForm
          initial={null}
          onCancel={() => setView({ mode: "list" })}
          onSaved={refresh}
        />
      )}
      {view.mode === "edit" && (
        <LlmConnectionForm
          initial={profiles.find((p) => p.name === view.name) ?? null}
          onCancel={() => setView({ mode: "list" })}
          onSaved={refresh}
        />
      )}

      {view.mode === "list" && profiles.length === 0 && (
        <div
          data-testid="llm-connections-empty"
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--text-secondary)",
            lineHeight: 1.5,
          }}
        >
          No LLM credential profiles are configured yet. Click "New LLM connection" above to add
          one.
        </div>
      )}

      {view.mode === "list" && profiles.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {profiles.map((p) => (
            <div
              key={p.name}
              data-testid={`llm-connection-row-${p.name}`}
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
                <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
                  {p.provider}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <Button
                  variant="ghost"
                  data-testid={`llm-connection-edit-${p.name}`}
                  onClick={() => setView({ mode: "edit", name: p.name })}
                >
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  data-testid={`llm-connection-delete-${p.name}`}
                  onClick={() => handleDelete(p.name)}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
