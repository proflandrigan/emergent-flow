import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
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
