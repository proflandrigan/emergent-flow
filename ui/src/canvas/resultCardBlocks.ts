// Block model for the `reports.result_card` node. Blocks are stored as a JSON string in the
// node's `blocks_json` param; these helpers never throw on malformed input.

import type { NodeRunStatus, Payload, RunMeta } from "../store/execution";

export type ResultCardBlock =
  | { kind: "markdown"; text: string }
  | { kind: "result"; source: string; caption: string }; // source = "<node_id>:<out_port_name>"

export function parseBlocks(json: unknown): ResultCardBlock[] {
  if (typeof json !== "string") {
    return [];
  }
  let raw: unknown;
  try {
    raw = JSON.parse(json);
  } catch {
    return [];
  }
  if (!Array.isArray(raw)) {
    return [];
  }
  const blocks: ResultCardBlock[] = [];
  for (const entry of raw as unknown[]) {
    if (typeof entry !== "object" || entry === null) {
      continue;
    }
    const rec = entry as Record<string, unknown>;
    if (rec.kind === "markdown" && typeof rec.text === "string") {
      blocks.push({ kind: "markdown", text: rec.text });
    } else if (rec.kind === "result" && typeof rec.source === "string") {
      blocks.push({
        kind: "result",
        source: rec.source,
        caption: typeof rec.caption === "string" ? rec.caption : "",
      });
    }
  }
  return blocks;
}

export function serializeBlocks(blocks: ResultCardBlock[]): string {
  return JSON.stringify(blocks);
}

export function splitSource(source: string): { nodeId: string; port: string } | null {
  const idx = source.lastIndexOf(":");
  if (idx < 0) {
    return null;
  }
  const nodeId = source.slice(0, idx);
  const port = source.slice(idx + 1);
  if (nodeId === "" || port === "") {
    return null;
  }
  return { nodeId, port };
}

export type BlockState = "ok" | "unrun" | "failed";

export interface ResolvedBlock {
  state: BlockState;
  payload: Payload | undefined;
  nodeId: string;
  port: string;
  /** Run identity of the last completed run (null when no run has completed). */
  runId: string | null;
  finishedAt: string | null;
}

/** Short display form of a run id (its trailing hash segment, else the first 8 chars). */
export function shortRunId(runId: string | null): string {
  if (!runId) {
    return "";
  }
  const tail = runId.split("-").pop() ?? "";
  return runId.length > 8 && tail.length >= 4 && tail.length < runId.length ? tail : runId.slice(0, 8);
}

/** One-line evidence text: `Run <short id> · <timestamp>`; empty when there is no run yet. */
export function formatRunEvidence(runId: string | null, finishedAt: string | null): string {
  const parts = [shortRunId(runId) !== "" ? `Run ${shortRunId(runId)}` : finishedAt ? "Run" : ""];
  if (finishedAt) {
    parts.push(finishedAt);
  }
  return parts.filter((p) => p !== "").join(" · ");
}

/**
 * Pure resolver: what a result block can honestly show given the execution state.
 * `ok` = a payload exists; `failed` = the source node errored with no payload; otherwise `unrun`
 * (never run, skipped, or an unparseable source).
 */
export function resolveBlockState(
  block: Extract<ResultCardBlock, { kind: "result" }>,
  results: Record<string, Record<string, Payload>>,
  statuses: Record<string, NodeRunStatus>,
  runMeta: RunMeta | null,
): ResolvedBlock {
  const parts = splitSource(block.source);
  const payload = parts ? results[parts.nodeId]?.[parts.port] : undefined;
  const status = parts ? statuses[parts.nodeId] : undefined;
  const state: BlockState = payload ? "ok" : status?.status === "error" ? "failed" : "unrun";
  return {
    state,
    payload,
    nodeId: parts?.nodeId ?? "",
    port: parts?.port ?? "",
    runId: runMeta?.runId ?? null,
    finishedAt: runMeta?.finishedAt ?? null,
  };
}
