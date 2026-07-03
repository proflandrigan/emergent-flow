import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { CompareGrid, type CompareGridLabel } from "./CompareGrid";
import type { EvalRunRow } from "./runEval";

const VARIANT_A = "anthropic:claude-sonnet-5";
const VARIANT_B = "anthropic:claude-haiku-4-5-20251001";

function makeRow(overrides: Partial<EvalRunRow>): EvalRunRow {
  return {
    row_id: 0,
    input: { q: "hi" },
    messages: [{ role: "user", content: "hi" }],
    provider: "anthropic",
    model: "claude-sonnet-5",
    output: "default output",
    input_tokens: 10,
    output_tokens: 5,
    cost_usd: 0.0012,
    latency_ms: 250,
    finish_reason: "stop",
    ...overrides,
  };
}

const rows: EvalRunRow[] = [
  makeRow({
    row_id: 0,
    provider: "anthropic",
    model: "claude-sonnet-5",
    output: "row0 sonnet output",
    input_tokens: 10,
    output_tokens: 5,
    cost_usd: 0.0012,
    latency_ms: 250,
  }),
  makeRow({
    row_id: 0,
    provider: "anthropic",
    model: "claude-haiku-4-5-20251001",
    output: "row0 haiku output",
  }),
  makeRow({
    row_id: 1,
    provider: "anthropic",
    model: "claude-sonnet-5",
    output: "row1 sonnet output",
  }),
  makeRow({
    row_id: 1,
    provider: "anthropic",
    model: "claude-haiku-4-5-20251001",
    output: "row1 haiku output",
  }),
];

test("renders one column per variant plus the input column", () => {
  render(<CompareGrid rows={rows} labels={[]} onLabelsChange={() => {}} />);

  expect(screen.getAllByRole("columnheader")).toHaveLength(3);
});

test("renders each cell's output text", () => {
  render(<CompareGrid rows={rows} labels={[]} onLabelsChange={() => {}} />);

  expect(screen.getByText("row0 sonnet output")).toBeInTheDocument();
  expect(screen.getByText("row0 haiku output")).toBeInTheDocument();
  expect(screen.getByText("row1 sonnet output")).toBeInTheDocument();
  expect(screen.getByText("row1 haiku output")).toBeInTheDocument();
});

test("renders each cell's cost/token/latency badge", () => {
  render(<CompareGrid rows={rows} labels={[]} onLabelsChange={() => {}} />);

  const cell = screen.getByTestId(`compare-grid-cell-0-${VARIANT_A}`);
  expect(
    within(cell).getByText("$0.0012 · 15 tok · 250ms"),
  ).toBeInTheDocument();
});

test("clicking Pass on one cell calls onLabelsChange with an upserted labels array, others untouched", () => {
  const onLabelsChange = vi.fn();
  render(
    <CompareGrid rows={rows} labels={[]} onLabelsChange={onLabelsChange} />,
  );

  const cell = screen.getByTestId(`compare-grid-cell-0-${VARIANT_A}`);
  fireEvent.click(within(cell).getByTestId("label-pass"));

  expect(onLabelsChange).toHaveBeenCalledTimes(1);
  const arg = onLabelsChange.mock.calls[0][0] as CompareGridLabel[];
  expect(arg).toEqual([
    { row_id: 0, variant: VARIANT_A, label: "pass", score: 1 },
  ]);
});

test("an existing label for one cell shows as active without affecting other cells", () => {
  const labels: CompareGridLabel[] = [
    { row_id: 0, variant: VARIANT_A, label: "pass", score: 1 },
  ];
  render(<CompareGrid rows={rows} labels={labels} onLabelsChange={() => {}} />);

  const labeledCell = screen.getByTestId(`compare-grid-cell-0-${VARIANT_A}`);
  expect(within(labeledCell).getByTestId("label-pass")).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  const otherCell = screen.getByTestId(`compare-grid-cell-0-${VARIANT_B}`);
  expect(within(otherCell).getByTestId("label-pass")).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});
