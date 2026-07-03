import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { PromptLabPanel } from "./PromptLabPanel";

afterEach(() => {
  vi.restoreAllMocks();
});

test("drives the full edit -> run -> compare -> label -> export flow", async () => {
  const clickSpy = vi.fn();
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:mock-url"),
    revokeObjectURL: vi.fn(),
  });
  HTMLAnchorElement.prototype.click = clickSpy;

  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, opts) => {
    const path = typeof url === "string" ? url : url.toString();
    const body = opts?.body ? JSON.parse(opts.body as string) : {};

    if (path === "/execute_node") {
      const nodeId = body.run_node as string;
      return new Response(
        JSON.stringify({
          payload_version: 2,
          results: {
            [nodeId]: {
              results: {
                kind: "table",
                head: [
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
                ],
              },
            },
          },
          statuses: { [nodeId]: { status: "ok" } },
        }),
        { status: 200 },
      );
    }

    if (path === "/eval/label") {
      return new Response(
        JSON.stringify({
          labeled: [
            {
              row_id: 0,
              input: { question: "2+2?" },
              messages: [{ role: "user", content: "2+2?" }],
              output: "4",
              label: "pass",
              score: 1,
            },
          ],
        }),
        { status: 200 },
      );
    }

    if (path === "/export/eval_set" || path === "/export/finetune") {
      return new Response(
        new Blob([
          '{"input":{"question":"2+2?"},"output":"4","label":"pass"}\n',
        ]),
        {
          status: 200,
          headers: {
            "Content-Disposition": 'attachment; filename="eval_set.jsonl"',
          },
        },
      );
    }

    throw new Error(`Unexpected fetch to ${path}`);
  });

  render(<PromptLabPanel />);

  fireEvent.change(screen.getByTestId("prompt-editor-system"), {
    target: { value: "You are terse." },
  });
  fireEvent.change(screen.getByTestId("prompt-editor-user"), {
    target: { value: "2+2?" },
  });

  fireEvent.click(
    within(screen.getByTestId("variant-picker")).getByTestId(
      "variant-checkbox-anthropic:claude-sonnet-5",
    ),
  );

  fireEvent.click(screen.getByTestId("prompt-lab-run"));

  await waitFor(() => {
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  fireEvent.click(
    within(
      screen.getByTestId("compare-grid-cell-0-anthropic:claude-sonnet-5"),
    ).getByTestId("label-pass"),
  );

  fireEvent.click(screen.getByTestId("prompt-lab-export-eval-set"));

  await waitFor(() => {
    expect(clickSpy).toHaveBeenCalled();
  });

  const calls = (
    globalThis.fetch as unknown as { mock: { calls: unknown[][] } }
  ).mock.calls.map((c) => c[0]);
  const labelIndex = calls.indexOf("/eval/label");
  const exportIndex = calls.indexOf("/export/eval_set");
  expect(labelIndex).toBeGreaterThanOrEqual(0);
  expect(exportIndex).toBeGreaterThanOrEqual(0);
  expect(labelIndex).toBeLessThan(exportIndex);

  expect(screen.queryByTestId("prompt-lab-error")).toBeNull();
});

test("a variable-less prompt sends one empty-binding row, not an empty dataset", async () => {
  // Regression test: InputSetTable hides its add-row UI for a variable-less prompt and
  // claims "this will run once with no bindings (single run mode)", but `dataset` state
  // used to stay `[]` forever, so eval.run's row loop never executed and Run silently
  // produced zero rows.
  let executeNodeBody: Record<string, unknown> | undefined;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, opts) => {
    const path = typeof url === "string" ? url : url.toString();
    const body = opts?.body ? JSON.parse(opts.body as string) : {};

    if (path === "/execute_node") {
      executeNodeBody = body;
      const nodeId = body.run_node as string;
      return new Response(
        JSON.stringify({
          payload_version: 2,
          results: {
            [nodeId]: {
              results: { kind: "table", columns: [], dtypes: [], shape: [1, 2], head: [] },
            },
          },
          statuses: { [nodeId]: { status: "ok" } },
        }),
        { status: 200 },
      );
    }

    throw new Error(`Unexpected fetch to ${path}`);
  });

  render(<PromptLabPanel />);

  fireEvent.change(screen.getByTestId("prompt-editor-user"), {
    target: { value: "2+2?" },
  });
  fireEvent.click(
    within(screen.getByTestId("variant-picker")).getByTestId(
      "variant-checkbox-anthropic:claude-sonnet-5",
    ),
  );
  fireEvent.click(screen.getByTestId("prompt-lab-run"));

  await waitFor(() => {
    expect(executeNodeBody).toBeDefined();
  });

  expect(executeNodeBody?.inputs).toEqual({ dataset: [{}] });
});

test("export buttons stay disabled until at least one row is labeled", async () => {
  // Regression test: the export buttons used to be gated only on `rows.length === 0`, so
  // clicking Export right after a run (before any label clicks) called `/eval/label` with
  // an empty `labels` array, which the server rejects with a raw LabelColumnError.
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, opts) => {
    const path = typeof url === "string" ? url : url.toString();
    const body = opts?.body ? JSON.parse(opts.body as string) : {};

    if (path === "/execute_node") {
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
                head: [
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
                ],
              },
            },
          },
          statuses: { [nodeId]: { status: "ok" } },
        }),
        { status: 200 },
      );
    }

    throw new Error(`Unexpected fetch to ${path}`);
  });

  render(<PromptLabPanel />);

  fireEvent.change(screen.getByTestId("prompt-editor-user"), {
    target: { value: "2+2?" },
  });
  fireEvent.click(
    within(screen.getByTestId("variant-picker")).getByTestId(
      "variant-checkbox-anthropic:claude-sonnet-5",
    ),
  );
  fireEvent.click(screen.getByTestId("prompt-lab-run"));

  await waitFor(() => {
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  expect(screen.getByTestId("prompt-lab-export-eval-set")).toBeDisabled();
  expect(screen.getByTestId("prompt-lab-export-finetune")).toBeDisabled();

  fireEvent.click(
    within(
      screen.getByTestId("compare-grid-cell-0-anthropic:claude-sonnet-5"),
    ).getByTestId("label-pass"),
  );

  expect(screen.getByTestId("prompt-lab-export-eval-set")).toBeEnabled();
  expect(screen.getByTestId("prompt-lab-export-finetune")).toBeEnabled();
});
