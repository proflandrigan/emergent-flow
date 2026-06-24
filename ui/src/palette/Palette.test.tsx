import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { Palette } from "./Palette";

beforeEach(() => {
  useGraphStore.getState().reset();
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("renders catalog entries from the static fallback", () => {
  render(<Palette />);
  expect(screen.getByText(/Load CSV/)).toBeInTheDocument();
});

test("search filters the list to matching entries", () => {
  render(<Palette />);
  fireEvent.change(screen.getByTestId("palette-search"), {
    target: { value: "anova" },
  });
  expect(screen.queryByText(/Load CSV/)).not.toBeInTheDocument();
  expect(screen.getByText(/ANOVA/)).toBeInTheDocument();
});

test("clicking an entry adds a node to the store", () => {
  render(<Palette />);
  fireEvent.click(screen.getByText(/Load CSV/));

  const { nodes } = useGraphStore.getState();
  const ids = Object.keys(nodes);
  expect(ids).toHaveLength(1);
  expect(nodes[ids[0]].type).toBe("data.load_csv");
});
