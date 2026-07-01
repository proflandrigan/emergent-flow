import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { runGraph } from "./runGraph";

beforeEach(() => {
  useGraphStore.getState().reset();
  useExecutionStore.getState().clear();
  useGraphStore.getState().addNodeFromSpec(
    {
      type: "t",
      version: 1,
      family: "f",
      label: "L",
      paradigm: "functional",
      ports: [],
      params: [],
    },
    { x: 0, y: 0 },
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

function sseResponse(
  events: Record<string, unknown>[],
  status = 200,
): Response {
  const body = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(body));
      controller.close();
    },
  });
  return new Response(stream, {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}

test("a node_skip event marks that node's status as skipped", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    sseResponse([
      { type: "node_start", node_id: "n1", label: "L", current: 1, total: 2 },
      { type: "node_error", node_id: "n1", elapsed_ms: 5, error: "boom" },
      { type: "node_skip", node_id: "n2" },
      { type: "run_complete", total_ms: 5 },
    ]),
  );

  await runGraph();

  expect(useExecutionStore.getState().statuses.n2).toEqual({
    status: "skipped",
  });
});

test("a stream that ends without run_complete/run_error surfaces an error instead of leaving running stuck", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    sseResponse([
      { type: "node_start", node_id: "n1", label: "L", current: 1, total: 1 },
    ]),
  );

  await runGraph();

  expect(useExecutionStore.getState().running).toBe(false);
  expect(useExecutionStore.getState().error).toMatch(/lost/i);
});

test("a mismatched payload_version on the first event fails the run before applying it", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    sseResponse([
      {
        type: "node_start",
        node_id: "n1",
        label: "L",
        current: 1,
        total: 1,
        payload_version: 999,
      },
      {
        type: "node_ok",
        node_id: "n1",
        elapsed_ms: 1,
        results: {},
        payload_version: 999,
      },
      { type: "run_complete", total_ms: 1, payload_version: 999 },
    ]),
  );

  await runGraph();

  expect(useExecutionStore.getState().error).toMatch(/incompatible/i);
  expect(useExecutionStore.getState().results).toEqual({});
  expect(useExecutionStore.getState().running).toBe(false);
});

test("a matching payload_version on events does not block the run", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    sseResponse([
      {
        type: "node_start",
        node_id: "n1",
        label: "L",
        current: 1,
        total: 1,
        payload_version: 2,
      },
      {
        type: "node_ok",
        node_id: "n1",
        elapsed_ms: 1,
        results: {},
        payload_version: 2,
      },
      { type: "run_complete", total_ms: 1, payload_version: 2 },
    ]),
  );

  await runGraph();

  expect(useExecutionStore.getState().error).toBeNull();
  expect(useExecutionStore.getState().statuses.n1).toEqual({ status: "ok" });
});

test("a node_ok event with cached: true sets that node's status to cached", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    sseResponse([
      { type: "node_start", node_id: "n1", label: "L", current: 1, total: 1 },
      {
        type: "node_ok",
        node_id: "n1",
        elapsed_ms: 1,
        results: {},
        cached: true,
      },
      { type: "run_complete", total_ms: 1 },
    ]),
  );

  await runGraph();

  expect(useExecutionStore.getState().statuses.n1).toEqual({
    status: "cached",
  });
});

test("a node_ok event with cached: false sets that node's status to ok", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    sseResponse([
      { type: "node_start", node_id: "n1", label: "L", current: 1, total: 1 },
      {
        type: "node_ok",
        node_id: "n1",
        elapsed_ms: 1,
        results: {},
        cached: false,
      },
      { type: "run_complete", total_ms: 1 },
    ]),
  );

  await runGraph();

  expect(useExecutionStore.getState().statuses.n1).toEqual({ status: "ok" });
});

test("calling runGraph while a run is already in flight is a no-op", async () => {
  let resolveFetch!: (res: Response) => void;
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockReturnValue(
    new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    }),
  );

  const first = runGraph();
  expect(useExecutionStore.getState().running).toBe(true);

  const second = runGraph();

  resolveFetch(sseResponse([{ type: "run_complete", total_ms: 0 }]));
  await Promise.all([first, second]);

  expect(fetchSpy).toHaveBeenCalledTimes(1);
});
