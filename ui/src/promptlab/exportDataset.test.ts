import { afterEach, expect, test, vi } from "vitest";

import { downloadDataset, labelRun } from "./exportDataset";

afterEach(() => {
  vi.restoreAllMocks();
});

test("labelRun posts to /eval/label and returns the labeled rows", async () => {
  const labeled = [{ row_id: 0, output: "4", label: "pass", score: 1 }];
  const fetchSpy = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(
      new Response(JSON.stringify({ labeled }), { status: 200 }),
    );

  const results = [
    {
      row_id: 0,
      input: { question: "2+2?" },
      messages: [{ role: "user", content: "2+2?" }],
      provider: "anthropic",
      model: "claude-sonnet-5",
      output: "4",
      input_tokens: 5,
      output_tokens: 1,
      cost_usd: 0.0001,
      latency_ms: 50,
      finish_reason: "stop",
    },
  ];
  const labels = [
    {
      row_id: 0,
      variant: "anthropic:claude-sonnet-5",
      label: "pass",
      score: 1,
    },
  ];

  const result = await labelRun(results, labels);

  expect(result).toEqual(labeled);
  expect(fetchSpy).toHaveBeenCalledTimes(1);
  const [url, opts] = fetchSpy.mock.calls[0];
  expect(url).toBe("/eval/label");
  const body = JSON.parse((opts as RequestInit).body as string);
  expect(body.results).toEqual(results);
  expect(body.labels).toEqual(labels);
});

test("labelRun throws on a non-2xx response", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ error: "bad" }), { status: 422 }),
  );

  await expect(labelRun([], [])).rejects.toThrow("bad");
});

test("downloadDataset posts rows to the right path per format", async () => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:mock-url"),
    revokeObjectURL: vi.fn(),
  });
  HTMLAnchorElement.prototype.click = vi.fn();

  const fetchSpy = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(
      async () => new Response(new Blob(["{}"]), { status: 200 }),
    );

  const rows = [{ input: { question: "2+2?" }, output: "4", label: "pass" }];

  await downloadDataset(rows, "eval_set");
  expect(fetchSpy.mock.calls[0][0]).toBe("/export/eval_set");

  await downloadDataset(rows, "finetune");
  expect(fetchSpy.mock.calls[1][0]).toBe("/export/finetune");
});

test("downloadDataset throws on a non-2xx response", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ error: "bad rows" }), { status: 422 }),
  );

  await expect(downloadDataset([], "eval_set")).rejects.toThrow("bad rows");
});
