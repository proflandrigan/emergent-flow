// Issue #95: the variable inspector's "Steps" tab. Lists every node's bound
// input/output variables, in execution order, using the compiler-allocated
// names the server's /inspect endpoint returns (grounded in the generated
// code by construction -- see emergentflow/codegen/inspect.py). Reuses the
// existing PayloadView for value rendering; does not build a new one.

import { useEffect, useState } from "react";

import type { Payload } from "../store/execution";
import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
import { PayloadView } from "./PayloadView";

export interface VarBinding {
  var_name: string;
  port_name: string;
  payload: Payload;
}

export interface StepTrace {
  step: number;
  node_id: string;
  node_label: string;
  status: string;
  inputs: VarBinding[];
  outputs: VarBinding[];
}

interface StepsPanelProps {
  onViewInCode: (varName: string) => void;
  debounceMs?: number;
}

export function StepsPanel({
  onViewInCode,
  debounceMs = 400,
}: StepsPanelProps): JSX.Element {
  const nodes = useGraphStore((s) => s.nodes);
  const edges = useGraphStore((s) => s.edges);
  const [steps, setSteps] = useState<StepTrace[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const graph = useGraphStore.getState().toIR();
    if (Object.keys(graph.nodes ?? {}).length === 0) {
      setSteps(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    const handle = setTimeout(() => {
      void (async () => {
        try {
          const res = await fetch("/inspect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(graph),
          });
          const body = await res.json();
          if (cancelled) {
            return;
          }
          if (!res.ok || body.error) {
            setError(body.error ?? `Server error ${res.status}`);
            setSteps(null);
          } else {
            setSteps(body.steps);
            setError(null);
          }
        } catch (err) {
          if (!cancelled) {
            const msg = err instanceof Error ? err.message : String(err);
            setError("Could not reach server: " + msg);
            setSteps(null);
          }
        } finally {
          if (!cancelled) {
            setLoading(false);
          }
        }
      })();
    }, debounceMs);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [nodes, edges, debounceMs]);

  function producingNodeId(steps: StepTrace[], varName: string): string | null {
    for (const step of steps) {
      if (step.outputs.some((b) => b.var_name === varName)) {
        return step.node_id;
      }
    }
    return null;
  }

  function handleSelectVariable(varName: string): void {
    if (!steps) {
      return;
    }
    const nodeId = producingNodeId(steps, varName);
    if (!nodeId) {
      return;
    }
    useSelectionStore.getState().clear();
    useSelectionStore.getState().setNodeSelected(nodeId, true);
  }

  function renderBinding(binding: VarBinding): JSX.Element {
    return (
      <div
        key={binding.var_name + ":" + binding.port_name}
        data-testid="steps-var-row"
        style={{
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-sm)",
          padding: "var(--space-2)",
          marginBottom: "var(--space-1)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
            cursor: "pointer",
          }}
          data-testid="steps-var-select"
          onClick={() => handleSelectVariable(binding.var_name)}
        >
          <code style={{ fontWeight: 600 }}>{binding.var_name}</code>
          <span style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
            ({binding.port_name})
          </span>
          <button
            type="button"
            data-testid="steps-view-in-code"
            onClick={(e) => {
              e.stopPropagation();
              onViewInCode(binding.var_name);
            }}
            style={{
              marginLeft: "auto",
              fontSize: "var(--text-sm)",
              background: "none",
              border: "none",
              color: "var(--accent)",
              cursor: "pointer",
            }}
          >
            View in code
          </button>
        </div>
        <PayloadView payload={binding.payload} />
      </div>
    );
  }

  if (Object.keys(nodes).length === 0) {
    return (
      <p data-testid="steps-empty" style={{ color: "var(--text-secondary)" }}>
        Add nodes to see step-by-step variable bindings.
      </p>
    );
  }

  if (loading && !error) {
    return (
      <p data-testid="steps-loading" style={{ color: "var(--text-secondary)" }}>
        Tracing...
      </p>
    );
  }

  if (error) {
    return (
      <pre
        data-testid="steps-error"
        style={{ color: "var(--danger)", whiteSpace: "pre-wrap" }}
      >
        {error}
      </pre>
    );
  }

  return (
    <div data-testid="steps-list">
      {(steps ?? []).map((step) => (
        <div key={step.node_id} style={{ marginBottom: "var(--space-3)" }}>
          <div style={{ fontWeight: 600, marginBottom: "var(--space-1)" }}>
            {step.step + 1}. {step.node_label}
          </div>
          {step.inputs.length > 0 ? (
            <div>
              <div style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
                Inputs
              </div>
              {step.inputs.map(renderBinding)}
            </div>
          ) : null}
          {step.outputs.length > 0 ? (
            <div>
              <div style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
                Outputs
              </div>
              {step.outputs.map(renderBinding)}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export default StepsPanel;
