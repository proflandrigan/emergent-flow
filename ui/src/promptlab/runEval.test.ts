import { afterEach, expect, test, vi } from "vitest";

import { runEval } from "./runEval";

afterEach(() => {
  vi.restoreAllMocks();
});

const baseInput = {
  system: "You are a {{persona}} assistant.",
  user: "Answer: {{question}}",
  variants: [{ provider: "anthropic", model: "claude-sonnet-5" }],
  dataset: [{ persona: "helpful", question: "hi" }],
};

test("posts the built graph and dataset to /execute_node", async () => {
  const fetchSpy = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (_url, opts) => {
      const body = JSON.parse((opts as RequestInit).body as string);
      const nodeId = body.run_node as string;
      return new Response(
        JSON.stringify({
          payload_version: 2,
          results: { [nodeId]: { results: { kind: "table", head: [] } } },
          statuses: { [nodeId]: { status: "ok" } },
        }),
        { status: 200 },
      );
    });

  await runEval(baseInput);

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  const [url, opts] = fetchSpy.mock.calls[0];
  expect(url).toBe("/execute_node");
  const requestBody = JSON.parse((opts as RequestInit).body as string);
  expect(requestBody.graph).toBeDefined();
  expect(typeof requestBody.run_node).toBe("string");
  expect(requestBody.inputs.dataset).toEqual(baseInput.dataset);
});

test("returns the parsed rows on success", async () => {
  const row = {
    row_id: 0,
    input: { q: "hi" },
    messages: [{ role: "user", content: "hi" }],
    provider: "anthropic",
    model: "claude-sonnet-5",
    output: "hello",
    input_tokens: 5,
    output_tokens: 3,
    cost_usd: 0.001,
    latency_ms: 100,
    finish_reason: "stop",
  };

  vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, opts) => {
    const body = JSON.parse((opts as RequestInit).body as string);
    const nodeId = body.run_node as string;
    return new Response(
      JSON.stringify({
        payload_version: 2,
        results: {
          [nodeId]: {
            results: {
              kind: "table",
              columns: [],
              dtypes: [],
              shape: [1, 2],
              head: [row],
              truncated: false,
            },
          },
        },
        statuses: { [nodeId]: { status: "ok" } },
      }),
      { status: 200 },
    );
  });

  const result = await runEval(baseInput);

  expect(result).toEqual([row]);
});

test("throws on a non-2xx response", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ error: "bad graph" }), { status: 422 }),
  );

  await expect(runEval(baseInput)).rejects.toThrow("bad graph");
});

test("throws when the table payload is truncated", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, opts) => {
    const body = JSON.parse((opts as RequestInit).body as string);
    const nodeId = body.run_node as string;
    return new Response(
      JSON.stringify({
        payload_version: 2,
        results: {
          [nodeId]: {
            results: {
              kind: "table",
              columns: [],
              dtypes: [],
              shape: [60, 2],
              head: [],
              truncated: true,
            },
          },
        },
        statuses: { [nodeId]: { status: "ok" } },
      }),
      { status: 200 },
    );
  });

  await expect(runEval(baseInput)).rejects.toThrow("60");
});

test('throws when the node status is "error"', async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, opts) => {
    const body = JSON.parse((opts as RequestInit).body as string);
    const nodeId = body.run_node as string;
    return new Response(
      JSON.stringify({
        payload_version: 2,
        results: {},
        statuses: { [nodeId]: { status: "error", error: "boom" } },
      }),
      { status: 200 },
    );
  });

  await expect(runEval(baseInput)).rejects.toThrow("boom");
});
