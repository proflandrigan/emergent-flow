export type Payload =
  | { kind: "scalar"; value: string | number | boolean | null }
  | { kind: "text"; value: string; length: number; truncated: boolean }
  | { kind: "image"; mime: string; data: string; width: number; height: number }
  | { kind: "html"; value: string; truncated: boolean }
  | {
      kind: "table";
      columns: string[];
      dtypes: string[];
      shape: [number, number];
      head: Record<string, unknown>[];
      truncated: boolean;
      describe?: Record<string, Record<string, number | string | null>>;
    }
  | { kind: "record"; type: string; fields: Record<string, Payload> }
  | { kind: "json"; value: unknown }
  | { kind: "unsupported"; type: string; repr: string };

export type NodeStatus = "ok" | "error" | "skipped" | "cached" | "running";

export interface NodeRunStatus {
  status: NodeStatus;
  error?: string;
  reason?: string;
}

/** Identity of a completed run: `runId` is null when the server supplied none. */
export interface RunMeta {
  runId: string | null;
  /** ISO-8601 UTC completion timestamp. */
  finishedAt: string;
}

export const EXPECTED_PAYLOAD_VERSION = 2;

export interface ExecuteResponse {
  payload_version: number;
  results: Record<string, Record<string, Payload>>;
  statuses: Record<string, NodeRunStatus>;
  /** Artifact-store revision per node stored during this run (additive; absent on older servers). */
  artifact_revisions?: Record<string, string>;
  /** Id of the persisted run record; null for partial scopes or when saving failed. */
  run_id?: string | null;
}
