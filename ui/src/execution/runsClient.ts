import { postJson } from "../promptlab/httpJson";

export interface RunEntry {
  run_id: string;
  timestamp: number;
  duration_ms: number;
  node_count: number;
  tag: string | null;
  graph_name: string | null;
}

export interface RunDetail {
  run_id: string;
  tag: string | null;
  graph_name: string | null;
  graph_hash: string;
  started_at: number;
  finished_at: number;
  duration_ms: number;
  node_count: number;
  statuses: Record<string, { status: string; elapsed_ms?: number; error?: string }>;
  reproducibility: {
    seeds: Record<string, number>;
    content_hashes: Record<string, string>;
    dependency_versions: Record<string, string>;
  };
  sdk_version: string;
}

async function requestJson(path: string, init: RequestInit): Promise<Response> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.error ?? `Server error ${res.status}`);
  }
  return res;
}

export async function listRuns(): Promise<RunEntry[]> {
  const res = await requestJson("/runs", { method: "GET" });
  const body = (await res.json()) as { runs: RunEntry[] };
  return body.runs;
}

export async function getRun(runId: string): Promise<RunDetail> {
  const res = await requestJson(`/runs/${runId}`, { method: "GET" });
  return (await res.json()) as RunDetail;
}

export async function getRunGraph(runId: string): Promise<Record<string, unknown>> {
  const res = await requestJson(`/runs/${runId}/graph`, { method: "GET" });
  return (await res.json()) as Record<string, unknown>;
}

export async function deleteRun(runId: string): Promise<void> {
  await requestJson(`/runs/${runId}`, { method: "DELETE" });
}