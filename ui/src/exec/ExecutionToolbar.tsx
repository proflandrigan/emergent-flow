// Header controls for running the current graph. "Download .py" POSTs the IR to `/compile` and
// saves the returned code as a file; "Execute" POSTs the IR to `/execute/stream` and applies each
// SSE event to `executionStore` incrementally as it arrives, so node status/results update in
// real time instead of waiting for the whole graph to finish (Epic 7 Story 4).

import { useState } from "react";

import { useGraphStore } from "../store/graphStore";
import { useExecutionStore } from "../store/executionStore";
import type { ParamModel } from "../store/model";
import { runGraph } from "./runGraph";
import { Button } from "../ui/Button";
import { IconButton } from "../ui/IconButton";
import { Input } from "../ui/Input";

function parseOverrideValue(typeToken: string, raw: string): unknown {
  if (typeToken === "int") {
    const n = Number(raw);
    return Number.isNaN(n) ? raw : Math.round(n);
  }
  if (typeToken === "float") {
    const n = Number(raw);
    return Number.isNaN(n) ? raw : n;
  }
  if (typeToken === "bool") {
    return raw === "true";
  }
  return raw;
}

function buildOverrides(
  params: Record<string, ParamModel> | undefined,
  raw: Record<string, string>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [name, param] of Object.entries(params ?? {})) {
    const text = raw[name];
    if (text === undefined || text === "") {
      continue; // blank input -> use the graph's default value
    }
    out[name] = parseOverrideValue(param.typeToken, text);
  }
  return out;
}

export function ExecutionToolbar(): JSX.Element {
  const [error, setError] = useState<string | null>(null);
  const [clearingCache, setClearingCache] = useState(false);
  const running = useExecutionStore((s) => s.running);
  const progress = useExecutionStore((s) => s.progress);
  const [showParams, setShowParams] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const graphParams = useGraphStore((s) => s.params);
  const paramEntries = Object.values(graphParams ?? {});

  async function handleDownload() {
    const graph = useGraphStore.getState().toIR();
    if (Object.keys(graph.nodes ?? {}).length === 0) {
      setError("Add nodes before downloading.");
      return;
    }
    try {
      const res = await fetch("/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(graph),
      });
      const body = await res.json();
      if (!res.ok || body.error) {
        setError(body.error ?? `Server error ${res.status}`);
        return;
      }
      const blob = new Blob([body.code], { type: "text/x-python" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "graph.py";
      anchor.click();
      URL.revokeObjectURL(url);
      setError(null);
    } catch (err) {
      setError(
        "Could not reach server: " +
          (err instanceof Error ? err.message : String(err)),
      );
    }
  }

  async function handleExecute() {
    const graph = useGraphStore.getState().toIR();
    if (Object.keys(graph.nodes ?? {}).length === 0) {
      setError("Add nodes before executing.");
      return;
    }
    setError(null);
    await runGraph({
      params: buildOverrides(graphParams, overrides),
      onError: setError,
    });
  }

  async function handleClearCache() {
    setClearingCache(true);
    try {
      const res = await fetch("/cache/clear", { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error ?? `Server error ${res.status}`);
        return;
      }
      setError(null);
    } catch (err) {
      setError(
        "Could not reach server: " +
          (err instanceof Error ? err.message : String(err)),
      );
    } finally {
      setClearingCache(false);
    }
  }

  return (
    <div
      style={{
        display: "inline-flex",
        flexDirection: "column",
        gap: "var(--space-1)",
      }}
    >
      <div style={{ display: "inline-flex", gap: "var(--space-2)" }}>
        <Button variant="ghost" data-testid="exec-download" onClick={handleDownload}>
          Download .py
        </Button>
        <Button
          variant="primary"
          data-testid="exec-run"
          disabled={running || clearingCache}
          onClick={handleExecute}
        >
          {running ? "Running…" : "Execute"}
        </Button>
        {paramEntries.length > 0 ? (
          <Button
            variant="ghost"
            data-testid="exec-params-toggle"
            onClick={() => setShowParams((v) => !v)}
          >
            {showParams ? "Hide run params" : "Run params…"}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          data-testid="exec-clear-cache"
          disabled={running || clearingCache}
          onClick={handleClearCache}
        >
          {clearingCache ? "Clearing…" : "Clear cache"}
        </Button>
      </div>
      {showParams && paramEntries.length > 0 ? (
        <div
          data-testid="exec-params-form"
          style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}
        >
          {paramEntries.map((p) => (
            <label key={p.name} style={{ fontSize: "var(--text-sm)" }}>
              <span style={{ fontWeight: 600 }}>{p.name}</span> ({p.typeToken})
              <Input
                data-testid={`exec-param-${p.name}`}
                placeholder={
                  p.value !== null && p.value !== undefined ? String(p.value) : ""
                }
                value={overrides[p.name] ?? ""}
                onChange={(e) =>
                  setOverrides((o) => ({ ...o, [p.name]: e.target.value }))
                }
              />
            </label>
          ))}
        </div>
      ) : null}
      {progress && (
        <div
          data-testid="exec-progress"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-1)",
          }}
        >
          <div
            role="progressbar"
            aria-valuenow={progress.current}
            aria-valuemin={0}
            aria-valuemax={progress.total}
            style={{
              height: 4,
              borderRadius: "var(--radius-pill)",
              background: "var(--surface-2)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${(progress.current / progress.total) * 100}%`,
                background: "var(--accent)",
                borderRadius: "var(--radius-pill)",
              }}
            />
          </div>
          <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>
            Running node {progress.current} of {progress.total} ({progress.label}
            …)
          </span>
        </div>
      )}
      {error && (
        <div
          role="alert"
          data-testid="exec-error"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
            padding: "var(--space-2) var(--space-3)",
            borderRadius: "var(--radius-sm)",
            background: "var(--danger-soft)",
            border: "1px solid var(--danger)",
            color: "var(--danger)",
            fontSize: "var(--text-sm)",
          }}
        >
          <span>{error}</span>
          <IconButton aria-label="Dismiss" onClick={() => setError(null)}>
            ×
          </IconButton>
        </div>
      )}
    </div>
  );
}
