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
    }
  | { kind: "record"; type: string; fields: Record<string, Payload> }
  | { kind: "json"; value: unknown }
  | { kind: "unsupported"; type: string; repr: string };

export type NodeStatus = "ok" | "error" | "skipped" | "cached" | "running";

export interface NodeRunStatus {
  status: NodeStatus;
  error?: string;
}

export const EXPECTED_PAYLOAD_VERSION = 2;

export interface ExecuteResponse {
  payload_version: number;
  results: Record<string, Record<string, Payload>>;
  statuses: Record<string, NodeRunStatus>;
}
