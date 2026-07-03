import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { RunHistory, type RunHistoryEntry } from "./RunHistory";

const entryA: RunHistoryEntry = {
  id: "entry-a",
  timestamp: Date.now() - 60000,
  system: "system a",
  user: "user a",
  variants: [{ provider: "openai", model: "gpt-4o" }],
  dataset: [{ question: "a" }, { question: "b" }],
  rows: [],
  labels: [],
};

const entryB: RunHistoryEntry = {
  id: "entry-b",
  timestamp: Date.now(),
  system: "system b",
  user: "user b",
  variants: [
    { provider: "openai", model: "gpt-4o" },
    { provider: "anthropic", model: "claude-3" },
  ],
  dataset: [{ question: "c" }],
  rows: [],
  labels: [],
};

test("empty state shows 'No runs yet'", () => {
  render(<RunHistory entries={[]} onSelect={vi.fn()} />);
  expect(screen.getByText("No runs yet")).toBeInTheDocument();
});

test("renders one entry per item with the correct summary text", () => {
  render(<RunHistory entries={[entryA, entryB]} onSelect={vi.fn()} />);
  expect(screen.getByText("1 variant × 2 rows")).toBeInTheDocument();
  expect(screen.getByText("2 variants × 1 row")).toBeInTheDocument();
});

test("renders entries in the given order (does not sort/reverse)", () => {
  render(<RunHistory entries={[entryB, entryA]} onSelect={vi.fn()} />);
  const list = screen.getByTestId("run-history");
  const buttons = within(list).getAllByRole("button");
  expect(buttons).toHaveLength(2);
  expect(buttons[0]).toBe(screen.getByTestId(`run-history-entry-${entryB.id}`));
  expect(buttons[1]).toBe(screen.getByTestId(`run-history-entry-${entryA.id}`));
});

test("clicking an entry calls onSelect with that exact entry object", () => {
  const onSelect = vi.fn();
  render(<RunHistory entries={[entryA, entryB]} onSelect={onSelect} />);
  fireEvent.click(screen.getByTestId(`run-history-entry-${entryA.id}`));
  expect(onSelect).toHaveBeenCalledTimes(1);
  expect(onSelect).toHaveBeenCalledWith(entryA);
});
