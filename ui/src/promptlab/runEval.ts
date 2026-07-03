import { buildEvalGraph, type EvalVariantParams } from "./buildEvalGraph";

export interface EvalRunRow {
  row_id: number;
  input: Record<string, unknown>;
  messages: { role: string; content: string }[];
  provider: string;
  model: string;
  output: unknown;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  finish_reason: string;
}

export interface RunEvalInput {
  system: string;
  user: string;
  variants: EvalVariantParams[];
  dataset: Record<string, string>[];
}

// POSTs a single-node eval.run graph (built by buildEvalGraph) to /execute_node with the
// dataset supplied directly as the unwired `dataset` IN port's input (Epic 9 Story 8's run
// trigger). Throws with a human-readable message on any failure (network error, a non-2xx
// response, or the node itself reporting an "error" status) rather than returning a union
// the caller must branch on, matching this project's `runGraph.ts` error-surfacing style.
export async function runEval(input: RunEvalInput): Promise<EvalRunRow[]> {
  const { graph, nodeId } = buildEvalGraph({
    system: input.system,
    user: input.user,
    variants: input.variants,
  });

  const res = await fetch("/execute_node", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      graph,
      run_node: nodeId,
      inputs: { dataset: input.dataset },
    }),
  });

  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.error ?? `Server error ${res.status}`);
  }

  const body = await res.json();
  const status = body.statuses?.[nodeId];
  if (status?.status === "error") {
    throw new Error(status.error ?? "eval.run failed");
  }

  const payload = body.results?.[nodeId]?.results;
  if (!payload || payload.kind !== "table") {
    throw new Error("Unexpected response shape from /execute_node");
  }

  return payload.head as EvalRunRow[];
}
