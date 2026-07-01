// Parses a `text/event-stream` response body (from `POST /execute/stream`) into typed per-node
// execution events. SSE frames ("data: <json>\n\n") can split across network reads at any byte
// offset, so the buffer carries any incomplete frame over to the next chunk rather than assuming
// one `read()` call returns exactly one frame.

import type { Payload } from "../store/execution";

// `payload_version` is optional in the type (even though the real server always sends it) so
// that a frame missing it is simply not version-checked rather than failing to parse -- see
// `runGraph.ts`'s tolerant comparison.
export type StreamEvent =
  | {
      type: "node_start";
      node_id: string;
      label: string;
      current: number;
      total: number;
      payload_version?: number;
    }
  | {
      type: "node_ok";
      node_id: string;
      elapsed_ms: number;
      results: Record<string, Payload>;
      cached: boolean;
      payload_version?: number;
    }
  | {
      type: "node_error";
      node_id: string;
      elapsed_ms: number;
      error: string;
      payload_version?: number;
    }
  | { type: "node_skip"; node_id: string; payload_version?: number }
  | { type: "run_complete"; total_ms: number; payload_version?: number }
  | { type: "run_error"; error: string; payload_version?: number };

function parseFrame(frame: string): StreamEvent | null {
  for (const line of frame.split("\n")) {
    if (line.startsWith("data: ")) {
      return JSON.parse(line.slice("data: ".length)) as StreamEvent;
    }
  }
  return null;
}

export async function* readSSEEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<StreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = parseFrame(frame);
        if (event) yield event;
      }
    }
    const trailing = parseFrame(buffer);
    if (trailing) yield trailing;
  } finally {
    reader.releaseLock();
  }
}
