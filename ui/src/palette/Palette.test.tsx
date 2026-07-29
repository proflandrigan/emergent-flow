import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useGraphStore } from "../store/graphStore";
import { Palette } from "./Palette";

beforeEach(() => {
  useGraphStore.getState().reset();
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
  localStorage.clear();
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

test("family sub-group header renders with correct node count", () => {
  render(<Palette />);
  const dataToggle = screen.getByText("Data").closest("button")!;
  // Bump this count whenever a data.* node is added to the catalog.
  // Epic 16 Story group A added http_fetch, load_excel, and load_google_sheet (7 -> 10).
  // Epic 16 Story group D added load_documents (10 -> 11).
  expect(dataToggle).toHaveTextContent("11");
});

test("clicking a family sub-group header hides its node rows", () => {
  render(<Palette />);
  expect(screen.getByText(/Load CSV/)).toBeInTheDocument();
  const dataToggle = screen.getByText("Data").closest("button")!;
  fireEvent.click(dataToggle);
  expect(screen.queryByText(/Load CSV/)).not.toBeInTheDocument();
});

test("collapse state persists to localStorage", () => {
  render(<Palette />);
  const dataToggle = screen.getByText("Data").closest("button")!;
  fireEvent.click(dataToggle);
  expect(localStorage.getItem("ef-palette-collapsed-families")).toBe(
    JSON.stringify(["data"]),
  );
});

test("node row has a title attribute carrying the catalog description", () => {
  render(<Palette />);
  const btn = screen.getByText(/Load CSV/).closest("button")!;
  expect(btn.getAttribute("title")).toBe("Load a CSV file into a pandas DataFrame.");
});

test("node row has an accessible name carrying both label and type", () => {
  render(<Palette />);
  expect(
    screen.getByRole("button", { name: "Load CSV (data.load_csv)" }),
  ).toBeInTheDocument();
});

test("searching for a term matching only one family hides other section headers", () => {
  render(<Palette />);
  fireEvent.change(screen.getByTestId("palette-search"), {
    target: { value: "anova" },
  });
  expect(screen.queryByText("Modeling")).not.toBeInTheDocument();
  expect(screen.queryByText("Data & Prep")).not.toBeInTheDocument();
  expect(screen.getByText("Analysis")).toBeInTheDocument();
  expect(screen.getByText("ANOVA")).toBeInTheDocument();
});

test("auto-expands a previously collapsed family when searching", () => {
  render(<Palette />);
  const dataToggle = screen.getByText("Data").closest("button")!;
  fireEvent.click(dataToggle);
  expect(screen.queryByText(/Load CSV/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByTestId("palette-search"), {
    target: { value: "load" },
  });
  expect(screen.getByText(/Load CSV/)).toBeInTheDocument();
});

test("clearing search query restores collapsed state after auto-expand", () => {
  render(<Palette />);
  const dataToggle = screen.getByText("Data").closest("button")!;
  fireEvent.click(dataToggle);
  expect(screen.queryByText(/Load CSV/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByTestId("palette-search"), {
    target: { value: "load" },
  });
  expect(screen.getByText(/Load CSV/)).toBeInTheDocument();
  fireEvent.change(screen.getByTestId("palette-search"), {
    target: { value: "" },
  });
  expect(screen.queryByText(/Load CSV/)).not.toBeInTheDocument();
});

test("hovering and un-hovering a node row does not throw and leaves it clickable", () => {
  render(<Palette />);
  const btn = screen.getByText(/Load CSV/).closest("button")!;

  fireEvent.mouseEnter(btn);
  fireEvent.mouseLeave(btn);

  expect(btn).toBeInTheDocument();

  fireEvent.click(btn);
  const { nodes } = useGraphStore.getState();
  const ids = Object.keys(nodes);
  expect(ids).toHaveLength(1);
  expect(nodes[ids[0]].type).toBe("data.load_csv");
});
