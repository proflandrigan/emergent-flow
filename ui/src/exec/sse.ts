// Parses a `text/event-stream` response body (from `POST /execute/stream`) into typed per-node
// execution events. SSE frames ("data: <json>\n\n") can split across network reads at any byte
// offset, so the buffer carries any incomplete frame over to the next chunk rather than assuming
// one `read()` call returns exactly one frame.

import type { Payload } from "../store/execution";

export type StreamEvent =
  | { type: "node_start"; node_id: string; label: string; current: number; total: number }
  | { type: "node_ok"; node_id: string; elapsed_ms: number; results: Record<string, Payload> }
  | { type: "node_error"; node_id: string; elapsed_ms: number; error: string }
  | { type: "run_complete"; total_ms: number }
  | { type: "run_error"; error: string };

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
