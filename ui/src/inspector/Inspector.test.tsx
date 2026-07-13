import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import { useExecutionStore } from "../store/executionStore";
import { useGraphStore } from "../store/graphStore";
import { useSelectionStore } from "../store/selectionStore";
import { Inspector } from "./Inspector";

const fakeSpec: CatalogNode = {
  type: "t",
  version: 1,
  family: "f",
  label: "L",
  paradigm: "functional",
  ports: [],
  params: [],
};

beforeEach(() => {
  useSelectionStore.setState({ nodes: {}, edges: {} });
  useGraphStore.getState().reset();
  useExecutionStore.getState().clear();
});

test("with nothing selected, the Config tab shows the empty state", () => {
  render(<Inspector />);
  expect(screen.getByTestId("inspector-empty")).toBeInTheDocument();
});

test("clicking the Code tab shows the code panel and hides the empty state", () => {
  render(<Inspector />);
  fireEvent.click(screen.getByTestId("inspector-tab-code"));
  expect(screen.getByTestId("code-empty")).toBeInTheDocument();
  expect(screen.queryByTestId("inspector-empty")).not.toBeInTheDocument();
});

test("with exactly one node selected, the Config tab shows the config form", () => {
  const id = useGraphStore.getState().addNodeFromSpec(fakeSpec, { x: 0, y: 0 });
  useSelectionStore.getState().setNodeSelected(id, true);

  render(<Inspector />);

  expect(screen.getByTestId("config-form")).toBeInTheDocument();
  expect(screen.queryByTestId("inspector-empty")).not.toBeInTheDocument();
});

test("Results tab with nothing selected shows the no-selection empty state", () => {
  render(<Inspector />);
  fireEvent.click(screen.getByTestId("inspector-tab-results"));
  expect(screen.getByTestId("results-empty-no-selection")).toBeInTheDocument();
});

test("Results tab with a selected node but no results shows the run-first empty state", () => {
  const id = useGraphStore.getState().addNodeFromSpec(fakeSpec, { x: 0, y: 0 });
  useSelectionStore.getState().setNodeSelected(id, true);

  render(<Inspector />);
  fireEvent.click(screen.getByTestId("inspector-tab-results"));
  expect(screen.getByTestId("results-empty-no-run")).toBeInTheDocument();
});

test("Results tab renders the selected node's OUT-port payloads", () => {
  const id = useGraphStore.getState().addNodeFromSpec(fakeSpec, { x: 0, y: 0 });
  useSelectionStore.getState().setNodeSelected(id, true);
  useExecutionStore.setState({
    results: { [id]: { out: { kind: "scalar", value: 42 } } },
    statuses: { [id]: { status: "ok" } },
    lastRunAt: Date.now(),
  });

  render(<Inspector />);
  fireEvent.click(screen.getByTestId("inspector-tab-results"));
  expect(screen.getByTestId("results-list")).toBeInTheDocument();
  expect(screen.getByTestId("payload-scalar")).toHaveTextContent("42");
  expect(screen.getByTestId("results-last-run")).toHaveTextContent("ago");
});

test("Results tab shows the error string when the node errored", () => {
  const id = useGraphStore.getState().addNodeFromSpec(fakeSpec, { x: 0, y: 0 });
  useSelectionStore.getState().setNodeSelected(id, true);
  useExecutionStore.setState({
    results: {},
    statuses: { [id]: { status: "error", error: "boom" } },
    lastRunAt: Date.now(),
  });

  render(<Inspector />);
  fireEvent.click(screen.getByTestId("inspector-tab-results"));
  expect(screen.getByTestId("results-error")).toHaveTextContent("boom");
});

test("Expand button opens the inspector in a modal overlay", () => {
  const id = useGraphStore.getState().addNodeFromSpec(fakeSpec, { x: 0, y: 0 });
  useSelectionStore.getState().setNodeSelected(id, true);
  useExecutionStore.setState({
    results: { [id]: { out: { kind: "scalar", value: 42 } } },
    statuses: { [id]: { status: "ok" } },
    lastRunAt: Date.now(),
  });

  render(<Inspector />);

  // Expand button is always visible (not just on results tab)
  const expandBtn = screen.getByTestId("inspector-expand-btn");
  expect(expandBtn).toBeInTheDocument();

  fireEvent.click(expandBtn);

  // Modal should render — the OverlayModal has a close button
  expect(screen.getByTestId("overlay-modal-close")).toBeInTheDocument();

  // The modal contains the same tabs (there will be duplicates — one in sidebar, one in modal)
  const configTabs = screen.getAllByTestId("inspector-tab-config");
  expect(configTabs.length).toBe(2);
});

test("Expand button is visible even without results", () => {
  const id = useGraphStore.getState().addNodeFromSpec(fakeSpec, { x: 0, y: 0 });
  useSelectionStore.getState().setNodeSelected(id, true);

  render(<Inspector />);
  expect(screen.getByTestId("inspector-expand-btn")).toBeInTheDocument();
});

test("Clicking the X button in expanded modal closes it", () => {
  const id = useGraphStore.getState().addNodeFromSpec(fakeSpec, { x: 0, y: 0 });
  useSelectionStore.getState().setNodeSelected(id, true);

  render(<Inspector />);

  fireEvent.click(screen.getByTestId("inspector-expand-btn"));
  expect(screen.getByTestId("overlay-modal-close")).toBeInTheDocument();

  fireEvent.click(screen.getByTestId("overlay-modal-close"));
  expect(screen.queryByTestId("overlay-modal-close")).not.toBeInTheDocument();
});
