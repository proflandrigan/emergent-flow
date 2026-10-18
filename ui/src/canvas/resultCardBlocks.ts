// Block model for the `reports.result_card` node. Blocks are stored as a JSON string in the
// node's `blocks_json` param; these helpers never throw on malformed input.

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
