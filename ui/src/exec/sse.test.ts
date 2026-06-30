import { describe, expect, test } from "vitest";

import { readSSEEvents } from "./sse";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(encoder.encode(chunks[i]));
        i += 1;
      } else {
        controller.close();
      }
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const e of readSSEEvents(stream)) {
    events.push(e);
  }
  return events;
}

describe("sse", () => {
  test("parses a single complete SSE frame", async () => {
    const stream = streamOf(['data: {"type":"run_complete","total_ms":42}\n\n']);
    const events = await collect(stream);
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ type: "run_complete", total_ms: 42 });
  });

  test("parses multiple frames in one chunk", async () => {
    const stream = streamOf([
      'data: {"type":"node_start","node_id":"n1","label":"L","current":1,"total":2}\n\ndata: {"type":"node_ok","node_id":"n1","elapsed_ms":10,"results":{}}\n\n',
    ]);
    const events = await collect(stream);
    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({
      type: "node_start",
      node_id: "n1",
      label: "L",
      current: 1,
      total: 2,
    });
    expect(events[1]).toEqual({
      type: "node_ok",
      node_id: "n1",
      elapsed_ms: 10,
      results: {},
    });
  });

  test("reassembles a frame split across two chunks", async () => {
    const stream = streamOf([
      'data: {"type":"node_start","node_id":"n1","label":"L',
      '","current":1,"total":2}\n\n',
    ]);
    const events = await collect(stream);
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({
      type: "node_start",
      node_id: "n1",
      label: "L",
      current: 1,
      total: 2,
    });
  });

  test("reassembles a frame split across three chunks at the blank-line terminator", async () => {
    const stream = streamOf([
      'data: {"type":"run_error","error":"boom"}\n',
      "\n",
    ]);
    const events = await collect(stream);
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ type: "run_error", error: "boom" });
  });

  test("yields nothing for an empty stream", async () => {
    const stream = streamOf([]);
    const events = await collect(stream);
    expect(events).toHaveLength(0);
  });

  test("yields a final frame with no trailing blank line", async () => {
    const stream = streamOf(['data: {"type":"run_complete","total_ms":1}']);
    const events = await collect(stream);
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ type: "run_complete", total_ms: 1 });
  });

  test("parses a node_skip frame", async () => {
    const stream = streamOf(['data: {"type":"node_skip","node_id":"n2"}\n\n']);
    const events = await collect(stream);
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ type: "node_skip", node_id: "n2" });
  });
});
