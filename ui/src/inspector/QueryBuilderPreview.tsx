import { useEffect, useState } from "react";
import { useGraphStore } from "../store/graphStore";
import type { NodeModel } from "../store/model";

interface QueryBuilderPreviewProps {
  node: NodeModel;
}

function buildSpec(node: NodeModel): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const p of node.params) {
    values[p.name] = p.value;
  }
  const spec: Record<string, unknown> = {
    source: String(values.source ?? ""),
  };
  for (const key of [
    "select",
    "where",
    "join",
    "group_by",
    "having",
    "order_by",
  ] as const) {
    const val = values[key];
    if (val && Array.isArray(val) && val.length > 0) {
      spec[key] = val;
    }
  }
  const limit = values.limit;
  if (limit != null) {
    spec.limit = limit;
  }
  if (values.distinct === true) {
    spec.distinct = true;
  }
  return spec;
}

function findParamValue(node: NodeModel, name: string): unknown {
  for (const p of node.params) {
    if (p.name === name) {
      return p.value;
    }
  }
  return null;
}

export function QueryBuilderPreview({
  node,
}: QueryBuilderPreviewProps): JSX.Element {
  const [sql, setSql] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [costLoading, setCostLoading] = useState(false);
  const [costResult, setCostResult] = useState<{
    bytesScanned: number | null;
    costUsd: number | null;
  } | null>(null);
  const [costError, setCostError] = useState<string | null>(null);

  const dialect = String(findParamValue(node, "dialect") ?? "duckdb");
  const spec = buildSpec(node);
  const specKey = JSON.stringify({ spec, dialect });

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setSql(null);
    // Debounced: specKey changes on every keystroke in the query-builder form, and firing
    // a /compile-spec round-trip per character floods the server and causes response
    // reordering; wait for a short pause in typing before compiling.
    const timer = setTimeout(() => {
      fetch("/compile-spec", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ spec, dialect }),
      })
        .then(async (res) => {
          if (!cancelled) {
            if (res.ok) {
              const data = (await res.json()) as { sql: string };
              setSql(data.sql);
            } else {
              const data = (await res.json()) as { error?: string };
              setError(data.error ?? `Compile error: ${res.status}`);
            }
          }
        })
        .catch(() => {
          if (!cancelled) {
            setError("Failed to compile spec");
          }
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [specKey, dialect]);

  function handleEstimateCost() {
    setCostLoading(true);
    setCostResult(null);
    setCostError(null);

    const ir = useGraphStore.getState().toIR();
    const patched = structuredClone(ir);
    const nodeId = node.id;
    if (patched.nodes && patched.nodes[nodeId]?.params) {
      for (const p of patched.nodes[nodeId].params!) {
        if (p.name === "dry_run") {
          p.value = true;
        }
      }
    }

    fetch("/execute_node", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ graph: patched, run_node: nodeId, inputs: {} }),
    })
      .then(async (res) => {
        if (!res.ok) {
          const data = (await res.json()) as { error?: string };
          setCostError(data.error ?? `Server error: ${res.status}`);
          return;
        }
        const data = (await res.json()) as {
          statuses?: Record<string, { status: string; error?: string }>;
          results?: Record<
            string,
            Record<string, { kind: string; value?: unknown }>
          >;
        };
        const nodeStatus = data.statuses?.[nodeId];
        if (!nodeStatus || nodeStatus.status === "error") {
          setCostError(nodeStatus?.error ?? "Dry run returned an error status");
          return;
        }
        // 'cost_estimate' is always a plain {dialect, bytes_scanned, cost_usd} dict
        // (serialized as kind: "json"), never the query's 'frame' output -- 'frame' stays
        // a genuine (empty, under dry_run) DataFrame regardless of dry_run.
        const costPayload = data.results?.[nodeId]?.cost_estimate;
        if (
          costPayload?.kind === "json" &&
          costPayload.value &&
          typeof costPayload.value === "object"
        ) {
          const value = costPayload.value as {
            bytes_scanned?: number | null;
            cost_usd?: number | null;
          };
          setCostResult({
            bytesScanned: value.bytes_scanned ?? null,
            costUsd: value.cost_usd ?? null,
          });
        } else {
          setCostError("Unexpected response format from dry run");
        }
      })
      .catch(() => {
        setCostError("Network error during dry run");
      })
      .finally(() => {
        setCostLoading(false);
      });
  }

  return (
    <div style={{ marginTop: "0.75rem" }}>
      <label
        style={{ display: "block", fontWeight: 600, marginBottom: "0.25rem" }}
      >
        SQL Preview
      </label>
      {error ? (
        <pre
          data-testid="query-builder-sql-preview-error"
          style={{
            color: "var(--danger)",
            fontFamily: "monospace",
            fontSize: "0.8rem",
            whiteSpace: "pre-wrap",
            margin: 0,
          }}
        >
          {error}
        </pre>
      ) : (
        <pre
          data-testid="query-builder-sql-preview"
          style={{
            width: "100%",
            fontFamily: "monospace",
            fontSize: "0.8rem",
            whiteSpace: "pre-wrap",
            margin: 0,
          }}
        >
          {sql ?? "Loading..."}
        </pre>
      )}

      <button
        type="button"
        data-testid="query-builder-estimate-cost"
        disabled={costLoading}
        onClick={handleEstimateCost}
        style={{ marginTop: "0.5rem" }}
      >
        {costLoading ? "Estimating…" : "Estimate cost"}
      </button>

      {costError ? (
        <div
          data-testid="query-builder-cost-error"
          style={{
            color: "var(--danger)",
            fontSize: "0.8rem",
            marginTop: "0.25rem",
          }}
        >
          {costError}
        </div>
      ) : null}

      {costResult ? (
        <div
          data-testid="query-builder-cost-badge"
          style={{ fontSize: "0.8rem", marginTop: "0.25rem" }}
        >
          {costResult.bytesScanned != null ? (
            <div>~{costResult.bytesScanned.toLocaleString()} bytes scanned</div>
          ) : null}
          {costResult.costUsd != null ? (
            <div>~${costResult.costUsd.toFixed(6)} estimated</div>
          ) : null}
          {costResult.bytesScanned == null && costResult.costUsd == null ? (
            <div>No cost estimate available for this dialect</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
